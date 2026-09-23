# ROADMAP — outstanding work

Living document. Anything "pending" in the RFCs lands here as a checklist.
Ordered roughly by next-action value, not written order.

## Deploy / ops

- [x] Worker rolled to the current image so `covers.backfill` and new Celery
      task registrations are live (`flyctl machines update 2873535a967e08 …`).
- [x] Seeders run on prod and verified: foie gras (~2700), Presidents (~5600),
      Richest Man id 87437, censorship 23 records (author-aware matcher,
      English-edition preference; all canonical picks verified on prod).
- [x] Censorship backend + `/banned` routes deployed; Illegal Books Catalog
      and Banned Works reference render live.
- [x] Banned Works reference list wired into the catalogue: Ibsen, Hardy,
      More, Shelley, Bierce, Gibran added to the banned-author sweep; the
      reference PD titles (Ghosts, Jude the Obscure, Utopia, Devil's
      Dictionary, The Prophet, Justine, …) tagged/ingested via
      `POST /api/v1/admin/scrape/suppressed-full`.
- [x] SECRET_KEY set via `fly secrets set` (base secret moved off the
      placeholder; config refuses the placeholder in non-DEBUG).
- [x] `get_current_user` now raises 401 (added `get_optional_user` for the
      anonymous-tolerant readers); bulk approve / approve-all gated on
      `license_verified`.

## Product build pending

- [x] Personalized home feed: `GET /api/v1/home/feed` (Continue reading,
      Picked for you from the reader's own shelves/progress/reviews, curated
      tag rows, seasonal band) + Netflix-style rows on `index.html`.
- [x] Admin banned-records review queue (`/admin/banned-records`).
- [x] `account/reset.html` fixed (CSP: inline script extracted to
      `/js/reset.js`; correct token storage + redirect).
- [ ] Theme generator UI in the account area (RFC-003).
- [ ] Seasonal / Author-birthday homepage modules wired through `/themes/active`
      (feed already surfaces the site-config `seasonal` band when set).
- [ ] Illegal Books: per-book "classified" page (all records for one book),
      and a `?uncensored=1` deep-link so OCR/ad-fragments can cite a banner
      without a separate page.
- [ ] Kindle list: EPUB download naming (`title - author.epub`) + a dedicated
      `/e` formats page for device instructions.

## Ergonomics (account / library)

- [ ] Empty-states for `my-library` / purchases / wishlist.
- [ ] `my-library.js`: move rename/delete/empty-shelf into the shelf header
      dropdown; expose progress resume tiles ("Continue reading").
- [ ] Admin dashboard: overview links already cover books/bundles/purchases/
      banned-records; add users + themes + site-config editors.

## Bundles & shelves

- [ ] Verify premium bundles on prod; add a second "Forbidden Shelf" bundle
      seeded through the same censorship mechanism (jurisdiction + disclaimer).
- [ ] Artistic books / media catalogue surface (illustrated editions,
      periodicals) — decide scope before building.

## Audit (security P1s)

- [x] JWT: base secret moved off the default (`config.py`) to the `fly
      secrets`-provided `SECRET_KEY`.
- [x] `get_current_user` now 401s; `get_optional_user` used where anonymous
      access is intentional.
- [x] Mass-approve endpoints gate on `license_verified` before approval.

## Docs

- [ ] RFF-001 shelves/saves/reader feedback; RFF-002 censorship review
      workflow (open after 2 weeks of prod data).
- [ ] Fold output of RFFs back here; keep GO-LIVE-GUIDE.md current.