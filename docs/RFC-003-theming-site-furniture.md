# RFC-003 — Theming engine & "site furniture"

Status: **Backend deployed; account/admin UI pending** · 2026-09

## Problem

The storefront had a single hand-rolled identity: one dark hero, one light
canvas, one font feeling. "The Netflix of reading culture" needs personal
themes and holiday/locale dressing (site furniture), driven from a table, not
from find-and-replacing page HTML.

## Design

### Backend (`seasonal_theme.py` + `SiteConfig`)

- `SeasonalTheme`: `matches` (ISO country + locale + month window),
  `token` (unique name), `overrides` + `shelf_config` (JSON blobs of CSS
  variable/colour overrides and homepage shelf arrangement), plus
  `active` and priority for overlapping windows.
- `SiteConfig`: singleton of presentational settings — shelf layout order,
  featured bundle slugs, announcement line.
- Public API: `GET /themes/active` (resolves theme for a viewer's
  country/locale/month, falling back to base), `GET /themes`,
  `GET /themes/site-config`.
- Admin API (super-admin): CRUD `/admin/themes`, `GET/PUT /admin/site-config`.
- Per-user choice lives on `User.theme_prefs` (JSON) with `ALLOWED_THEME_KEYS`
  sanitisation through `PUT /auth/me`.

### Intended frontend surface (pending)

- **Theme generator** in the account area: pick base (light/dark/sepia),
  two accent colours, serif/sans headline preference → writes `theme_prefs`
  → the storefront applies it.
- **Seasonal dressing**: `theme.js` fetches `/themes/active` (honouring a
  stored user override) and applies colour/shelf overrides before paint —
  so Eid, Christmas, Author birthdays, loc=KE heritage rows just appear,
  no per-page plumbing.
- **Shelf furniture editor**: admin screen that writes `site-config`
  homepage shelf order + featured placements.

## Decisions

1. Overrides are **CSS-variable + config**, never page templates; a theme is
   data, not a copy of the homepage.
2. Resolution is server-authoritative (`/themes/active`), applied client-side
   before paint to avoid a flash; user overrides win.
3. Seasonal themes are countries/locales/months, and multiple may overlap —
   priority + explicit `active` resolve conflicts.

## Verification

- Migration + model tests pass (`test_seasonal_themes.py`, 5 cases).
- `PUT /auth/me` sanitises unknown `theme_prefs` keys.
- Deploy applies on app boot (alembic head).

## Files

- `backend/app/models/seasonal_theme.py`, migrations `b1c2d3e4f5a6`,
  `a1b2c3d4e5f7` (theme_prefs/locale)
- `backend/app/api/v1/themes.py`, `admin.py` CRUD
- Account/theme-generator + admin furniture UI: **pending** (see ROADMAP)