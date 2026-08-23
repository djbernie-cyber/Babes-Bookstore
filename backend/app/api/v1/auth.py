from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from urllib.parse import urlencode
import httpx

from .deps import get_db, get_current_user
from ...models.user import User
from ...config import settings
from ...services.security import hash_password, verify_password, MIN_PASSWORD_LENGTH

router = APIRouter(prefix="/auth", tags=["auth"])



class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=256)
    name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class GoogleCallbackRequest(BaseModel):
    code: str
    state: str = None


def create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_or_create_google_user(email: str, name: str, google_id: str) -> User:
    from ...database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        stmt = select(User).where(User.email == email)
        user = (await db.execute(stmt)).scalar_one_or_none()
        if user:
            user.google_id = google_id
            if name and not user.name:
                user.name = name
        else:
            user = User(email=email, name=name, google_id=google_id)
            db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


def verify_google_token(token: str) -> dict:
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
        return {
            "email": idinfo["email"],
            "name": idinfo.get("name", ""),
            "google_id": idinfo["sub"],
        }
    except Exception:
        return None


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALLBACK_PATH = "/api/v1/auth/google/callback"


def _google_redirect_uri() -> str:
    """Single source of truth for the OAuth redirect URI.

    GOOGLE_REDIRECT_URI is authoritative when it points at a real host.
    When it is still the localhost default and we are running in
    production, derive the callback from PRODUCTION_URL so the deployed
    app does not send Google a localhost redirect.
    """
    uri = settings.GOOGLE_REDIRECT_URI
    if not settings.DEBUG and settings.PRODUCTION_URL and (
        "localhost" in uri or "127.0.0.1" in uri
    ):
        return f"{settings.PRODUCTION_URL.rstrip('/')}{GOOGLE_CALLBACK_PATH}"
    return uri


@router.get("/google/login")
async def google_login():
    """Redirect to Google OAuth consent screen."""
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID or "",
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    query = urlencode(params)
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{query}")


@router.get("/google/callback")
async def google_callback(code: str, state: str = None, db: AsyncSession = Depends(get_db)):
    """Handle Google OAuth callback — exchange code for tokens, create/find user, return JWT."""
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": _google_redirect_uri(),
                "grant_type": "authorization_code",
            },
        )

    if token_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Google authentication failed")

    token_data = token_response.json()
    id_token_str = token_data.get("id_token")

    if not id_token_str:
        raise HTTPException(status_code=400, detail="No ID token received")

    user_info = verify_google_token(id_token_str)
    if not user_info:
        raise HTTPException(status_code=400, detail="Invalid Google token")

    user = await get_or_create_google_user(
        email=user_info["email"],
        name=user_info["name"],
        google_id=user_info["google_id"],
    )

    app_token = create_access_token(user.id)
    return TokenResponse(
        access_token=app_token,
        user={"id": user.id, "email": user.email, "name": user.name, "is_admin": user.is_admin},
    )


@router.post("/google/token")
async def google_token_login(body: GoogleCallbackRequest, db: AsyncSession = Depends(get_db)):
    """Login with Google ID token (for frontend JS SDK)."""
    user_info = verify_google_token(body.code)
    if not user_info:
        raise HTTPException(status_code=400, detail="Invalid Google token")

    user = await get_or_create_google_user(
        email=user_info["email"],
        name=user_info["name"],
        google_id=user_info["google_id"],
    )

    app_token = create_access_token(user.id)
    return TokenResponse(
        access_token=app_token,
        user={"id": user.id, "email": user.email, "name": user.name, "is_admin": user.is_admin},
    )


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.email == req.email)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=req.email,
        name=req.name,
        hashed_password=hash_password(req.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "email": user.email, "name": user.name, "is_admin": user.is_admin},
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await _authenticate(req.email, req.password, db)


@router.post("/token", summary="OAuth2 password flow (Swagger / form clients)")
async def token(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    try:
        email = form.username.strip().lower()
    except AttributeError:
        raise HTTPException(status_code=422, detail="username is required")
    return await _authenticate(email, form.password, db)


async def _authenticate(email: str, password: str, db: AsyncSession) -> TokenResponse:
    stmt = select(User).where(User.email == email)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "email": user.email, "name": user.name, "is_admin": user.is_admin},
    )


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "is_admin": current_user.is_admin,
    }