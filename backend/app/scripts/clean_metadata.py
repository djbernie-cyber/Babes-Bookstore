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


# Two bare capitalised tokens, "London, Jack", where the second is a common
# given name: a reversal pass turned an already-natural name inside out.
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
    """Return the corrected author, or None to leave the record alone."""
    if not raw:
        return None
    a = raw.strip()
    m = TWO_TOKEN.match(a)
    if not m:
        return None
    first, second = m.group(1), m.group(2)
    if first.lower() in NOT_SURNAMES:
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
            if new_title != b.title or new_author:
                touched.append((b, new_title, new_author))

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
        # the failure mode the retag task already hit.
        CHUNK = 500
        for i in range(0, len(touched), CHUNK):
            async with AsyncSessionLocal() as wdb:
                for b, new_title, new_author in touched[i:i + CHUNK]:
                    if new_title != b.title:
                        b.title = new_title
                    if new_author:
                        b.author = new_author
                await wdb.commit()
            print(f"  wrote {min(i + CHUNK, len(touched)):,}/{len(touched):,}")

        print("\nAPPLIED.")


if __name__ == "__main__":
    asyncio.run(run("--apply" in sys.argv))
