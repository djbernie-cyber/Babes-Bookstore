# RFC-004 — Super-admin maintenance layer

Status: **Implemented (backend)**, UI pending · 2026-09

## Problem

Launch gave `williammajanja@gmail.com` an `is_admin` flag and nothing to do
with it that wasn't hand-cranked through the DB or the scrape endpoints. The
operator needs a real maintenance surface: add/remove admins, change user
roles and activation, reset passwords, and eyeball every future admin surface
the RFCs above rely on (themes, censorship review, site furniture).

## Design

### Model

- `User.is_superadmin` boolean. `is_admin` remains the *site operator* role;
  `is_superadmin` gates the maintenance/data-admin surface.
- Migrations `a1b2c3d4e5f6` (`is_superadmin` + promotes the launch account),
  `a1b2c3d4e5f7` (`theme_prefs`, `locale`).

### Dependency

`require_superadmin` in `api/v1/deps.py` — 403 for the signed-in-but-not-
super-admin, 401 anonymous, and it refuses to let a super-admin **demote or
deactivate themselves** (no lock-out foot-guns).

### API — user management (`admin.py`)

- `GET /admin/users` — paginated user list (role, activation, purchases,
  reviews, theme_prefs) for the operator dashboard.
- `POST /admin/users/{id}/role` — promote/demote `is_admin` / `is_superadmin`.
- `POST /admin/users/{id}/activation` — enable/disable an account.
- `POST /admin/users/{id}/password` — set a fresh password.

### Identity endpoints

`GET/PUT /auth/me` now round-trip `is_superadmin`, `theme_prefs`, `locale`;
`PUT /auth/me` is the sanctioned place for account/theme prefs (the older
ad-hoc `/library/prefs` reader preferences also continue to work).

## Decisions

1. Super-admin is **separate from admin**: an admin can approve books and run
   scrapes; a super-admin manages people and the data-admin surfaces
   (censorship review, themes, site config).
2. Self-demotion / self-deactivation is **hard-blocked server-side**.
3. Everything signs through the existing audit log (`log_action`).

## Verification

- pytest: role endpoints return 401/403/404 correctly; self-immolation blocked.
- Migrations applied on app boot; `williammajanja@gmail.com` verified
  super-admin post-deploy.

## Files

- `backend/app/models/user.py`, migrations `a1b2c3d4e5f6`,`a1b2c3d4e5f7`
- `backend/app/api/v1/deps.py` (`require_superadmin`), `auth.py` payloads
- `backend/app/api/v1/admin.py` (users CRUD)
- Pending: admin dashboard UI (`/admin` pages), "Manage users" screens