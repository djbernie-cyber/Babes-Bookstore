# Censorship record intake

Machine-harvested records come from `app/scripts/harvest_censorship.py`.
Records that need a human reading a primary source come through here instead,
because a transcribed record carries a different and stronger claim: someone
checked the page.

## What to send, per record

```json
{
  "work_title":    "required — the work as the source names it",
  "work_author":   "author or null",
  "work_year":     "year of publication, as a string, or null",
  "country_code":  "required — ISO 3166-1 alpha-2. KE / UG / TZ. 'X' only for transnational",
  "country_name":  "display name, e.g. 'Kenya (British East Africa)'",
  "subdivision":   "optional — province/region, e.g. 'Nyanza', 'Zanzibar'",
  "status":        "banned | restricted | contested",
  "banned_since":  "free text as the source gives it, e.g. '1926' or '1948–1952'",
  "ban_reason":    "required — the documented reason, in the source's own terms",
  "source_url":    "required — stable link to the page you read",
  "citation":      "required — gazette name + issue/page, or archive reference",
  "notes":         "optional — anything a reader should know"
}
```

`source_url` and `citation` are both required. A record without a locatable
source is an assertion, and the archive is built on the difference between the
two.

## Sources that work

- *Kenya Gazette*, *Uganda Gazette*, *Tanganyika Gazette*, *Zanzibar Gazette* —
  notices of prohibited publications.
- India Office Records, Kew (`IOR` class marks) — correspondence on press
  control.
- The British administrations' official "List of Prohibited / Immoral Books"
  circulated to colonies.
- Hansard and colony debating-council Hansard — questions put in the legislature.

## Loading

    python -m app.scripts.load_censorship_intake --file censorship_intake/<name>.json
    python -m app.scripts.load_censorship_intake --file <name>.json --dry

Idempotent on `(work_title, country_code, banned_since)`, same as the harvester,
so re-sending a corrected file updates in place instead of duplicating.
