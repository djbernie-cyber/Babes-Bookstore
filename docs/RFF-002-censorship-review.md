# RFF-002 — Censorship review workflow

Status: **Open** · 2026-09

## What we said we'd do

- Verified-only records surface publicly; reader flags land unverified behind
  a super-admin review queue (`verify` / `reject` / delete).
- Seeder is the only bulk writer; idempotent by `(book, country)`.
- The catalog never links to pirate sources and repeats jurisdictional
  disclaimer framing.

## What we'd now reconsider

1. **Flag spam surface.** `/banned/books/{id}/flag` is open to any logged-in
   user with no rate limit. Two weeks of prod data will tell whether queued
   garbage outruns the admin review screen; if so, restrict flags to
   `provenance` = a URL or ISBN evidence field (currently free-text only).
2. **Provenance.** `ban_reason` carries fact; `source_url` exists but the
   flag form doesn't send one. Add an evidence field that flattens to
   `source_url` at verify time.
3. **Status drift.** A book can be `banned` in one country and freely printed
   in another — the card already shows country, but a per-book "elsewhere"
   summary would help. `GET /banned/books/{id}` exists; surface it on the
   book detail page.
4. **Jurisdiction framing.** The gate repeats the "you are responsible for
   your own jurisdiction" line — keep it, but never turn it into a geo-block
   (a reader in a censoring country must not be routed around).

## Open questions

- Should super-admins get a "trusted flags" throttle instead of a public
  review queue?
- Is `contested` (unproven but historically cited) too broad to ship publicly,
  or exactly the catalogue's point?

## Decided follow-ups

- Add evidence (`source_url`) to the flag form.
- Surface per-book records on `books/detail.html` via `/banned/books/{id}`.
- Two-week review date: after first production traffic.