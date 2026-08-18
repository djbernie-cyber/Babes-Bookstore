from pydantic import BaseModel, EmailStr, model_validator
from typing import Optional
from datetime import datetime


class CheckoutRequest(BaseModel):
    bundle_id: Optional[int] = None
    bundle_slug: Optional[str] = None
    email: EmailStr
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None

    @model_validator(mode="after")
    def check_bundle_ref(self):
        if self.bundle_id is None and not self.bundle_slug:
            raise ValueError("Either bundle_id or bundle_slug is required")
        return self


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