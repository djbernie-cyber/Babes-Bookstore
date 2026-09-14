"""M-Pesa B2Pochi payout (refund) tests.

Covers the unsigned-callback hardening on /checkout/webhook/b2pochi and the
admin refund endpoint that initiates a payout. Daraja itself is stubbed —
no live credentials are required.
"""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.purchase import Purchase, PurchaseStatus, PaymentProvider
from app.models.refund import Refund, RefundStatus
from app.services.security import hash_password


async def _make_admin(db):
    from app.models.user import User
    admin = User(email="refund-admin@example.com", hashed_password=hash_password("pw"),
                 is_admin=True, is_active=True)
    db.add(admin)
    await db.commit()
    return admin


async def _login(client):
    r = await client.post("/api/v1/auth/login",
                          json={"email": "refund-admin@example.com", "password": "pw"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _paid_purchase(db, bundle, phone="254700000000"):
    purchase = Purchase(
        bundle_id=bundle.id,
        customer_email="kenya@example.com",
        customer_phone=phone,
        amount_cents=1000,
        currency="kes",
        download_token=f"tok-refund-{phone}",
        status=PurchaseStatus.PAID,
        payment_provider=PaymentProvider.MPESA,
        mpesa_checkout_id=f"WS_REFUND_{phone}",
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)
    return purchase


def _result(**over) -> dict:
    result = {
        "ResultType": 0,
        "ResultCode": 0,
        "ResultDesc": "The service request is processed successfully.",
        "OriginatorConversationID": "BBREF-1-1",
        "ConversationID": "AG_20260914_0001",
        "TransactionID": "TRX-1",
        "ResultParameters": {"ResultParameter": [
            {"Key": "TransactionReceipt", "Value": "REC123"},
            {"Key": "TransactionAmount", "Value": 1700},
        ]},
    }
    result.update(over)
    return {"Result": result}


# ── webhook hardening ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_json_returns_error(client):
    r = await client.post("/api/v1/checkout/webhook/b2pochi",
                          content="not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    assert r.json()["ResultCode"] == 1


@pytest.mark.asyncio
async def test_missing_originator_id_ignored(client):
    r = await client.post("/api/v1/checkout/webhook/b2pochi",
                          json=_result(OriginatorConversationID=""))
    assert r.json()["ResultCode"] == 0
    assert "no OriginatorConversationID" in r.json()["ResultDesc"]


@pytest.mark.asyncio
async def test_non_numeric_result_code_rejected(client):
    r = await client.post("/api/v1/checkout/webhook/b2pochi",
                          json=_result(ResultCode="OK"))
    assert r.json()["ResultCode"] == 1
    assert "Invalid ResultCode" in r.json()["ResultDesc"]


@pytest.mark.asyncio
async def test_unknown_refund_ignored(client):
    r = await client.post("/api/v1/checkout/webhook/b2pochi",
                          json=_result(OriginatorConversationID="NOPE-1"))
    assert r.json()["ResultCode"] == 0
    assert "Unknown refund" in r.json()["ResultDesc"]


@pytest.mark.asyncio
async def test_success_marks_refund_succeeded(client, db, seeded):
    purchase = await _paid_purchase(db, seeded["bundle"])
    refund = Refund(purchase_id=purchase.id, amount_cents=1700, currency="kes",
                    status=RefundStatus.PROCESSING,
                    originator_conversation_id="BBREF-1-1")
    db.add(refund)
    await db.commit()

    r = await client.post("/api/v1/checkout/webhook/b2pochi", json=_result())
    assert r.json()["ResultCode"] == 0

    await db.refresh(refund)
    assert refund.status == RefundStatus.SUCCEEDED
    assert refund.transaction_id == "REC123"
    assert refund.conversation_id == "AG_20260914_0001"


@pytest.mark.asyncio
async def test_failure_marks_refund_failed(client, db, seeded):
    purchase = await _paid_purchase(db, seeded["bundle"])
    refund = Refund(purchase_id=purchase.id, amount_cents=1700, currency="kes",
                    status=RefundStatus.PROCESSING,
                    originator_conversation_id="BBREF-1-1")
    db.add(refund)
    await db.commit()

    r = await client.post("/api/v1/checkout/webhook/b2pochi",
                          json=_result(ResultCode=2001, ResultDesc="Request not permitted"))
    assert r.json()["ResultCode"] == 0

    await db.refresh(refund)
    assert refund.status == RefundStatus.FAILED
    assert refund.result_code == "2001"


@pytest.mark.asyncio
async def test_terminal_refund_not_re_transitioned(client, db, seeded):
    purchase = await _paid_purchase(db, seeded["bundle"])
    refund = Refund(purchase_id=purchase.id, amount_cents=1700, currency="kes",
                    status=RefundStatus.SUCCEEDED,
                    originator_conversation_id="BBREF-1-1")
    db.add(refund)
    await db.commit()

    r = await client.post("/api/v1/checkout/webhook/b2pochi",
                          json=_result(ResultCode=2001, ResultDesc="late failure"))
    assert "Already settled" in r.json()["ResultDesc"]
    await db.refresh(refund)
    assert refund.status == RefundStatus.SUCCEEDED


# ── admin refund endpoint ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refund_requires_admin(client, db, seeded):
    purchase = await _paid_purchase(db, seeded["bundle"])
    r = await client.post(f"/api/v1/admin/purchases/{purchase.id}/refund")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_refund_submits_b2pochi(client, db, seeded):
    await _make_admin(db)
    headers = await _login(client)
    purchase = await _paid_purchase(db, seeded["bundle"])

    ack = {"ConversationID": "AG_999", "OriginatorConversationID": "x",
           "ResponseCode": "0", "ResponseDescription": "Accepted"}
    with patch("app.services.mpesa_b2c.submit_b2pochi", new=AsyncMock(return_value=ack)):
        r = await client.post(f"/api/v1/admin/purchases/{purchase.id}/refund", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == RefundStatus.PROCESSING
    assert body["conversation_id"] == "AG_999"
    # 1000 pence GBP -> 10.00 * 170 = 1700 KES
    assert body["amount"] == 1700
    assert body["originator_conversation_id"].startswith(f"BBREF-{purchase.id}-")

    # a duplicate attempt is refused while one is in flight
    r2 = await client.post(f"/api/v1/admin/purchases/{purchase.id}/refund", headers=headers)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_refund_rejects_non_mpesa(client, db, seeded):
    await _make_admin(db)
    headers = await _login(client)
    purchase = await _paid_purchase(db, seeded["bundle"])
    purchase.payment_provider = PaymentProvider.STRIPE
    await db.commit()

    r = await client.post(f"/api/v1/admin/purchases/{purchase.id}/refund", headers=headers)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_refund_rejects_unpaid(client, db, seeded):
    await _make_admin(db)
    headers = await _login(client)
    purchase = await _paid_purchase(db, seeded["bundle"])
    purchase.status = PurchaseStatus.PENDING
    await db.commit()

    r = await client.post(f"/api/v1/admin/purchases/{purchase.id}/refund", headers=headers)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_refund_unknown_purchase_404(client, db):
    await _make_admin(db)
    headers = await _login(client)
    r = await client.post("/api/v1/admin/purchases/999999/refund", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_refund_rejected_by_daraja_marked_failed(client, db, seeded):
    await _make_admin(db)
    headers = await _login(client)
    purchase = await _paid_purchase(db, seeded["bundle"])

    ack = {"ResponseCode": "1", "ResponseDescription": "Insufficient balance"}
    with patch("app.services.mpesa_b2c.submit_b2pochi", new=AsyncMock(return_value=ack)):
        r = await client.post(f"/api/v1/admin/purchases/{purchase.id}/refund", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == RefundStatus.FAILED
    assert r.json()["result_code"] == "1"