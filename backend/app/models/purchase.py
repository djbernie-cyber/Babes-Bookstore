from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class PurchaseStatus:
    """Single source of truth for purchase status values (stored as strings)."""

    PENDING = "pending"
    PAID = "paid"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class PaymentProvider:
    STRIPE = "stripe"
    PAYPAL = "paypal"
    SQUARE = "square"
    APPLE_PAY = "apple_pay"
    GOOGLE_PAY = "google_pay"
    MPESA = "mpesa"
    FREE = "free"


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    bundle_id = Column(Integer, ForeignKey("bundles.id"), nullable=False)

    # Payment provider info
    payment_provider = Column(String(20), default=PaymentProvider.STRIPE)

    # Stripe
    stripe_session_id = Column(String(200), nullable=True, index=True)
    stripe_payment_intent = Column(String(200), nullable=True, index=True)

    # PayPal
    paypal_order_id = Column(String(200), nullable=True, index=True)

    # Square
    square_order_id = Column(String(200), nullable=True, index=True)

    # M-Pesa
    mpesa_checkout_id = Column(String(200), nullable=True, index=True)
    customer_phone = Column(String(20), nullable=True)

    # Pricing
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(10), default="gbp")

    customer_email = Column(String(255), nullable=True)

    download_token = Column(String(64), unique=True, nullable=False, index=True)
    download_expires_at = Column(DateTime, nullable=True)
    download_count = Column(Integer, default=0)
    max_downloads = Column(Integer, default=5)

    status = Column(String(20), default=PurchaseStatus.PENDING)
    zip_path = Column(String(500), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="purchases")
    bundle = relationship("Bundle", back_populates="purchases")

    def __repr__(self):
        return f"<Purchase {self.id}: {self.customer_email} - {self.bundle_id}>"