from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "Babe's Bookstore"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/babes_bookstore"
    SYNC_DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/babes_bookstore"

    REDIS_URL: str = "redis://localhost:6379/0"

    SECRET_KEY: str = "change-me-in-production-please-use-openssl-rand-hex-32"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # Standard pricing (£10 GBP)
    STANDARD_PRICE_PENCE: int = 1000
    CURRENCY: str = "gbp"
    CURRENCY_SYMBOL: str = "£"

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"
    PRODUCTION_URL: str = "https://babes-bookstore-api.fly.dev"

    # Cloudflare R2
    R2_ACCOUNT_ID: Optional[str] = None
    R2_ACCESS_KEY_ID: Optional[str] = None
    R2_SECRET_ACCESS_KEY: Optional[str] = None
    R2_BUCKET_NAME: str = "babes-bookstore"
    R2_PUBLIC_URL: Optional[str] = None

    # Stripe
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    # PayPal
    PAYPAL_CLIENT_ID: Optional[str] = None
    PAYPAL_CLIENT_SECRET: Optional[str] = None
    PAYPAL_MODE: str = "sandbox"  # sandbox or live
    PAYPAL_WEBHOOK_ID: Optional[str] = None

    # Square
    SQUARE_ACCESS_TOKEN: Optional[str] = None
    SQUARE_LOCATION_ID: Optional[str] = None
    SQUARE_ENVIRONMENT: str = "sandbox"  # sandbox or production

    # SendGrid
    SENDGRID_API_KEY: Optional[str] = None
    FROM_EMAIL: str = "noreply@babesbookstore.com"

    # Admin accounts (auto-created on startup with free downloads)
    ADMIN_EMAILS: list[str] = [
        "dj.bernie@hotmail.co.uk",
        "williammajanja@gmail.com",
    ]

    ALLOWED_LICENSES: list[str] = [
        "public_domain",
        "cc0_1.0",
        "cc_by_4.0",
        "cc_by_sa_4.0",
    ]

    BLOCKED_LICENSES: list[str] = [
        "cc_by_nc",
        "cc_by_nc_sa",
        "cc_by_nc_nd",
        "cc_by_nd",
        "proprietary",
        "all_rights_reserved",
    ]

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()