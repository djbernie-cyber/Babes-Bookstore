# RFC-001 — The William Majanja Illegal Books Catalog

Status: **Implemented** · Backend + frontend + seed data · 2026-09

## Problem

The store opened claiming "we keep the record of censorship because a bookstore
is only honest if it refuses to flinch." The static `banned-works.html` page was
a curated reference list, but it had no data layer: it could not answer "what
was banned in country X", could not grow from reader submissions, and leaned on
hardcoded prose rather than verified records.

## Design

### Data model — `censorship_records`

A `CensorshipRecord` is attached to a **catalogued, approved, licence-verified**
book (the `banned-works` reference page can keep documenting in-print titles;
the *catalog* only links to books readers can actually read here).

- `book_id` → `Book`; `country_code` (ISO 3166-1 alpha-2); `country_name`.
- `status`: `banned` | `restricted` | `contested`.
- `ban_reason` (why it was suppressed); `banned_since`; `source_url`.
- Trust flow: `verified=false` until a super-admin verifies; `proposed_by`
  (user id) recorded on flags, cleared on verification; `verified_by`
  stamped as `verified:<admin_id>`.
- Written by the seeder as a fact sheet; readers can only *flag* — they cannot
  publish records directly.

### API — `/api/v1/banned/*`

Public (no auth):
- `GET /banned/records` — verified records joined to the approved book;
  filters `country` (alpha-2), `status`, `q` (title/author).
- `GET /banned/countries` — per-country rollups for the filter dropdown.
- `GET /banned/books/{id}` — all records for one book.

Auth required:
- `POST /banned/books/{id}/flag` — propose a country/status/reason for a book.
  Idempotent per (book, country); a verified pair returns 409.

Super-admin only (`/admin/banned-records`):
- List pending flags, `POST /{id}/review` (`verify`/`reject`), `DELETE`.

### Frontend — `illegal-books.html`

Dark-stone page with:
- A **cookie-based disclaimer gate** (`bb-illegal-ack`) shown once per device:
  "babesbooks.store is a tool and an archive of information... users are
  responsible for the laws of their own jurisdiction."
- Country / status / text filters backed by the API (no hardcoded rows).
- Cards grouped by country showing the suppression reason; "Read / Download"
  links into the catalogue, "Flag in another country" opens an inline form.
- A "Where to read these, legally" strip pointing at Project Gutenberg,
  Wikisource and the Internet Archive **public** collections.

### Content boundary (decision)

The catalog documents bans and links **legal, public-domain** editions only.
Deliberately NOT wired: mirror/pirate sites (PDFdrive et al.), region-locked
copies, or any "help me circumvent my jurisdiction" affordance. The disclaimer
repeats this framing in the user's face, on every visit.

## Decisions

1. **Records require a catalogue book.** In-print / uncatalogued bans live on
   the static reference page, not the catalog rows.
2. **Flagging ≠ publishing.** Reader flags land unverified behind a
   super-admin review queue; the seeder is the only verified-data writer.
3. **Login required to flag** (friction + auditability); **no login required to
   read the catalog** (no pressure on readers in censoring jurisdictions).
4. **No jurisdiction prompts.** Nobody guesses your country; the gate is a
   self-acknowledged disclaimer, not a geo-block.
5. Seeder is **idempotent** by `(book_id, country_code)` so re-runs are safe.

## Verification

- `pytest` suite passes with censorship tests (records, countries, review
  flow, 404/401/409 paths).
- Seed script re-runnable; unknown titles skipped with a logged note.
- Manual: `/banned/countries`, `/banned/records?country=US` over the API on
  prod after deployment.

## Files

- `backend/app/models/censorship.py`, migration `c1d2e3f4a5b6`
- `backend/app/api/v1/censorship.py`
- `backend/app/scripts/seed_censorship.py`
- `frontend/illegal-books.html`, `frontend/js/illegal-books.js`
- Homepage nav / footer / explore-card links