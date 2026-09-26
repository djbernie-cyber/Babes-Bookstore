"""Report on catalogue metadata hygiene. Read-only.

    python /app/app/scripts/audit_metadata_hygiene.py
    python /app/app/scripts/audit_metadata_hygiene.py --samples 20

Counts the defect classes that make the storefront look broken: MARC
subfield codes leaking into titles, runaway subtitle/boilerplate titles,
"Last, First" authors that were reversed when they were already in natural
order, and books shelved under a tag they do not belong to.
"""
import asyncio
import re
import sys
from collections import Counter

sys.path.insert(0, "/app")

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.book import Book, BookStatus

# MARC subfield delimiters: $A $B $C $N $P $D ... and the ": $b" variant.
MARC_CODE = re.compile(r"(?:^|\s|[:;])\$[A-Za-z0-9]")
LONG_TITLE = 120
# "London, Jack" -- two single tokens, second one capitalised. A real
# "Last, First" has the surname first and usually a given name or initials
# after it, so two bare single tokens is the shape a naive reversal creates.
TWO_TOKEN_COMMA = re.compile(r"^([A-Z][\w'’-]+),\s+([A-Z][\w'’-]+)$")
# "Lloyd, Henry Demarest" -- surname, then two or more given-name tokens.
FULL_REVERSED = re.compile(r"^([A-Z][\w'’-]+),\s+([A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+)*)$")

KNOWN_GIVEN_NAMES = {
    "jack", "john", "james", "robert", "henry", "george", "charles", "thomas",
    "william", "edward", "mary", "elizabeth", "frederick", "arthur", "harold",
    "walter", "herbert", "francis", "alice", "emma", "charlotte", "victoria",
    "nicholas", "samuel", "benjamin", "daniel", "michael", "peter", "paul",
}


async def main(samples: int) -> None:
    async with AsyncSessionLocal() as db:
        approved = (await db.execute(
            select(func.count()).select_from(Book)
            .where(Book.status == BookStatus.APPROVED)
        )).scalar_one()
        print(f"approved books: {approved:,}\n")

        rows = (await db.execute(
            select(Book.id, Book.title, Book.author, Book.category, Book.source, Book.tags)
            .where(Book.status == BookStatus.APPROVED)
        )).all()
        print(f"scanned {len(rows):,} approved rows\n")

        marc, long_t, two_tok, full_rev = [], [], [], []
        for b in rows:
            t = b.title or ""
            a = (b.author or "").strip()
            if MARC_CODE.search(t):
                marc.append(b)
            if len(t) > LONG_TITLE:
                long_t.append(b)
            m = TWO_TOKEN_COMMA.match(a)
            if m and m.group(2).lower() in KNOWN_GIVEN_NAMES:
                two_tok.append(b)
            elif FULL_REVERSED.match(a):
                full_rev.append(b)

        def pct(n):
            return f"{n:,} ({100*n/max(len(rows),1):.2f}%)"

        print("DEFECT COUNTS")
        print(f"  MARC subfield codes in title : {pct(len(marc))}")
        print(f"  titles > {LONG_TITLE} chars            : {pct(len(long_t))}")
        print(f"  author reversed, bare given   : {pct(len(two_tok))}")
        print(f"  author 'Last, First' form     : {pct(len(full_rev))}")
        print()

        def show(label, items, key=lambda b: f"{b.title!r} / {b.author!r}"):
            print(f"--- {label} ({len(items)}) ---")
            for b in items[:samples]:
                print(f"  #{b.id} [{b.source}] {key(b)}")
            print()

        show("MARC codes in title", marc)
        show("overlong titles", sorted(long_t, key=lambda b: -len(b.title or "")),
             key=lambda b: f"len={len(b.title or '')} {(b.title or '')[:150]!r}")
        show("reversed author (bare given name)", two_tok)

        # Douglas: shelved as African literature but an American abolitionist.
        doug = [b for b in rows
                if b.tags and "African Literature" in (b.tags or [])
                and "douglass" in (b.author or "").lower()]
        african_total = [b for b in rows if b.tags and "African Literature" in (b.tags or [])]
        print(f"--- African Literature shelf ---")
        print(f"  total tagged: {len(african_total):,}")
        print(f"  authored by Douglass: {len(doug):,}")
        print("  top authors on this shelf:")
        for a, n in Counter(b.author for b in african_total).most_common(12):
            print(f"    {n:5,}  {a}")
        print()

        print("--- longest titles overall ---")
        for b in sorted(rows, key=lambda b: -len(b.title or ""))[:samples]:
            print(f"  #{b.id} len={len(b.title or ''):4} {(b.title or '')[:170]!r}")
        print()

        print("--- author field shapes ---")
        empty = sum(1 for b in rows if not (b.author or "").strip())
        print(f"  empty author: {empty:,}")
        for a, n in Counter(b.author for b in rows).most_common(15):
            print(f"    {n:6,}  {a!r}")


if __name__ == "__main__":
    samples = 20
    if "--samples" in sys.argv:
        samples = int(sys.argv[sys.argv.index("--samples") + 1])
    asyncio.run(main(samples))
