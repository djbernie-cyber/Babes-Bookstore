from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from urllib.parse import urlencode
import httpx
import json

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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class GoogleCallbackRequest(BaseModel):
    code: str
    state: str = None


ALLOWED_THEME_KEYS = {
    "accent", "accent_text", "bg", "surface", "surface_hover", "text",
    "muted", "border", "font_serif", "font_body", "radius", "density",
    "paper", "link",
}


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    theme: Optional[str] = Field(None, pattern="^(light|dark|sepia)$")
    reader_font_size: Optional[str] = Field(None, pattern="^(s|m|l|xl)$")
    reader_theme: Optional[str] = Field(None, pattern="^(sepia|light|dark)$")
    locale: Optional[str] = Field(None, max_length=10)
    theme_prefs: Optional[dict] = None


def create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_reset_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=30)
    payload = {"sub": _norm_email(email), "purpose": "password_reset", "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "is_admin": user.is_admin,
        "is_superadmin": user.is_superadmin,
    }


async def get_or_create_google_user(email: str, name: str, google_id: str) -> User:
    from ...database import AsyncSessionLocal
    email = _norm_email(email)
    async with AsyncSessionLocal() as db:
        stmt = select(User).where(func.lower(User.email) == email)
        user = (await db.execute(stmt)).scalar_one_or_none()
        if user:
            if user.email != email:
                user.email = email
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
        user=_user_payload(user),
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
        user=_user_payload(user),
    )


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    email = _norm_email(req.email)
    stmt = select(User).where(func.lower(User.email) == email)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=email,
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
    stmt = select(User).where(func.lower(User.email) == _norm_email(email))
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "email": user.email, "name": user.name, "is_admin": user.is_admin},
    )


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Email a signed, 30-minute reset link when the address exists.

    Never discloses whether an account exists — responses are identical either
    way, matching the behaviour of every reputable store.
    """
    email = _norm_email(body.email)
    stmt = select(User).where(func.lower(User.email) == email)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is not None and user.is_active:
        token = create_reset_token(user.email)
        url = f"{settings.FRONTEND_URL.rstrip('/')}/account/reset?token={token}"
        from ...services.email_service import email_service
        email_service.send_password_reset(user.email, url)
    return {"message": "If that address has an account, a reset link is on its way."}


@router.post("/reset-password", response_model=TokenResponse)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Verify the signed reset token and set a fresh password, then log in."""
    try:
        payload = jwt.decode(body.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("purpose") != "password_reset":
            raise JWTError
        email = _norm_email(payload.get("sub") or "")
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    stmt = select(User).where(func.lower(User.email) == email)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user.hashed_password = hash_password(body.password)
    await db.commit()

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
        **_user_payload(current_user),
        "theme": current_user.theme,
        "theme_prefs": current_user.theme_prefs,
        "locale": current_user.locale,
        "reader_font_size": current_user.reader_font_size,
        "reader_theme": current_user.reader_theme,
        "free_downloads": current_user.free_downloads,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
    }


@router.put("/me")
async def update_me(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update account profile + reading/theme preferences (syncs per-account)."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if body.name is not None:
        current_user.name = body.name.strip() or None
    if body.theme is not None:
        current_user.theme = body.theme
    if body.reader_font_size is not None:
        current_user.reader_font_size = body.reader_font_size
    if body.reader_theme is not None:
        current_user.reader_theme = body.reader_theme
    if body.locale is not None:
        current_user.locale = body.locale.strip() or None
    if body.theme_prefs is not None:
        clean = {}
        for k, v in body.theme_prefs.items():
            if k in ALLOWED_THEME_KEYS and isinstance(v, str) and len(v) <= 80:
                clean[k] = v
        current_user.theme_prefs = json.dumps(clean) if clean else None
    await db.commit()
    await db.refresh(current_user)
    return {
        **_user_payload(current_user),
        "theme": current_user.theme,
        "theme_prefs": current_user.theme_prefs,
        "locale": current_user.locale,
        "reader_font_size": current_user.reader_font_size,
        "reader_theme": current_user.reader_theme,
    }