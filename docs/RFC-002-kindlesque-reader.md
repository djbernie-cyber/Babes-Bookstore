# RFC-002 — Kindle-style reader ergonomics

Status: **Implemented** (frontend) · 2026-09

## Problem

The original reader was a single scroll of flat paragraphs: headings were
stripped by `tidy()`, there was no table of contents, no pagination, no way to
"read elsewhere", and font size topped out at three steps. "Vibecoded" would
have been generous.

## Design

### Chapters, not paragraphs

Text is parsed into **chapters** of **blocks** (`p` / `li` / `td` / `pre` /
`blockquote` / `img`). A recursive walker treats headings (`h1`–`h6`) as chapter
boundaries and block-level containers (`div`, `section`, `article`, tables)
recursively so text is never duplicated. Books without headings degrade to one
chapter.

### Two reading modes

- **Pages (default)** — real measured pagination: blocks are laid into an
  off-screen measuring column matching the reader's font size and width; pages
  split when the column exceeds the viewport height. Prev/next buttons, `.page-ind`
  ("Page 3 of 24 · Chapter 4 of 12"), arrow-key/`PageUp`/`PageDown`/`Home`/`End`
  navigation, and a 12-chapter TOC dropdown.
- **Scroll** — lazy chunked rendering with `h1` chapter markers; TOC jumps to a
  chapter and re-renders from there; back-to-top button.

### Progress = position, not just percent

Progress writes `{percent, position}`. Pages mode stores `c{i}:p:{j}`; scroll
mode stores `para-{n}`. On return, a pages-mode anchor resumes at the exact
page; percent feeds a top progress bar in both modes.

### Read elsewhere / export

Toolbar "⇩ Read elsewhere" opens a popover explaining device transfer (Kindle
accepts EPUB via "Send to Kindle" email; Calibre/USB otherwise) with a direct
download link to `/api/v1/books/{id}/download` (the existing source EPUB/PDF/TXT
endpoint — no new backend). Suppressed works must clear the same
`bb-spp-{id}` acknowledgment before the download link is armed.

### Preference hygiene

Font size now has 4 steps (s/m/l/xl) and themes 3 (sepia/light/dark). All sync
through `/api/v1/library/prefs` for signed-in users; **mode** stays local
(localStorage) since it is a device affordance, not an account setting.

## Decisions

1. Pagination is **measured per page-height and font size** — no magic constant
   "paragraphs per page", no CSS multi-column hacks; rebuilds on resize.
2. TOC is a `<select>` (works with the site CSP; no JS event juggling).
3. Keyboard navigation is enabled in pages mode only (scroll mode keeps native
   scrolling).
4. Mode choice is not synced to the account; reading position is.

## Verification

- Files parse clean (JSC/JXA syntax check).
- Manual matrix: size s/m/l/xl × pages/scroll × theme, TOC jumps, resume after
  reload (anchor), suppressed gate, export popover.

## Files

- `frontend/books/reader.html` (toolbar: TOC, mode toggle, A−/A/A+/A++,
  export popover, progress bar, pager)
- `frontend/js/reader.js` (full rewrite)
- `backend/app/api/v1/books.py` download endpoint (existing, reused)