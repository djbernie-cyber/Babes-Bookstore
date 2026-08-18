from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class CheckoutRequest(BaseModel):
    bundle_id: int
    email: EmailStr
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class PurchaseCreate(BaseModel):
    bundle_id: int
    email: EmailStr


class PurchaseResponse(BaseModel):
    id: int
    bundle_id: int
    customer_email: str
    amount_cents: int
    currency: str
    status: str
    download_token: str
    download_expires_at: Optional[datetime] = None
    download_count: int
    max_downloads: int
    created_at: datetime

    class Config:
        from_attributes = True