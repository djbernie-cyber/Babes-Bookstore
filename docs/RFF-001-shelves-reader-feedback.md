# RFF-001 — Shelves, saves, reader feedback

Status: **Open** · 2026-09

## What we said we'd do

- Named user shelves created/renamed/deleted via the library API
  (`/api/v1/library/*`); wishlist is the default shelf.
- "Add to shelf" / "make a new shelf" dropdown on every book detail page.
- Reading progress (percent + anchor) with account sync and a
  continue-reading strip.

## What we'd now reconsider

1. **Wishlist / Saved conflation.** The wishlist endpoint and the default
   shelf are the same rows but two names in the UI. Does "Saved" belong on the
   account as a distinct default, and wishlist stay checkout-facing? Decide
   before building the account redesign.
2. **Progress anchor semantics.** Pages mode stores `c{i}:p:{j}`; scroll mode
   `para-{n}` is decorative (we don't resolve it). Either resolve para anchors
   or stop writing a position scroll mode can honor.
3. **Shelf book_count staleness** — the detail-page shelf dropdown shows counts
   from the list call; cheap to keep, but state they're "as of load".

## Open questions

- Should shelves be sortable / have cover-collage previews on the account page?
- Should "Continue reading" appear on the homepage for signed-in users
  (it already exists at `/library/continue-reading`)?

## Decided follow-ups

- Move into ROADMAP once prod shakes out: continue-reading tiles, account
  shelf redesign, resolve `para-` anchors.
- Two-week review date: after first production traffic.