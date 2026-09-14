"""M-Pesa (Daraja STK-push) callback hardening tests.

Daraja callbacks are unsigned, so the webhook must be strict about payload
shape, reject non-numeric result codes, and never create a payment — only
complete purchases we already created as PENDING.
"""
import pytest
from unittest.mock import patch
from sqlalchemy import select

from app.models.purchase import Purchase, PurchaseStatus, PaymentProvider


def _bump(stk: dict) -> dict:
    return {"Body": {"stkCallback": stk}}


@pytest.mark.asyncio
async def test_invalid_json_returns_error(client):
    r = await client.post(
        "/api/v1/checkout/webhook/mpesa",
        content="not json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json()["ResultCode"] == 1


@pytest.mark.asyncio
async def test_non_mapping_body_rejected(client):
    r = await client.post(
        "/api/v1/checkout/webhook/mpesa",
        json=[1, 2, 3],
    )
    assert r.json()["ResultCode"] == 1


@pytest.mark.asyncio
async def test_missing_checkout_id_ignored(client):
    r = await client.post(
        "/api/v1/checkout/webhook/mpesa",
        json=_bump({"ResultCode": 0}),
    )
    assert r.json()["ResultCode"] == 0
    assert "no CheckoutRequestID" in r.json()["ResultDesc"]


@pytest.mark.asyncio
async def test_non_numeric_result_code_rejected(client):
    r = await client.post(
        "/api/v1/checkout/webhook/mpesa",
        json=_bump({"ResultCode": "SUCCESS", "CheckoutRequestID": "WS123"}),
    )
    assert r.json()["ResultCode"] == 1
    assert "Invalid ResultCode" in r.json()["ResultDesc"]


@pytest.mark.asyncio
async def test_unknown_purchase_ignored(client):
    r = await client.post(
        "/api/v1/checkout/webhook/mpesa",
        json=_bump({"ResultCode": 0, "CheckoutRequestID": "UNKNOWN-1"}),
    )
    assert r.json()["ResultCode"] == 0
    assert "Unknown purchase" in r.json()["ResultDesc"]


@pytest.mark.asyncio
async def test_success_completes_existing_pending_purchase(client, db, seeded):
    bundle = seeded["bundle"]
    purchase = Purchase(
        bundle_id=bundle.id,
        customer_email="kenya@example.com",
        customer_phone="254700000000",
        amount_cents=100,
        currency="kes",
        download_token="tok",
        status=PurchaseStatus.PENDING,
        payment_provider=PaymentProvider.MPESA,
        mpesa_checkout_id="WS_CO_202609140000001",
    )
    db.add(purchase)
    await db.commit()

    with patch("app.tasks.package_bundle.package_bundle_task.delay") as delay:
        r = await client.post(
            "/api/v1/checkout/webhook/mpesa",
            json=_bump({"ResultCode": 0, "CheckoutRequestID": "WS_CO_202609140000001"}),
        )

    assert r.json()["ResultCode"] == 0
    delay.assert_called_once()
    await db.refresh(purchase)
    assert purchase.status == PurchaseStatus.PAID


@pytest.mark.asyncio
async def test_failure_marks_purchase_failed(client, db, seeded):
    bundle = seeded["bundle"]
    purchase = Purchase(
        bundle_id=bundle.id,
        customer_email="kenya@example.com",
        amount_cents=100,
        currency="kes",
        download_token="tok",
        status=PurchaseStatus.PENDING,
        payment_provider=PaymentProvider.MPESA,
        mpesa_checkout_id="WS_CO_202609140000002",
    )
    db.add(purchase)
    await db.commit()

    r = await client.post(
        "/api/v1/checkout/webhook/mpesa",
        json=_bump({"ResultCode": 1032, "CheckoutRequestID": "WS_CO_202609140000002"}),
    )

    assert r.json()["ResultCode"] == 0
    await db.refresh(purchase)
    assert purchase.status == PurchaseStatus.FAILED