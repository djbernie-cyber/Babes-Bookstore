from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
from datetime import datetime

from .deps import get_db
from ...models.seasonal_theme import SeasonalTheme, SiteConfig
from ...models.bundle import Bundle

router = APIRouter(prefix="/themes", tags=["themes"])


def _parse_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _theme_dict(t: SeasonalTheme) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "locale": t.locale,
        "country_code": t.country_code,
        "starts_at": t.starts_at.isoformat() if t.starts_at else None,
        "ends_at": t.ends_at.isoformat() if t.ends_at else None,
        "is_default": t.is_default,
        "overrides": _parse_json(t.overrides),
        "shelf_config": _parse_json(t.shelf_config),
    }


def _theme_live(t: SeasonalTheme, now: datetime | None = None) -> bool:
    now = now or datetime.utcnow()
    if not t.active:
        return False
    if t.starts_at and now < t.starts_at:
        return False
    if t.ends_at and now > t.ends_at:
        return False
    return True


@router.get("/active")
async def get_active_themes(
    locale: str = "all",
    country_code: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Themes currently live for the requesting reader, most specific first
    (locale match → country match → global default). Merged overrides are keyed
    so the frontend can layer personal theme → seasonal theme → scheme."""
    rows = (await db.execute(select(SeasonalTheme))).scalars().all()
    now = datetime.utcnow()

    def rank(t: SeasonalTheme) -> int:
        if t.locale not in ("", "all") and t.locale.lower() == (locale or "all").lower():
            return 0
        if t.country_code and t.country_code.upper() == (country_code or "").upper():
            return 1
        if t.is_default:
            return 2
        return 3

    live = [t for t in rows if _theme_live(t, now)]
    live.sort(key=rank)

    merged: dict = {}
    for t in live:
        merged.update(_parse_json(t.overrides))

    return {
        "themes": [_theme_dict(t) for t in live],
        "merged_overrides": merged,
        "requested": {"locale": locale, "country_code": country_code},
    }


@router.get("")
async def list_public_themes(db: AsyncSession = Depends(get_db)):
    """A browseable gallery of human-curated seasonal looks (holidays, Author
    Birthday showcases, library 'seasons') for the homepage/theme picker."""
    rows = (await db.execute(select(SeasonalTheme).where(SeasonalTheme.active == True))).scalars().all()
    return {"items": [_theme_dict(t) for t in rows]}


@router.get("/site-config")
async def get_site_config(db: AsyncSession = Depends(get_db)):
    """Admin-arranged shelf layout (the 'site furniture') plus the featured
    bundle ids so the homepage can render shelves in the arranged order."""
    cfg = (await db.execute(select(SiteConfig).where(SiteConfig.id == 1))).scalar_one_or_none()
    furniture = _parse_json(cfg.furniture) if cfg else {}
    featured_ids = furniture.get("featured_bundle_ids") if isinstance(furniture, dict) else None

    bundles = {}
    if featured_ids:
        rows = (await db.execute(select(Bundle).where(Bundle.id.in_(featured_ids)))).scalars().all()
        bundles = {b.id: {"id": b.id, "title": b.title, "slug": b.slug} for b in rows}

    return {"furniture": furniture, "featured_bundles": bundles}