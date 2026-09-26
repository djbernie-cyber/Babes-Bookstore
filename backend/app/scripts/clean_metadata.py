"""Clean catalogue metadata in place.

    python /app/app/scripts/clean_metadata.py --dry-run
    python /app/app/scripts/clean_metadata.py --apply

Three defects, all visible on the storefront:

1. MARC subfield codes leaked into titles. Gutenberg's 245 field encodes the
   main title as ``$a`` and everything after as ``$b``, so titles arrived as
   ``"A military dictionary : $b or, Explanation of the several systems"``.
   The ingestor also hard-truncated at 500 characters, leaving ~4.8k titles
   ending mid-word. Codes are stripped, whitespace repaired, and runaway
   titles are cut back at a clause or word boundary.

2. The "African literature" shelf led with colonial adventure novels. The
   retag pass deliberately tags COLONIAL_AUTHORS with ``African Literature``
   (plus ``Colonial Sauce``) so empire-framing works stay visible -- so this
   is fixed in the shelf query, not by rewriting tags. Untagging here would
   simply be undone by the next ``retag.african_literature`` run, which
   recomputes the tag from the author every time.

3. A name-reversal pass mangled a few hundred authors into "London, Jack"
   instead of "Jack London". Only the provably-wrong two-token cases are
   corrected; genuine "Surname, Given" library records are left alone,
   because that is a legitimate catalogue convention, not a defect.
"""
import asyncio
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.book import Book, BookStatus

# "$a", "$b", ": $b", " ; $c" -- drop the code, keep the words around it.
MARC_CODE = re.compile(r"(?:(?<=\s)|^|[:;])\$[A-Za-z0-9]")
# Leftover punctuation scaffolding once the codes are gone.
JUNK = [
    (re.compile(r"\s*:\s*:\s*"), ": "),
    (re.compile(r"\s+([:;,])"), r" \1"),
    (re.compile(r"\(\s*\)"), ""),
    (re.compile(r"\s{2,}"), " "),
    (re.compile(r"\s+([.?!:;])"), r"\1"),
]
MAX_TITLE = 200
# Prefer cutting at a real clause boundary before falling back to a word.
CLAUSE = re.compile(r"^(.{40,MAX})(?=\s[:;—]\s|\.\s)")


def clean_title(raw: str) -> str:
    if not raw:
        return raw
    t = raw
    for _ in range(3):                      # codes can sit next to each other
        t = MARC_CODE.sub(" ", t)
    for pat, rep in JUNK:
        t = pat.sub(rep, t)
    t = t.strip().strip("-—:;, ")
    if len(t) <= MAX_TITLE:
        return t
    m = CLAUSE.match(t)
    cut = m.group(1) if m else None
    if not cut or len(cut) < 40:
        cut = t[:MAX_TITLE].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-—") + "…"


# A place name in the surname slot. Gutenberg's "London, Jack" is Jack
# London reversed by a name-normalisation pass; "Dickens, Charles" is a
# perfectly good library record. The two are structurally identical, so the
# only sound discriminator is that one of them starts with a city.
PLACE_TOKENS = {
    "london", "paris", "york", "new york", "oxford", "cambridge", "edinburgh",
    "dublin", "berlin", "vienna", "madrid", "rome", "liverpool", "manchester",
    "glasgow", "aberdeen", "boston", "chicago", "toronto", "montreal",
    "sydney", "melbourne", "cape town", "lagos", "accra", "nairobi",
    "johannesburg", "harlem", "buenos aires",
}
# Two bare capitalised tokens, "London, Jack", where the second is a common
# given name.
TWO_TOKEN = re.compile(r"^([A-Z][\w'’-]+),\s+([A-Z][\w'’-]+)$")
GIVEN_NAMES = {
    "jack", "john", "james", "robert", "henry", "george", "charles", "thomas",
    "william", "edward", "mary", "elizabeth", "frederick", "arthur", "harold",
    "walter", "herbert", "francis", "alice", "emma", "charlotte", "victoria",
    "nicholas", "samuel", "benjamin", "daniel", "michael", "peter", "paul",
    "andrew", "richard", "patrick", "donald", "douglas", "roger", "ralph",
    "edmund", "albert", "caroline", "harriet", "dorothy", "agnes", "vera",
}
# Words that are surnames but read as given names; reversing these is wrong.
NOT_SURNAMES = {"psalms", "proverbs", "ecclesiastes", "genesis", "exodus"}


def clean_author(raw: str):
    """Return the corrected author, or None to leave the record alone.

    Deliberately narrow. 9,106 approved rows are stored as "Surname, Given",
    which is standard library practice and which readers of a catalogue
    expect; rewriting all of them to natural order would churn ~8.9k author
    strings and their pages for a formatting preference. Only records whose
    surname slot holds a place name -- the fingerprint of the reversal bug --
    are corrected.
    """
    if not raw:
        return None
    a = raw.strip()
    m = TWO_TOKEN.match(a)
    if not m:
        return None
    first, second = m.group(1), m.group(2)
    if first.lower() in NOT_SURNAMES:
        return None
    if first.lower() not in PLACE_TOKENS:
        return None
    if second.lower() not in GIVEN_NAMES:
        return None
    return f"{second} {first}"


async def run(apply: bool) -> None:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Book).where(Book.status == BookStatus.APPROVED).order_by(Book.id)
        )).scalars().all()
        print(f"scanning {len(rows):,} approved books (apply={apply})\n")

        t_fixed = a_fixed = 0
        samples = {"title": [], "author": []}
        touched = []

        for b in rows:
            new_title = clean_title(b.title or "")
            new_author = clean_author(b.author or "")

            if new_title != b.title:
                t_fixed += 1
                if len(samples["title"]) < 8:
                    samples["title"].append((b.id, b.title, new_title))
            if new_author:
                a_fixed += 1
                if len(samples["author"]) < 8:
                    samples["author"].append((b.id, b.author, new_author))
            # Store primitives, never ORM objects: holding Book instances
            # across sessions and committing a different one silently
            # persists nothing while still reporting success.
            if new_title != b.title or new_author:
                touched.append((b.id, new_title if new_title != b.title else None, new_author))

        print(f"titles cleaned          : {t_fixed:,}")
        print(f"authors un-reversed     : {a_fixed:,}")
        print(f"rows to write           : {len(touched):,}\n")

        for i, (bid, old, new) in enumerate(samples["title"]):
            print(f"TITLE #{bid}\n  - {old[:150]!r}\n  + {new!r}")
        print()
        for i, (bid, old, new) in enumerate(samples["author"]):
            print(f"AUTHOR #{bid}\n  - {old!r}\n  + {new!r}")
        print()

        if not apply:
            print("DRY RUN -- nothing written. Re-run with --apply.")
            return

        # Write in chunks so one huge transaction cannot time out the proxy,
        # the failure mode the retag task already hit. Each chunk re-fetches
        # its rows in the writing session so the mutated objects are actually
        # attached to it.
        CHUNK = 500
        written = 0
        for i in range(0, len(touched), CHUNK):
            chunk = touched[i:i + CHUNK]
            ids = [t[0] for t in chunk]
            async with AsyncSessionLocal() as wdb:
                books = (await wdb.execute(
                    select(Book).where(Book.id.in_(ids))
                )).scalars().all()
                by_id = {b.id: b for b in books}
                for bid, new_title, new_author in chunk:
                    b = by_id.get(bid)
                    if b is None:
                        continue
                    if new_title is not None:
                        b.title = new_title
                    if new_author is not None:
                        b.author = new_author
                await wdb.commit()
            written += len(chunk)
            print(f"  wrote {written:,}/{len(touched):,}")

        # Read the rows back in a fresh session. A commit that reports success
        # without changing anything is the exact failure this script already
        # suffered once, so verify rather than trust.
        async with AsyncSessionLocal() as vdb:
            check_ids = [t[0] for t in touched[:50]]
            after = {b.id: b for b in (await vdb.execute(
                select(Book).where(Book.id.in_(check_ids))
            )).scalars().all()}
            stuck = []
            for bid, new_title, new_author in touched[:50]:
                b = after.get(bid)
                if b is None:
                    stuck.append((bid, "row missing"))
                    continue
                if new_title is not None and b.title != new_title:
                    stuck.append((bid, f"title still {b.title[:60]!r}"))
                if new_author is not None and b.author != new_author:
                    stuck.append((bid, f"author still {b.author!r}"))

        if stuck:
            print(f"\nVERIFY FAILED -- {len(stuck)} of 50 sampled rows did not persist:")
            for bid, why in stuck[:10]:
                print(f"  #{bid}: {why}")
            sys.exit(1)
        print(f"\nVERIFIED: {min(50, len(touched))} sampled rows read back clean.")
        print("APPLIED.")


if __name__ == "__main__":
    asyncio.run(run("--apply" in sys.argv))
