"""Regression tests for per-bundle pricing at checkout.

Covers the bug where every provider charged the global STANDARD_PRICE
(£10), regardless of what the bundle's price_cents actually was. That
silently undercharged any premium bundle and lost revenue on every sale.
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_amount_helper_returns_bundle_price():
    from app.api.v1.webhooks import _amount
    from app.models.bundle import Bundle

    cheap = Bundle(name="x", slug="x", price_cents=500)
    assert _amount(cheap) == 500

    premium = Bundle(name="x", slug="x", price_cents=2500)
    assert _amount(premium) == 2500


@pytest.mark.asyncio
async def test_amount_helper_falls_back_for_invalid():
    from app.api.v1.webhooks import _amount, STANDARD_PRICE
    from app.models.bundle import Bundle

    assert _amount(Bundle(name="x", slug="x", price_cents=None)) == STANDARD_PRICE
    assert _amount(Bundle(name="x", slug="x", price_cents=-5)) == STANDARD_PRICE


@pytest.mark.asyncio
async def test_currency_helper_uses_bundle_currency():
    from app.api.v1.webhooks import _currency
    from app.models.bundle import Bundle

    assert _currency(Bundle(name="x", slug="x", price_cents=10, currency="USD")) == "usd"
    assert _currency(Bundle(name="x", slug="x", price_cents=10, currency=None)) == "gbp"


@pytest.mark.asyncio
async def test_bundle_response_includes_currency(client, seeded):
    r = await client.get("/api/v1/bundles?featured=true")
    item = r.json()["items"][0]
    assert "currency" in item
    assert item["currency"] == "gbp"


@pytest.mark.asyncio
async def test_stripe_checkout_uses_bundle_price(client, db, seeded):
    """An admin's premium bundle must charge its own price, not £10."""
    from app.models.bundle import Bundle
    bun = seeded["bundle"]
    bun.price_cents = 2500
    await db.commit()

    fake_session = MagicMock()
    fake_session.url = "https://stripe.example/sess"
    fake_session.id = "cs_test_123"

    with patch("app.api.v1.webhooks.stripe.checkout.Session.create", return_value=fake_session) as create:
        r = await client.post(
            "/api/v1/checkout/stripe",
            json={"bundle_slug": bun.slug, "email": "buyer@example.com"},
        )

    assert r.status_code == 200, r.text
    call_kwargs = create.call_args.kwargs
    assert call_kwargs["line_items"][0]["price_data"]["unit_amount"] == 2500
    assert call_kwargs["line_items"][0]["price_data"]["currency"] == "gbp"

    # Purchase row must record the actual amount and the bundle's currency,
    # not the global defaults.
    from sqlalchemy import select
    from app.models.purchase import Purchase
    purchases = (await db.execute(select(Purchase))).scalars().all()
    assert len(purchases) == 1
    assert purchases[0].amount_cents == 2500
    assert purchases[0].currency == "GBP"


@pytest.mark.asyncio
async def test_stripe_checkout_uses_bundle_currency(client, db, seeded):
    """A USD bundle must charge in dollars, not pounds."""
    from app.models.bundle import Bundle
    bun = seeded["bundle"]
    bun.price_cents = 1500
    bun.currency = "usd"
    await db.commit()

    fake_session = MagicMock()
    fake_session.url = "https://stripe.example/sess"
    fake_session.id = "cs_test_456"

    with patch("app.api.v1.webhooks.stripe.checkout.Session.create", return_value=fake_session) as create:
        r = await client.post(
            "/api/v1/checkout/stripe",
            json={"bundle_slug": bun.slug, "email": "buyer@example.com"},
        )

    assert r.status_code == 200, r.text
    assert create.call_args.kwargs["line_items"][0]["price_data"]["currency"] == "usd"
    assert create.call_args.kwargs["line_items"][0]["price_data"]["unit_amount"] == 1500


@pytest.mark.asyncio
async def test_paypal_checkout_uses_bundle_price(client, db, seeded):
    from app.models.bundle import Bundle
    bun = seeded["bundle"]
    bun.price_cents = 1234
    bun.currency = "eur"
    await db.commit()

    fake_response = MagicMock()
    fake_response.json.return_value = {
        "id": "PAYID-123",
        "links": [{"rel": "approve", "href": "https://paypal.example/approve"}],
    }
    fake_response.raise_for_status = MagicMock()

    with patch("app.api.v1.webhooks._get_paypal_access_token", return_value="tok"), \
         patch("app.api.v1.webhooks.httpx.AsyncClient") as client_cls:
        instance = MagicMock()
        instance.__aenter__.return_value.post.return_value = fake_response
        instance.__aexit__.return_value = None
        client_cls.return_value = instance

        r = await client.post(
            "/api/v1/checkout/paypal",
            json={"bundle_slug": bun.slug, "email": "buyer@example.com"},
        )

    assert r.status_code == 200, r.text
    body = instance.__aenter__.return_value.post.call_args.kwargs["json"]
    assert body["purchase_units"][0]["amount"]["currency_code"] == "EUR"
    assert body["purchase_units"][0]["amount"]["value"] == "12.34"


@pytest.mark.asyncio
async def test_apple_pay_uses_bundle_price(client, db, seeded):
    from app.models.bundle import Bundle
    bun = seeded["bundle"]
    bun.price_cents = 2000
    await db.commit()

    fake_intent = MagicMock()
    fake_intent.id = "pi_test_789"
    fake_intent.client_secret = "cs_secret_789"

    with patch("app.api.v1.webhooks.stripe.PaymentIntent.create", return_value=fake_intent) as create:
        r = await client.post(
            "/api/v1/checkout/apple-pay",
            json={"bundle_slug": bun.slug, "email": "buyer@example.com"},
        )

    assert r.status_code == 200, r.text
    assert create.call_args.kwargs["amount"] == 2000


@pytest.mark.asyncio
async def test_bundle_price_change_only_reflects_at_next_checkout(client, db, seeded):
    """An old checkout keeps its original price when the bundle is later edited."""
    bun = seeded["bundle"]
    bun.price_cents = 1000
    await db.commit()

    # Free checkout of the original price.
    from app.services.security import hash_password
    from app.models.user import User
    admin = User(
        email="admin@example.com",
        hashed_password=hash_password("secret"),
        is_admin=True,
        free_downloads=True,
    )
    db.add(admin)
    await db.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    with patch("app.tasks.package_bundle.package_bundle_task.delay"):
        r = await client.post(
            "/api/v1/checkout/free",
            json={"bundle_slug": bun.slug, "email": "admin@example.com"},
            headers=auth,
        )
    assert r.status_code == 200, r.text

    # Now bump the price. The previous checkout row must not change.
    bun.price_cents = 5000
    await db.commit()

    from sqlalchemy import select
    from app.models.purchase import Purchase
    purchase = (await db.execute(select(Purchase))).scalars().first()
    assert purchase.amount_cents == 0  # free download, immutable