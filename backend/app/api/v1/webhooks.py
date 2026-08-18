import secrets
import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Header, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import stripe
import httpx

from .deps import get_db, get_current_user, require_admin
from ...models.bundle import Bundle
from ...models.purchase import Purchase
from ...models.user import User
from ...config import settings
from ...schemas.purchase import CheckoutRequest, CheckoutResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/checkout", tags=["checkout"])

STANDARD_PRICE = settings.STANDARD_PRICE_PENCE
CURRENCY = settings.CURRENCY

FRONTEND_URL = settings.FRONTEND_URL


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

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    stripe.api_key = settings.STRIPE_SECRET_KEY

    purchase = Purchase(
        bundle_id=bundle.id,
        user_id=current_user.id if current_user else None,
        customer_email=req.email,
        amount_cents=STANDARD_PRICE,
        currency=CURRENCY,
        download_token=secrets.token_urlsafe(32),
        status="pending",
        payment_provider="stripe",
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
                        "currency": CURRENCY,
                        "product_data": {
                            "name": bundle.name,
                            "description": bundle.description or f"{len(bundle.bundle_books)} books",
                        },
                        "unit_amount": STANDARD_PRICE,
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
    base = "https://api-m.sandbox.paypal.com" if settings.PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"
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

    if not settings.PAYPAL_CLIENT_ID:
        raise HTTPException(status_code=500, detail="PayPal not configured")

    purchase = Purchase(
        bundle_id=bundle.id,
        user_id=current_user.id if current_user else None,
        customer_email=req.email,
        amount_cents=STANDARD_PRICE,
        currency=CURRENCY,
        download_token=secrets.token_urlsafe(32),
        status="pending",
        payment_provider="paypal",
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)

    try:
        access_token = await _get_paypal_access_token()
        base = "https://api-m.sandbox.paypal.com" if settings.PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base}/v2/checkout/orders",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [
                        {
                            "amount": {
                                "currency_code": CURRENCY.upper(),
                                "value": f"{STANDARD_PRICE / 100:.2f}",
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

    if not settings.SQUARE_ACCESS_TOKEN:
        raise HTTPException(status_code=500, detail="Square not configured")

    purchase = Purchase(
        bundle_id=bundle.id,
        user_id=current_user.id if current_user else None,
        customer_email=req.email,
        amount_cents=STANDARD_PRICE,
        currency=CURRENCY,
        download_token=secrets.token_urlsafe(32),
        status="pending",
        payment_provider="square",
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)

    base_url = "https://connect.squareupsandbox.com" if settings.SQUARE_ENVIRONMENT == "sandbox" else "https://connect.squareup.com"

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
                                    "amount": STANDARD_PRICE,
                                    "currency": CURRENCY.upper(),
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
                                        "amount": STANDARD_PRICE,
                                        "currency": CURRENCY.upper(),
                                    },
                                }
                            ],
                            "pricing_options": {"auto_apply_taxes": True},
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

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    stripe.api_key = settings.STRIPE_SECRET_KEY

    purchase = Purchase(
        bundle_id=bundle.id,
        user_id=current_user.id if current_user else None,
        customer_email=req.email,
        amount_cents=STANDARD_PRICE,
        currency=CURRENCY,
        download_token=secrets.token_urlsafe(32),
        status="pending",
        payment_provider="apple_pay",
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)

    try:
        intent = stripe.PaymentIntent.create(
            amount=STANDARD_PRICE,
            currency=CURRENCY,
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

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    stripe.api_key = settings.STRIPE_SECRET_KEY

    purchase = Purchase(
        bundle_id=bundle.id,
        user_id=current_user.id if current_user else None,
        customer_email=req.email,
        amount_cents=STANDARD_PRICE,
        currency=CURRENCY,
        download_token=secrets.token_urlsafe(32),
        status="pending",
        payment_provider="google_pay",
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)

    try:
        intent = stripe.PaymentIntent.create(
            amount=STANDARD_PRICE,
            currency=CURRENCY,
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
    """Free download for admin users with free_downloads=True."""
    if not current_user or not (current_user.is_admin and current_user.free_downloads):
        raise HTTPException(status_code=403, detail="Free downloads not available for your account")

    bundle = await _resolve_bundle(req, db)
    _s, _c = _urls(req)

    purchase = Purchase(
        bundle_id=bundle.id,
        user_id=current_user.id,
        customer_email=current_user.email,
        amount_cents=0,
        currency=CURRENCY,
        download_token=secrets.token_urlsafe(32),
        status="completed",
        payment_provider="free",
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)

    from ...tasks.package_bundle import package_bundle_task
    package_bundle_task.delay(purchase.id)

    return CheckoutResponse(
        checkout_url=f"/account?purchase_id={purchase.id}&token={purchase.download_token}",
        session_id=f"free_{purchase.id}",
    )


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
            if purchase and purchase.status != "completed":
                purchase.stripe_payment_intent = obj.get("id")
                purchase.status = "paid"
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
        if purchase and purchase.status != "completed":
            purchase.status = "paid"
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
            if purchase and purchase.status != "completed":
                purchase.status = "paid"
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