"""Auth, admin seeding, and free-download authorization tests."""
import pytest


@pytest.mark.asyncio
async def test_register_and_login(client):
    r = await client.post("/api/v1/auth/register", json={
        "email": "reader@example.com", "password": "s3cret-pass", "name": "Reader",
    })
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert token
    assert r.json()["user"]["is_admin"] is False

    r2 = await client.post("/api/v1/auth/login", json={
        "email": "reader@example.com", "password": "s3cret-pass",
    })
    assert r2.status_code == 200
    assert r2.json()["access_token"]


@pytest.mark.asyncio
async def test_duplicate_registration_rejected(client):
    payload = {"email": "dupe@example.com", "password": "s3cret-pass"}
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 200
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 400


@pytest.mark.asyncio
async def test_login_with_wrong_password_rejected(client):
    await client.post("/api/v1/auth/register", json={
        "email": "wrong@example.com", "password": "correct-pass",
    })
    r = await client.post("/api/v1/auth/login", json={
        "email": "wrong@example.com", "password": "bad-pass",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_oauth_only_user_cannot_login_with_blank_password(client, db):
    """Regression: a Google-only user has hashed_password=None."""
    from app.models.user import User
    db.add(User(email="google@example.com", name="G", google_id="gid-1"))
    await db.commit()

    r = await client.post("/api/v1/auth/login", json={
        "email": "google@example.com", "password": "",
    })
    assert r.status_code in (401, 422)


@pytest.mark.asyncio
async def test_me_requires_authentication(client):
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_me_returns_profile(client):
    reg = await client.post("/api/v1/auth/register", json={
        "email": "me@example.com", "password": "s3cret-pass", "name": "Me",
    })
    token = reg.json()["access_token"]
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_admin_endpoint_blocked_for_anonymous(client):
    assert (await client.get("/api/v1/admin/stats")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_endpoint_blocked_for_normal_user(client):
    reg = await client.post("/api/v1/auth/register", json={
        "email": "normal@example.com", "password": "s3cret-pass",
    })
    token = reg.json()["access_token"]
    r = await client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_emails_are_configured():
    """Both requested accounts must be present in config."""
    from app.config import settings

    assert "williammajanja@gmail.com" in settings.ADMIN_EMAILS
    assert "dj.bernie@hotmail.co.uk" in settings.ADMIN_EMAILS


@pytest.mark.asyncio
async def test_admin_seeding_grants_admin_and_free_downloads(session_factory):
    """Seeding must create each configured admin with free downloads."""
    from app.config import settings
    from app.models.user import User
    from app.main import _seed_admin_users
    from sqlalchemy import select

    await _seed_admin_users(session_factory)

    async with session_factory() as s:
        for email in settings.ADMIN_EMAILS:
            u = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
            assert u is not None, f"{email} was not seeded"
            assert u.is_admin is True
            assert u.free_downloads is True


@pytest.mark.asyncio
async def test_admin_seeding_is_idempotent(session_factory):
    """Re-running seeding must not create duplicates."""
    from app.config import settings
    from app.models.user import User
    from app.main import _seed_admin_users
    from sqlalchemy import select, func

    await _seed_admin_users(session_factory)
    await _seed_admin_users(session_factory)

    async with session_factory() as s:
        count = (await s.execute(
            select(func.count(User.id)).where(User.email.in_(settings.ADMIN_EMAILS))
        )).scalar()
        assert count == len(settings.ADMIN_EMAILS)


@pytest.mark.asyncio
async def test_seeding_promotes_existing_user_to_admin(session_factory):
    """A pre-existing account that later appears in ADMIN_EMAILS is promoted."""
    from app.models.user import User
    from app.main import _seed_admin_users
    from sqlalchemy import select

    async with session_factory() as s:
        s.add(User(email="williammajanja@gmail.com", name="Will",
                   is_admin=False, free_downloads=False))
        await s.commit()

    await _seed_admin_users(session_factory)

    async with session_factory() as s:
        u = (await s.execute(
            select(User).where(User.email == "williammajanja@gmail.com")
        )).scalar_one()
        assert u.is_admin is True
        assert u.free_downloads is True


@pytest.mark.asyncio
async def test_free_checkout_denied_for_anonymous(client, seeded):
    r = await client.post("/api/v1/checkout/free", json={
        "bundle_slug": "classic-literature", "email": "x@example.com",
    })
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_free_checkout_denied_for_normal_user(client, seeded):
    """A paying customer must not be able to claim free downloads."""
    reg = await client.post("/api/v1/auth/register", json={
        "email": "cheapskate@example.com", "password": "s3cret-pass",
    })
    token = reg.json()["access_token"]
    r = await client.post(
        "/api/v1/checkout/free",
        json={"bundle_slug": "classic-literature", "email": "cheapskate@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
