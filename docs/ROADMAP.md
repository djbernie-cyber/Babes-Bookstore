# ROADMAP — outstanding work

Living document. Anything "pending" in the RFCs lands here as a checklist.
Ordered roughly by next-action value, not written order.

## Deploy / ops (do first)

- [ ] **Roll the worker machine** to the current image so `covers.backfill`
      (and any new Celery task registration) is live:
      `flyctl machines update 2873535a967e08 -a babes-bookstore -i registry.fly.io/babes-bookstore:deployment-01M377T7108R3R5PZ21JH68MPT --restart always --yes`
      (use `FLY_API_TOKEN` from `~/.fly/config.yml`; deploy from repo root).
- [ ] Verify app machine + migrations post-deploy; trigger a covers backfill
      and confirm the Military Library has 23/23 covers.
- [ ] Run seeders on prod (upload via `fly ssh console`):
      `/tmp/add_richest.py` → `seed_premium_bundles.py` → `seed_censorship.py`.
      Verify: foie gras bundle ~1000 books, Presidents bundle live, Richest Man
      + classics in the showcase, `/api/v1/banned/countries` populated.
- [ ] Deploy the censorship backend (migration `c1d2e3f4a5b6` + `/banned`
      routes) to app and worker; confirm the Illegal Books Catalog renders live.

## Product build pending

- [ ] Admin dashboard pages: `/admin` overview linking users, themes,
      censorship review (`/admin/banned-records`), site-config editor.
- [ ] Theme generator UI in the account area (RFC-003).
- [ ] Seasonal / Author-birthday homepage modules wired through `/themes/active`.
- [ ] Illegal Books: per-book "classified" page (all records for one book),
      and a `?uncensored=1` deep-link so OCR/ad-fragments can cite a banner
      without a separate page.
- [ ] Kindle list: EPUB download naming (`title - author.epub`) + a dedicated
      `/e` formats page for device instructions.

## Ergonomics (account / library)

- [ ] Fix `frontend/account/reset.html` (broken password reset flow).
- [ ] Empty-states for `my-library` / purchases / wishlist.
- [ ] `my-library.js`: move rename/delete/empty-shelf into the shelf header
      dropdown; expose progress resume tiles ("Continue reading").

## Bundles & shelves

- [ ] Verify premium bundles on prod; add a second "Forbidden Shelf" bundle
      seeded through the same censorship mechanism (jurisdiction + disclaimer).
- [ ] Artistic books / media catalogue surface (illustrated editions,
      periodicals) — decide scope before building.

## Audit (security P1s)

- [ ] JWT: move off default `SECRET_KEY` (`config.py:18-20`) to env at deploy.
- [ ] `get_current_user` should 401 — today it returns `None` and callers
      decide (`deps.py:26-43`).
- [ ] Mass-approve endpoints bypass licence checks (`admin.py:454-461,
      475-495`) — gate on `license_verified` before `approve-all`.

## Docs

- [ ] RFF-001 shelves/saves/reader feedback; RFF-002 censorship review
      workflow (open after 2 weeks of prod data).
- [ ] Fold output of RFFs back here; keep GO-LIVE-GUIDE.md current.