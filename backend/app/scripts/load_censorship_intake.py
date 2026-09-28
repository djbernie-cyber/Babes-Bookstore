"""Load hand-transcribed suppression records from an intake file.

Separate from the harvester on purpose. Harvested rows are a machine reading
of a citable table and are marked ``provenance: harvested``; a transcribed row
is a person reading a primary source, so it is marked ``curated`` and carries
both a link and a print citation. Mixing the two would make the map's weakest
claims look like its strongest.
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.censorship import CensorshipRecord, CensorshipStatus

REQUIRED = ("work_title", "country_code", "ban_reason", "source_url", "citation")
#: CensorshipStatus is a plain class of string constants, not an Enum, so its
#: legal values are read off the class rather than iterated -- iterating it
#: raises TypeError, and hardcoding them here would let the two drift apart.
VALID_STATUS = {v for k, v in vars(CensorshipStatus).items()
                if not k.startswith("_") and isinstance(v, str)}


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def validate(rec, where):
    """Reject rows that would enter the archive as assertions.

    The point of a transcribed record is that it can be checked, so a missing
    citation is a hard error rather than a warning.
    """
    errs = [f"{where}: missing {f}" for f in REQUIRED if not (rec.get(f) or "").strip()]
    cc = (rec.get("country_code") or "").strip()
    if cc and (len(cc) != 2 or not cc.isalpha()):
        errs.append(f"{where}: country_code must be ISO 3166-1 alpha-2, got {cc!r}")
    st = (rec.get("status") or "banned").strip()
    if st not in VALID_STATUS:
        errs.append(f"{where}: status must be one of {sorted(VALID_STATUS)}, got {st!r}")
    if len(rec.get("ban_reason", "")) < 15:
        errs.append(f"{where}: ban_reason too short to be a documented reason")
    return errs


def _key(r):
    return (_norm(r.get("work_title")), (r.get("country_code") or "").upper(),
            _norm(r.get("banned_since")))


async def run(path, dry):
    doc = json.loads(Path(path).read_text())
    records = doc.get("records", [])
    if not records:
        print(f"{path}: no records to load")
        return 0

    errs = []
    for i, r in enumerate(records):
        errs += validate(r, f"records[{i}]")
    if errs:
        print("refusing to load — these rows are not citable:\n")
        for e in errs:
            print("  -", e)
        return 1

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(
            CensorshipRecord.work_title, CensorshipRecord.country_code,
            CensorshipRecord.banned_since))).fetchall()
        have = {(_norm(w), (c or "").upper(), _norm(y)) for w, c, y in rows}

        fresh, seen = [], set(have)
        for r in records:
            k = _key(r)
            if k in seen:
                continue
            seen.add(k)
            fresh.append(r)

        for r in fresh:
            print(f"  + [{r['country_code']}] {r['work_title'][:52]:54} "
                  f"{(r.get('banned_since') or ''):>10}  {r['citation'][:44]}")

        if dry:
            print(f"\nDRY RUN — {len(fresh)} would be inserted "
                  f"({len(records) - len(fresh)} already present)")
            return 0

        for r in fresh:
            db.add(CensorshipRecord(
                work_title=r["work_title"].strip()[:240],
                work_author=(r.get("work_author") or None) and r["work_author"][:180],
                work_year=r.get("work_year"),
                country_code=r["country_code"].strip().upper(),
                country_name=r.get("country_name") or r.get("subdivision"),
                status=(r.get("status") or "banned").strip(),
                ban_reason=r["ban_reason"].strip(),
                banned_since=r.get("banned_since"),
                source_url=r["source_url"].strip(),
                notes="; ".join(x for x in [
                    r.get("notes"), f"Citation: {r['citation']}"] if x),
                verified=True,
                verified_by="curated:transcribed",
            ))
        await db.commit()
        total = (await db.execute(
            select(func.count()).select_from(CensorshipRecord))).scalar()
        print(f"\ncommitted {len(fresh)}; archive now holds {total} records")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    sys.exit(asyncio.run(run(a.file, a.dry)))
