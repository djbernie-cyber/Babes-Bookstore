from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
import httpx

from ..deps import get_db, get_current_user
from ...models.user import User
from ...config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = None


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


@router.get("/google/login")
async def google_login():
    """Redirect to Google OAuth consent screen."""
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    if settings.PRODUCTION_URL and "localhost" not in settings.GOOGLE_REDIRECT_URI:
        redirect_uri = f"{settings.PRODUCTION_URL}/api/v1/auth/google/callback"
    elif settings.PRODUCTION_URL:
        redirect_uri = settings.GOOGLE_REDIRECT_URI.replace("localhost:8000", settings.PRODUCTION_URL.replace("https://", ""))

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"https://accounts.google.com/o/oauth2/v2/auth?{query}")


@router.get("/google/callback")
async def google_callback(code: str, state: str = None, db: AsyncSession = Depends(get_db)):
    """Handle Google OAuth callback — exchange code for tokens, create/find user, return JWT."""
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    if settings.PRODUCTION_URL and "localhost" not in settings.GOOGLE_REDIRECT_URI:
        redirect_uri = f"{settings.PRODUCTION_URL}/api/v1/auth/google/callback"
    elif settings.PRODUCTION_URL:
        redirect_uri = settings.GOOGLE_REDIRECT_URI.replace("localhost:8000", settings.PRODUCTION_URL.replace("https://", ""))

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
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
        hashed_password=pwd_context.hash(req.password),
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
    stmt = select(User).where(User.email == req.email)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not pwd_context.verify(req.password, user.hashed_password or ""):
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