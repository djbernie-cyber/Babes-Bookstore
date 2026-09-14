"""M-Pesa B2Pochi payout (refund) records.

A refund reverses a completed M-Pesa purchase by paying the customer's
Pochi wallet from the business B2C shortcode via Daraja's
``mpesa/b2pochi/v1/paymentrequest`` endpoint. Daraja callbacks are not
cryptographically signed, so the webhook only transitions refunds WE
created that are still awaiting settlement — it never creates money.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from ..database import Base


class RefundStatus:
    PENDING = "pending"            # created, awaiting submission (or retry)
    PROCESSING = "processing"      # submitted to Daraja, awaiting callback
    SUCCEEDED = "succeeded"        # ResultCode 0 — money dispatched
    FAILED = "failed"              # Daraja rejected or final non-zero code


class Refund(Base):
    __tablename__ = "refunds"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=False, index=True)

    # Amount settled to the Pochi wallet (KES shillings — KES has no cents).
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(10), default="kes")

    originator_conversation_id = Column(String(100), nullable=True, unique=True, index=True)
    conversation_id = Column(String(100), nullable=True, index=True)
    transaction_id = Column(String(100), nullable=True)
    customer_phone = Column(String(20), nullable=True)

    status = Column(String(20), default=RefundStatus.PENDING, index=True)
    result_code = Column(String(20), nullable=True)
    result_desc = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def is_terminal(self) -> bool:
        return self.status in (RefundStatus.SUCCEEDED, RefundStatus.FAILED)