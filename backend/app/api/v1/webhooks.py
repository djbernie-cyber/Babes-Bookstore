import secrets
import logging
import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Header, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import stripe
import httpx

from .deps import get_db, get_current_user, require_admin
from ...models.bundle import Bundle
from ...models.purchase import Purchase, PurchaseStatus, PaymentProvider
from ...models.user import User
from ...config import settings
from ...schemas.purchase import CheckoutRequest, CheckoutResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/checkout", tags=["checkout"])

#: Fallback used only when a bundle has no price of its own.
STANDARD_PRICE = settings.STANDARD_PRICE_PENCE
CURRENCY = settings.CURRENCY

FRONTEND_URL = settings.FRONTEND_URL

PAYPAL_API_BASE = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "live": "https://api-m.paypal.com",
}
SQUARE_API_BASE = {
    "sandbox": "https://connect.squareupsandbox.com",
    "production": "https://connect.squareup.com",
}


def _paypal_base() -> str:
    mode = settings.PAYPAL_MODE if settings.PAYPAL_MODE in PAYPAL_API_BASE else "sandbox"
    return PAYPAL_API_BASE[mode]


def _square_base() -> str:
    env = settings.SQUARE_ENVIRONMENT if settings.SQUARE_ENVIRONMENT in SQUARE_API_BASE else "sandbox"
    return SQUARE_API_BASE[env]


def _amount(bundle: Bundle) -> int:
    """Authoritative charge amount, in the smallest currency unit.

    Always derived from the bundle record so an admin changing a bundle's
    price is actually reflected at checkout. Previously every provider
    charged the global standard price, so any bundle priced above £10 was
    undercharged and the difference was lost on every sale.
    """
    price = bundle.price_cents
    if price is None or price < 0:
        return STANDARD_PRICE
    return price


def _currency(bundle: Bundle) -> str:
    """Bundle currency, falling back to the configured default."""
    return (bundle.currency or CURRENCY).lower()


async def _resolve_bundle(req: CheckoutRequest, db: AsyncSession) -> Bundle:
    """Resolve a bundle by id or slug, with books eagerly loaded."""
    from sqlalchemy.orm import selectinload
    from ...models.bundle import BundleBook

    stmt = select(Bundle).options(
        selectinload(Bundle.bundle_books).selectinload(BundleBook.book)
    )
    if req.bundle_id is not None:
        stmt = stmt.where(Bundle.id == req.bundle_id)
    else:
        stmt = stmt.where(Bundle.slug == req.bundle_slug)

    bundle = (await db.execute(stmt)).unique().scalar_one_or_none()
    if not bundle or not bundle.active:
        raise HTTPException(status_code=404, detail="Bundle not found or inactive")
    return bundle


def _urls(req: CheckoutRequest) -> tuple[str, str]:
    """Resolve success/cancel URLs with sensible defaults."""
    success = req.success_url or f"{FRONTEND_URL}/account"
    cancel = req.cancel_url or f"{FRONTEND_URL}/bundles"
    return success, cancel


@router.get("/config")
async def get_checkout_config():
    """Return public payment config for the frontend."""
    return {
        "currency": CURRENCY,
        "currency_symbol": settings.CURRENCY_SYMBOL,
        "price_pence": STANDARD_PRICE,
        "price_display": f"{settings.CURRENCY_SYMBOL}{STANDARD_PRICE / 100:.2f}",
        "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "paypal_client_id": settings.PAYPAL_CLIENT_ID,
        "google_client_id": settings.GOOGLE_CLIENT_ID,
        "square_application_id": settings.SQUARE_ACCESS_TOKEN and settings.SQUARE_LOCATION_ID,
        "mpesa_enabled": bool(settings.MPESA_SHORTCODE and settings.MPESA_CONSUMER_KEY),
        "mpesa_shortcode": settings.MPESA_SHORTCODE,
        "mpesa_environment": settings.MPESA_ENVIRONMENT,
    }


# ─── STRIPE ────────────────────────────────────────────────────────────────


@router.post("/stripe", response_model=CheckoutResponse)
async def create_stripe_checkout(
    req: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    bundle = await _resolve_bundle(req, db)
    _s, _c = _urls(req)
    amount = _amount(bundle)
    currency = _currency(bundle)

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    stripe.api_key = settings.STRIPE_SECRET_KEY

    purchase = Purchase(
        bundle_id=bundle.id,
        user_id=current_user.id if current_user else None,
        customer_email=req.email,
        amount_cents=amount,
        currency=currency,
        download_token=secrets.token_urlsafe(32),
        status=PurchaseStatus.PENDING,
        payment_provider=PaymentProvider.STRIPE,
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            payment_method_options={
                "card": {
                    "request_three_d_secure": "automatic",
                },
            },
            line_items=[
                {
                    "price_data": {
                        "currency": currency,
                        "product_data": {
                            "name": bundle.name,
                            "description": bundle.description or f"{len(bundle.bundle_books)} books",
                        },
                        "unit_amount": amount,
                    },
                    "quantity": 1,
                }
            ],
            customer_email=req.email,
            mode="payment",
            success_url=f"{_s}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=_c,
            payment_intent_data={
                "metadata": {
                    "purchase_id": str(purchase.id),
                    "bundle_id": str(bundle.id),
                    "provider": "stripe",
                },
            },
            metadata={
                "purchase_id": str(purchase.id),
                "bundle_id": str(bundle.id),
            },
        )

        purchase.stripe_session_id = session.id
        await db.commit()

        return CheckoutResponse(
            checkout_url=session.url,
            session_id=session.id,
        )
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── PAYPAL ────────────────────────────────────────────────────────────────


async def _get_paypal_access_token() -> str:
    auth = (settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET)
    base = _paypal_base()
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{base}/v1/oauth2/token", auth=auth, data={"grant_type": "client_credentials"})
        resp.raise_for_status()
        return resp.json()["access_token"]


@router.post("/paypal", response_model=CheckoutResponse)
async def create_paypal_checkout(
    req: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    bundle = await _resolve_bundle(req, db)
    _s, _c = _urls(req)
    amount = _amount(bundle)
    currency = _currency(bundle)

    if not settings.PAYPAL_CLIENT_ID:
        raise HTTPException(status_code=500, detail="PayPal not configured")

    purchase = Purchase(
        bundle_id=bundle.id,
        user_id=current_user.id if current_user else None,
        customer_email=req.email,
        amount_cents=amount,
        currency=currency,
        download_token=secrets.token_urlsafe(32),
        status=PurchaseStatus.PENDING,
        payment_provider=PaymentProvider.PAYPAL,
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)

    try:
        access_token = await _get_paypal_access_token()
        base = _paypal_base()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base}/v2/checkout/orders",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [
                        {
                            "amount": {
                                "currency_code": currency.upper(),
                                "value": f"{amount / 100:.2f}",
                            },
                            "description": f"{bundle.name} — {len(bundle.bundle_books)} books",
                            "custom_id": str(purchase.id),
                        }
                    ],
                    "application_context": {
                        "return_url": f"{_s}?payment=paypal&purchase_id={purchase.id}",
                        "cancel_url": _c,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()

        approve_url = next(
            (link["href"] for link in data.get("links", []) if link.get("rel") == "approve"),
            None,
        )
        if not approve_url:
            raise HTTPException(status_code=500, detail="PayPal approval URL not found")

        purchase.paypal_order_id = data.get("id")
        await db.commit()

        return CheckoutResponse(checkout_url=approve_url, session_id=data.get("id", ""))
    except Exception as e:
        logger.error(f"PayPal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── SQUARE ─────────────────────────────────────────────────────────────────


@router.post("/square", response_model=CheckoutResponse)
async def create_square_checkout(
    req: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    bundle = await _resolve_bundle(req, db)
    _s, _c = _urls(req)
    amount = _amount(bundle)
    currency = _currency(bundle)

    if not settings.SQUARE_ACCESS_TOKEN:
        raise HTTPException(status_code=500, detail="Square not configured")

    purchase = Purchase(
        bundle_id=bundle.id,
        user_id=current_user.id if current_user else None,
        customer_email=req.email,
        amount_cents=amount,
        currency=currency,
        download_token=secrets.token_urlsafe(32),
        status=PurchaseStatus.PENDING,
        payment_provider=PaymentProvider.SQUARE,
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)

    base_url = _square_base()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base_url}/v2/online-checkouts",
                headers={
                    "Authorization": f"Bearer {settings.SQUARE_ACCESS_TOKEN}",
                    "Content-Type": "application/json",
                    "Square-Version": "2024-01-18",
                },
                json={
                    "idempotency_key": secrets.token_urlsafe(16),
                    "checkout": {
                        "location_id": settings.SQUARE_LOCATION_ID,
                        "line_items": [
                            {
                                "name": bundle.name,
                                "description": bundle.description or f"{len(bundle.bundle_books)} books",
                                "quantity": "1",
                                "pricing_options": {
                                    "enabled_recurring": False,
                                },
                                "base_price_money": {
                                    "amount": amount,
                                    "currency": currency.upper(),
                                },
                            }
                        ],
                        "order": {
                            "location_id": settings.SQUARE_LOCATION_ID,
                            "line_items": [
                                {
                                    "name": bundle.name,
                                    "description": bundle.description or f"{len(bundle.bundle_books)} books",
                                    "quantity": "1",
                                    "base_price_money": {
                                        "amount": amount,
                                        "currency": currency.upper(),
                                    },
                                }
                            ],
                            "pricing_options": {"auto_apply_taxes": False},
                        },
                        "redirect_url": f"{_s}?payment=square&purchase_id={purchase.id}",
                        "ask_for_shipping_address": False,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            checkout_url = data.get("checkout", {}).get("url")

            purchase.square_order_id = data.get("checkout", {}).get("id")
            await db.commit()

            return CheckoutResponse(checkout_url=checkout_url, session_id=data.get("checkout", {}).get("id", ""))
    except Exception as e:
        logger.error(f"Square error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── APPLE PAY (via Stripe) ────────────────────────────────────────────────


@router.post("/apple-pay")
async def create_apple_pay_session(
    req: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Apple Pay is handled client-side via Stripe. Return payment intent."""
    bundle = await _resolve_bundle(req, db)
    _s, _c = _urls(req)
    amount = _amount(bundle)
    currency = _currency(bundle)

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    stripe.api_key = settings.STRIPE_SECRET_KEY

    purchase = Purchase(
        bundle_id=bundle.id,
        user_id=current_user.id if current_user else None,
        customer_email=req.email,
        amount_cents=amount,
        currency=currency,
        download_token=secrets.token_urlsafe(32),
        status=PurchaseStatus.PENDING,
        payment_provider=PaymentProvider.APPLE_PAY,
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            statement_descriptor="BABES BOOKSTORE",
            metadata={
                "purchase_id": str(purchase.id),
                "bundle_id": str(bundle.id),
                "provider": "apple_pay",
            },
        )

        purchase.stripe_session_id = intent.id
        await db.commit()

        return {
            "client_secret": intent.client_secret,
            "purchase_id": purchase.id,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── GOOGLE PAY (via Stripe) ──────────────────────────────────────────────


@router.post("/google-pay")
async def create_google_pay_session(
    req: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Google Pay is handled client-side via Stripe. Return payment intent."""
    bundle = await _resolve_bundle(req, db)
    _s, _c = _urls(req)
    amount = _amount(bundle)
    currency = _currency(bundle)

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    stripe.api_key = settings.STRIPE_SECRET_KEY

    purchase = Purchase(
        bundle_id=bundle.id,
        user_id=current_user.id if current_user else None,
        customer_email=req.email,
        amount_cents=amount,
        currency=currency,
        download_token=secrets.token_urlsafe(32),
        status=PurchaseStatus.PENDING,
        payment_provider=PaymentProvider.GOOGLE_PAY,
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            statement_descriptor="BABES BOOKSTORE",
            metadata={
                "purchase_id": str(purchase.id),
                "bundle_id": str(bundle.id),
                "provider": "google_pay",
            },
        )

        purchase.stripe_session_id = intent.id
        await db.commit()

        return {
            "client_secret": intent.client_secret,
            "purchase_id": purchase.id,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── FREE DOWNLOAD (Admin) ───────────────────────────────────────────────────


@router.post("/free", response_model=CheckoutResponse)
async def create_free_checkout(
    req: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Payless checkout for any authenticated admin — any bundle, including custom.

    Any is_admin user may claim a free download (amount 0). The legacy
    free_downloads flag is still honoured but no longer required, so newly
    promoted admins are immediately eligible.
    """
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Free downloads are available to admin accounts only — contact support to be promoted")

    bundle = await _resolve_bundle(req, db)
    _s, _c = _urls(req)

    purchase = Purchase(
        bundle_id=bundle.id,
        user_id=current_user.id,
        customer_email=current_user.email,
        amount_cents=0,
        currency=_currency(bundle),
        download_token=secrets.token_urlsafe(32),
        status=PurchaseStatus.COMPLETED,
        payment_provider=PaymentProvider.FREE,
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)

    # Device download: try to package synchronously so the same device
    # that browsed can download immediately. Falls back to async worker.
    zip_key = None
    try:
        from sqlalchemy.orm import selectinload
        from ...models.bundle import BundleBook
        # Ensure bundle books are loaded for sync packaging
        await db.refresh(bundle, ["bundle_books"])
        # Try sync packaging (fast for 3-18 books, ~3-8s)
        from ...services.packaging import packaging
        from datetime import timedelta
        books = [bb.book for bb in bundle.bundle_books if bb.book and bb.book.status.value == "approved"]  # type: ignore
        if books:
            zip_key = packaging.create_bundle_zip(bundle, books)
            purchase.zip_path = zip_key
            purchase.download_expires_at = datetime.utcnow() + timedelta(hours=settings.DOWNLOAD_WINDOW_HOURS)
            await db.commit()
            logger.info("Free checkout sync-packaged bundle %s for purchase %s -> %s", bundle.slug, purchase.id, zip_key)
    except Exception as e:
        logger.warning("Sync packaging failed for free checkout %s, falling back to async: %s", purchase.id, e)
        try:
            from ...tasks.package_bundle import package_bundle_task
            package_bundle_task.delay(purchase.id)
        except Exception:
            pass
    else:
        # Also queue async as backup if sync didn't produce a file (e.g. no books)
        if not zip_key:
            try:
                from ...tasks.package_bundle import package_bundle_task
                package_bundle_task.delay(purchase.id)
            except Exception:
                pass

    # Return a same-device direct download URL when we have a zip, otherwise
    # fall back to the account page (frontend will poll).
    if zip_key:
        from ...services.storage import storage
        direct = storage.get_signed_url(zip_key, expires_in=settings.DOWNLOAD_WINDOW_HOURS * 3600)
        # direct is /api/v1/purchases/storage/... for local fallback, or presigned R2 URL
        return CheckoutResponse(
            checkout_url=direct or f"/account?purchase_id={purchase.id}&token={purchase.download_token}",
            session_id=f"free_{purchase.id}",
        )

    return CheckoutResponse(
        checkout_url=f"/account?purchase_id={purchase.id}&token={purchase.download_token}",
        session_id=f"free_{purchase.id}",
    )


# ─── M-PESA (Safaricom Daraja — mobile money) ────────────────────────────


def _mpesa_base() -> str:
    env = (settings.MPESA_ENVIRONMENT or "sandbox").lower()
    return "https://sandbox.safaricom.co.ke" if env == "sandbox" else "https://api.safaricom.co.ke"


async def _mpesa_access_token() -> str:
    if not settings.MPESA_CONSUMER_KEY or not settings.MPESA_CONSUMER_SECRET:
        raise HTTPException(status_code=500, detail="M-Pesa not configured — set MPESA_CONSUMER_KEY/SECRET")
    import base64 as _b64
    creds = f"{settings.MPESA_CONSUMER_KEY}:{settings.MPESA_CONSUMER_SECRET}"
    token = _b64.b64encode(creds.encode()).decode()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_mpesa_base()}/oauth/v1/generate?grant_type=client_credentials",
            headers={"Authorization": f"Basic {token}"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


@router.post("/mpesa", response_model=CheckoutResponse)
async def create_mpesa_checkout(
    req: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Initiate M-Pesa STK push — funds settle to your Daraja shortcode.

    Provide `phone` as 2547XXXXXXXX (Kenya) — we'll normalise 07xx → 2547xx.
    Amount is derived from the bundle price (GBP pence → KES). In sandbox
    the amount can be 1 KES for testing.
    """
    bundle = await _resolve_bundle(req, db)
    amount_cents = _amount(bundle)
    currency = _currency(bundle)

    # Validate M-Pesa config
    if not settings.MPESA_SHORTCODE or not settings.MPESA_PASSKEY:
        raise HTTPException(status_code=500, detail="M-Pesa not configured — set MPESA_SHORTCODE/PASSKEY")

    # Normalise phone: 07xx, 7xx, +2547xx → 2547xx
    raw_phone = (req.phone or "").strip().replace(" ", "").replace("-", "")
    if not raw_phone:
        raise HTTPException(status_code=400, detail="phone is required for M-Pesa (format 2547XXXXXXXX)")
    if raw_phone.startswith("+"):
        raw_phone = raw_phone[1:]
    if raw_phone.startswith("0"):
        raw_phone = "254" + raw_phone[1:]
    if raw_phone.startswith("7") and len(raw_phone) == 9:
        raw_phone = "254" + raw_phone
    if not raw_phone.startswith("254") or len(raw_phone) != 12:
        raise HTTPException(status_code=400, detail="Invalid M-Pesa phone — use 2547XXXXXXXX")

    # Convert GBP pence → KES (approx 1 GBP = 170 KES for display; sandbox allows 1)
    # Use bundle price in KES minor units (KES has no cents, so amount is shillings)
    kes_amount = max(1, int(round((amount_cents / 100) * 170)))
    # In sandbox, cap to 1 for easier testing if you prefer — remove this line in production
    # kes_amount = 1

    callback_url = settings.MPESA_CALLBACK_URL or f"{settings.PRODUCTION_URL}/api/v1/checkout/webhook/mpesa"

    purchase = Purchase(
        bundle_id=bundle.id,
        user_id=current_user.id if current_user else None,
        customer_email=req.email,
        customer_phone=raw_phone,
        amount_cents=amount_cents,
        currency=currency,
        download_token=secrets.token_urlsafe(32),
        status=PurchaseStatus.PENDING,
        payment_provider=PaymentProvider.MPESA,
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)

    # Daraja STK push
    try:
        import base64, datetime as _dt
        token = await _mpesa_access_token()
        timestamp = _dt.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        password = base64.b64encode(f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}".encode()).decode()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_mpesa_base()}/mpesa/stkpush/v1/processrequest",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "BusinessShortCode": settings.MPESA_SHORTCODE,
                    "Password": password,
                    "Timestamp": timestamp,
                    "TransactionType": "CustomerPayBillOnline",
                    "Amount": kes_amount,
                    "PartyA": raw_phone,
                    "PartyB": settings.MPESA_SHORTCODE,
                    "PhoneNumber": raw_phone,
                    "CallBackURL": callback_url,
                    "AccountReference": f"BABES-{bundle.id}-{purchase.id}",
                    "TransactionDesc": f"{bundle.name[:20]}",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        # Daraja returns CheckoutRequestID on success
        checkout_id = data.get("CheckoutRequestID") or data.get("MerchantRequestID") or ""
        purchase.mpesa_checkout_id = checkout_id
        await db.commit()
        # Frontend should poll /api/v1/purchases/{id} or wait for STK push on phone
        return CheckoutResponse(
            checkout_url=f"/account?purchase_id={purchase.id}&token={purchase.download_token}&mpesa=pending",
            session_id=checkout_id or f"mpesa_{purchase.id}",
        )
    except httpx.HTTPStatusError as e:
        logger.error("M-Pesa STK failed: %s %s", e.response.status_code, e.response.text)
        raise HTTPException(status_code=500, detail=f"M-Pesa STK push failed: {e.response.text[:200]}")
    except Exception as e:
        logger.error("M-Pesa error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/mpesa")
async def mpesa_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Safaricom callback — Body -> stkCallback -> ResultCode 0 = success."""
    try:
        body = await request.json()
    except Exception:
        return {"ResultCode": 1, "ResultDesc": "Invalid JSON"}

    try:
        stk = body.get("Body", {}).get("stkCallback", {})
        result_code = stk.get("ResultCode")
        checkout_id = stk.get("CheckoutRequestID")
        if not checkout_id:
            return {"ResultCode": 0, "ResultDesc": "Ignored — no CheckoutRequestID"}

        stmt = select(Purchase).where(Purchase.mpesa_checkout_id == checkout_id)
        purchase = (await db.execute(stmt)).scalar_one_or_none()
        if not purchase:
            logger.warning("M-Pesa callback for unknown CheckoutRequestID %s", checkout_id)
            return {"ResultCode": 0, "ResultDesc": "Unknown purchase"}

        if result_code == 0:
            purchase.status = PurchaseStatus.PAID
            # For M-Pesa we consider PAID → COMPLETED after packaging, but mark PAID now
            await db.commit()
            from ...tasks.package_bundle import package_bundle_task
            package_bundle_task.delay(purchase.id)
            # Optionally complete immediately for device download (packaging will set COMPLETED)
            # We leave status PAID so the worker will transition to COMPLETED
        else:
            purchase.status = PurchaseStatus.FAILED
            await db.commit()
            logger.info("M-Pesa payment failed for %s ResultCode %s", checkout_id, result_code)
    except Exception as e:
        logger.error("M-Pesa webhook error: %s", e)

    return {"ResultCode": 0, "ResultDesc": "Accepted"}


# ─── WEBHOOKS ──────────────────────────────────────────────────────────────


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if not settings.STRIPE_WEBHOOK_SECRET or not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    stripe.api_key = settings.STRIPE_SECRET_KEY
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] in ("checkout.session.completed", "payment_intent.succeeded"):
        obj = event["data"]["object"]
        purchase_id = obj.get("metadata", {}).get("purchase_id") or (
            await _find_purchase_by_session(obj.get("id") or obj.get("metadata", {}).get("stripe_session_id"), db)
        )

        if purchase_id:
            purchase = await db.get(Purchase, int(purchase_id))
            if purchase and purchase.status != PurchaseStatus.COMPLETED:
                purchase.stripe_payment_intent = obj.get("id")
                purchase.status = PurchaseStatus.PAID
                await db.commit()
                from ...tasks.package_bundle import package_bundle_task
                package_bundle_task.delay(purchase.id)

    return {"received": True}


@router.post("/webhook/paypal")
async def paypal_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not settings.PAYPAL_WEBHOOK_ID:
        return {"received": True}

    body = await request.json()
    event_type = body.get("event_type")

    if event_type == "CHECKOUT.ORDER.APPROVED":
        resource = body.get("resource", {})
        order_id = resource.get("id")
        stmt = select(Purchase).where(Purchase.paypal_order_id == order_id)
        purchase = (await db.execute(stmt)).scalar_one_or_none()
        if purchase and purchase.status != PurchaseStatus.COMPLETED:
            purchase.status = PurchaseStatus.PAID
            await db.commit()
            from ...tasks.package_bundle import package_bundle_task
            package_bundle_task.delay(purchase.id)

    return {"received": True}


@router.post("/webhook/square")
async def square_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    event_type = body.get("type")

    if event_type == "payment.completed":
        order_id = body.get("data", {}).get("object", {}).get("payment", {}).get("order_id")
        if order_id:
            stmt = select(Purchase).where(Purchase.square_order_id == order_id)
            purchase = (await db.execute(stmt)).scalar_one_or_none()
            if purchase and purchase.status != PurchaseStatus.COMPLETED:
                purchase.status = PurchaseStatus.PAID
                await db.commit()
                from ...tasks.package_bundle import package_bundle_task
                package_bundle_task.delay(purchase.id)

    return {"received": True}


async def _find_purchase_by_session(session_id, db):
    if not session_id:
        return None
    stmt = select(Purchase).where(Purchase.stripe_session_id == session_id)
    purchase = (await db.execute(stmt)).scalar_one_or_none()
    return str(purchase.id) if purchase else None