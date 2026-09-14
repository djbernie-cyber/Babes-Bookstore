"""M-Pesa Daraja Business Pay To Pochi (B2Pochi) client.

Used to push refunds from the business B2C shortcode into a customer's
Pochi wallet. Unlike STK push there is no passkey: authentication is the
OAuth bearer token plus a pre-encrypted initiator ``SecurityCredential``.

Docs: ``POST {base}/mpesa/b2pochi/v1/paymentrequest``

Notes that matter operationally:
  * ``OriginatorConversationID`` must be unique per request — Daraja
    rejects duplicates, so it doubles as our idempotency key.
  * ``Amount`` is whole KES shillings, min 10, max 250,000.
  * The synchronous response only acknowledges *acceptance*; the outcome
    arrives later on ``ResultURL`` (see the b2pochi webhook).
  * OAuth tokens expire hourly — we always mint a fresh one per submission.
"""
import base64

import httpx
from fastapi import HTTPException

from ..config import settings


def _base_url() -> str:
    env = (settings.MPESA_ENVIRONMENT or "sandbox").lower()
    return "https://sandbox.safaricom.co.ke" if env == "sandbox" else "https://api.safaricom.co.ke"


def is_configured() -> bool:
    return bool(
        settings.MPESA_CONSUMER_KEY
        and settings.MPESA_CONSUMER_SECRET
        and settings.MPESA_B2C_SHORTCODE
        and settings.MPESA_B2C_INITIATOR_NAME
        and settings.MPESA_B2C_SECURITY_CREDENTIAL
    )


def _callback_url() -> str:
    return settings.MPESA_B2POCHI_CALLBACK_URL or (
        f"{settings.PRODUCTION_URL}/api/v1/checkout/webhook/b2pochi"
    )


async def mpesa_access_token() -> str:
    if not settings.MPESA_CONSUMER_KEY or not settings.MPESA_CONSUMER_SECRET:
        raise HTTPException(status_code=500, detail="M-Pesa not configured — set MPESA_CONSUMER_KEY/SECRET")
    creds = base64.b64encode(
        f"{settings.MPESA_CONSUMER_KEY}:{settings.MPESA_CONSUMER_SECRET}".encode()
    ).decode()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_base_url()}/oauth/v1/generate?grant_type=client_credentials",
            headers={"Authorization": f"Basic {creds}"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


def build_b2pochi_payload(refund, phone: str) -> dict:
    """Assemble the paymentrequest body for a Refund row.

    ``phone`` is the customer's mobile in 2547XXXXXXXX form (their Pochi
    wallet identifier).
    """
    callback = _callback_url()
    return {
        "OriginatorConversationID": refund.originator_conversation_id,
        "InitiatorName": settings.MPESA_B2C_INITIATOR_NAME,
        "SecurityCredential": settings.MPESA_B2C_SECURITY_CREDENTIAL,
        "CommandID": "BusinessPayToPochi",
        "Amount": int(refund.amount_cents),
        "PartyA": settings.MPESA_B2C_SHORTCODE,
        "PartyB": phone,
        "Remarks": f"Refund for purchase {refund.purchase_id}",
        "QueueTimeOutURL": callback,
        "ResultURL": callback,
        "Occassion": "Bookstore refund",
    }


async def submit_b2pochi(refund, phone: str) -> dict:
    """Submit a payout request. Returns Daraja's synchronous ack dict.

    Raises HTTPException on transport/HTTP failure so the caller can leave
    the refund PENDING and retry without losing the record.
    """
    if not is_configured():
        raise HTTPException(
            status_code=500,
            detail=(
                "M-Pesa B2Pochi not configured — set MPESA_B2C_SHORTCODE, "
                "MPESA_B2C_INITIATOR_NAME and MPESA_B2C_SECURITY_CREDENTIAL"
            ),
        )
    token = await mpesa_access_token()
    payload = build_b2pochi_payload(refund, phone)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_base_url()}/mpesa/b2pochi/v1/paymentrequest",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=502,
                    detail=f"Daraja B2Pochi error {resp.status_code}: {resp.text[:300]}",
                )
            data = resp.json()
    except HTTPException:
        raise
    except Exception as e:  # network/timeout/JSON — leave refund retryable
        raise HTTPException(status_code=502, detail=f"Daraja B2Pochi request failed: {e}")

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Unexpected Daraja B2Pochi response")
    return data