from typing import AsyncGenerator, Optional
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import OAuth2PasswordBearer

from ...database import AsyncSessionLocal
from ...models.user import User
from jose import JWTError, jwt
from ...config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def _resolve_user(
    token: Optional[str],
    db: AsyncSession,
) -> Optional[User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None

    user = await db.get(User, int(user_id))
    if not user or not user.is_active:
        return None
    return user


async def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """The current user when signed in, ``None`` otherwise.

    Use this for endpoints that work for anonymous readers and add
    personalised touches only when a user is present.
    """
    return await _resolve_user(token, db)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """The signed-in user, or an explicit 401.

    Endpoints that must be authenticated depend on this; they never see a
    ``None`` user and never have to guess what 'missing login' means.
    """
    user = await _resolve_user(token, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(current_user: Optional[User] = Depends(get_current_user)) -> User:
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return current_user


async def require_superadmin(current_user: Optional[User] = Depends(get_current_user)) -> User:
    """Owners/maintenance staff. Everything an admin can do, plus managing
    admin accounts, passwords and 'repair' maintenance tasks."""
    if not current_user or not (current_user.is_admin and current_user.is_superadmin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super-admin required")
    return current_user