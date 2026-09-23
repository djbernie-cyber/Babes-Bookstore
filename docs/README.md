# RFC / RFF — Documents

Proposals and follow-up discussions for babesbooks.store. Each RFC states a
problem, the design, and explicit decisions; each RFF invites reconsideration
and records the decided follow-ups. Documents are numbered in the order they
were written, not in build order.

## Index

| Doc | Status | Topic |
|-----|--------|-------|
| RFC-001 — The William Majanja Illegal Books Catalog | Implemented (backend deployed); frontend live | Banned-books-by-country engine, disclaimers, flagging |
| RFC-002 — Kindle-style reader ergonomics | Implemented (frontend) | Chapter-aware reader, Pages/Scroll modes, export-to-device |
| RFC-003 — Theming engine & "site furniture" | Backend deployed; account/admin UI pending | Seasonal themes, site config, shelf layout, theme generator |
| RFC-004 — Super-admin maintenance layer | Implemented (backend) | User management, role/activation/password admin endpoints |
| RFF-001 — Shelves, saves & reader feedback | Open | Named-shelf UX, progress, export feedback |
| RFF-002 — Censorship review workflow | Open | Flag → verify/reject queue, source hygiene, jurisdiction framing |
| ROADMAP.md | Living | Outstanding work & launch checklist deltas |

## Writing new docs

- RFCs: concise problem statement, design sketch, decision records (status),
  and migration/verification notes.
- RFFs: "what we said we'd do, what we'd now change", open questions, and a
  short decided-follow-ups list that gets folded back into ROADMAP.md.