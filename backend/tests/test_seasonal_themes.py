"""Unit tests for the seasonal/holiday theming resolver + super-admin model.

Pure logic only (no network, no DB): theme liveness over holiday windows,
locale/country matching priority, and the User.is_superadmin flag.
"""
from datetime import datetime

from app.api.v1.themes import _theme_live, _parse_json
from app.models.seasonal_theme import SeasonalTheme
from app.models.user import User


def _theme(**kw):
    defaults = dict(
        id=1, name="Test", slug="test", locale="all", is_default=False, active=True,
        starts_at=None, ends_at=None, overrides=None, shelf_config=None,
    )
    defaults.update(kw)
    t = SeasonalTheme(**defaults)
    return t


def test_theme_live_respects_window():
    now = datetime(2026, 12, 24, 12, 0, 0)
    xmas = _theme(
        starts_at=datetime(2026, 12, 1), ends_at=datetime(2027, 1, 1),
    )
    assert _theme_live(xmas, now) is True
    assert _theme_live(xmas, datetime(2026, 7, 1, 12, 0, 0)) is False


def test_theme_live_respects_active_flag():
    off = _theme(active=False)
    assert _theme_live(off) is False


def test_default_theme_always_live():
    default = _theme(is_default=True)
    assert _theme_live(default) is True


def test_parse_json_tolerates_bad_input():
    assert _parse_json(None) == {}
    assert _parse_json("not json") == {}
    assert _parse_json('{"accent":"#8a2414"}') == {"accent": "#8a2414"}


def test_user_has_superadmin_flag():
    u = User(email="a@b.c")
    assert u.is_superadmin in (None, False)
    u.is_superadmin = True
    assert u.is_superadmin is True