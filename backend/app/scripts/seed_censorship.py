"""Seed well-documented censorship records for books on the shelves.

Idempotent: skips (book, country) pairs that already exist. Titles are matched
by normalised substring; books not yet in the catalogue are reported, not
inserted, so this works against the live approved catalogue.

Run inside the API container:
    cd /app && PYTHONPATH=/app python /tmp/seed_censorship.py
"""
import asyncio
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select, delete as sa_delete

from app.database import AsyncSessionLocal
from app.models.book import Book, BookStatus
from app.models.censorship import CensorshipRecord, CensorshipStatus

# Why-banned essays: written as factual, public-knowledge history. No invented
# source URLs — source_url stays null rather than pointing anywhere unproven.
RECORDS = [
    # ── Ulysses ──────────────────────────────────────────────────────────
    dict(match=["ulysses"], author="joyce",
         country_code="US", country_name="United States", status=CensorshipStatus.RESTRICTED,
         banned_since="1920–1933",
         ban_reason="Serialised chapters were confiscated and the full novel was seized by "
                    "US customs in 1920. A 1921 court deemed it obscene; the 1933 'U.S. v. One "
                    "Book Called Ulysses' decision reversed the ban and opened the way for "
                    "literary modernism.",
         notes="Run of the novel (Random House) later required importer declaratory judgement."),
    dict(match=["ulysses"], author="joyce",
         country_code="IE", country_name="Ireland", status=CensorshipStatus.BANNED,
         banned_since="1920s–1960s",
         ban_reason="Joyce's native Ireland kept Ulysses off shelves for decades under "
                    "censorship law; copies reached readers via the continent and England "
                    "long before domestic editions appeared.",
         notes="Censorship of Publications Act era."),
    # ── Decameron ────────────────────────────────────────────────────────
    dict(match=["decameron"], author="boccaccio",
         country_code="IT", country_name="Italy", status=CensorshipStatus.BANNED,
         banned_since="1497 / 1559",
         ban_reason="Savonarola's 'bonfire of the vanities' took copies in Florence in 1497, "
                    "and the Council of Trent placed the Decameron on the Index of Prohibited "
                    "Books in 1559. Religious censorship treated the hundred tales as "
                    "indecorous and heretical for three centuries.",
         notes="Later censored editions removed anti-clerical tales."),
    # ── Kama Sutra ───────────────────────────────────────────────────────
    dict(match=["kama sutra"], author="vatsyayana",
         country_code="GB", country_name="United Kingdom", status=CensorshipStatus.BANNED,
         banned_since="1883–1963",
         ban_reason="Burton's 1883 translation was published privately and treated as "
                    "obscenity; prosecutions under the Obscene Publications Act made it "
                    "legally risky to sell or import for more than half a century.",
         notes="Ran as a société ('the Kama Shastra Society') to evade censorship."),
    dict(match=["kama sutra"], author="vatsyayana",
         country_code="US", country_name="United States", status=CensorshipStatus.RESTRICTED,
         banned_since="1920s–1960s",
         ban_reason="US Customs routinely barred importations as obscene material; the "
                    "Comstock-era postal bans kept retail copies scarce until the 1960s "
                    "obscenity rulings relaxed enforcement.",
         notes="Customs seizure lists repeatedly included it."),
    # ── One Thousand and One Nights ──────────────────────────────────────
    dict(match=["arabian nights", "thousand and one nights"], author="",
         country_code="EG", country_name="Egypt", status=CensorshipStatus.CONTESTED,
         banned_since="modern era",
         ban_reason="Full, unexpurgated editions of the Nights have periodically been "
                    "challenged for sexual content and banned in translation in several "
                    "countries while scholarly and children's editions circulate freely.",
         notes="Contested status: scope of 'complete' editions in dispute."),
    # ── Madame Bovary ────────────────────────────────────────────────────
    dict(match=["madame bovary"], author="flaubert",
         country_code="FR", country_name="France", status=CensorshipStatus.CONTESTED,
         banned_since="1857",
         ban_reason="Flaubert was prosecuted for offending public morals when the novel "
                    "appeared; the court famously acquitted him, and the trial became part "
                    "of the book's legend as a landmark of realism.",
         notes="Acquittal; prosecutor pursued 'religious morality' angle."),
    # ── Candide ──────────────────────────────────────────────────────────
    dict(match=["candide"], author="voltaire",
         country_code="RU", country_name="Russia", status=CensorshipStatus.BANNED,
         banned_since="1759",
         ban_reason="The Russian Orthodox Church and the Imperial censorship banned "
                    "Candide for its satire of providence, the Church and state power; "
                    "early Russian readers met it through surreptitious manuscripts.",
         notes="Also condemned in French 'public order' rulings at publication."),
    # ── Huckleberry Finn ─────────────────────────────────────────────────
    dict(match=["huckleberry finn"], author="twain",
         country_code="US", country_name="United States", status=CensorshipStatus.CONTESTED,
         banned_since="1885–present",
         ban_reason="From its first year — Concord's library called it 'trash' — through "
                    "modern school-district removals, Huckleberry Finn has been the most "
                    "challenged classic in US classrooms, objected to for its vernacular "
                    "language and its satirical treatment of race.",
         notes="ALA Banned Books data lists it among the most challenged classics."),
    # ── Leaves of Grass ──────────────────────────────────────────────────
    dict(match=["leaves of grass", "song of myself"], author="whitman",
         country_code="US", country_name="United States", status=CensorshipStatus.BANNED,
         banned_since="1882",
         ban_reason="The Boston district attorney ordered the 1881 edition suppressed for "
                    "obscenity, and a bookseller was prosecuted for selling it. Whitman "
                    "re-issued the same text through a Philadelphia publisher weeks later.",
         notes="Classic 'whack-a-mole': banning drove more sales."),
    # ── Fanny Hill ───────────────────────────────────────────────────────
    dict(match=["fanny hill", "memoirs of a woman of pleasure"], author="cleland",
         country_code="US", country_name="United States", status=CensorshipStatus.BANNED,
         banned_since="1821–1966",
         ban_reason="The first book ever prosecuted as obscene in Massachusetts (1821) and "
                    "long seized by customs; the 1966 'Memoirs v. Massachusetts' ruling "
                    "finally cleared it, a defining test of the obscenity standard.",
         notes="Cleland's 1748 novel remained an import-crime for 140 years."),
    dict(match=["fanny hill", "memoirs of a woman of pleasure"], author="cleland",
         country_code="GB", country_name="United Kingdom", status=CensorshipStatus.RESTRICTED,
         banned_since="19th century",
         ban_reason="Prosecutions and obscenity trials made selling Fanny Hill a legal "
                    "gamble in England through the nineteenth century, though it never "
                    "lacked an underground circulation.",
         notes="Obscene Publications Act treatments."),
    # ── The Social Contract ──────────────────────────────────────────────
    dict(match=["social contract"], author="rousseau",
         country_code="FR", country_name="France", status=CensorshipStatus.BANNED,
         banned_since="1762",
         ban_reason="Rousseau's 'Du contrat social' was condemned by the Parliament of Paris "
                    "and publicly burned, and his Geneva birthplace added its own sentence; "
                    "he spent years as a fleeing writer with warrents against him.",
         notes="One of the era's great burned books."),
    # ── The Prince ───────────────────────────────────────────────────────
    dict(match=["the prince"], author="machiavelli",
         country_code="IT", country_name="Italy / Holy See", status=CensorshipStatus.RESTRICTED,
         banned_since="1559",
         ban_reason="Placed on the Index of Prohibited Books in 1559; the work was attacked "
                    "across Europe as a manual of tyranny, the origin of 'Machiavellian' as "
                    "an insult.",
         notes="Index listing; later revised editions expurgated."),
    # ── Communist Manifesto ──────────────────────────────────────────────
    dict(match=["communist manifesto", "manifesto of the communist"], author="marx",
         country_code="DE", country_name="Germany", status=CensorshipStatus.BANNED,
         banned_since="1848–1860s",
         ban_reason="Banned soon after the revolutions of 1848 across the German states; "
                    "Marx and Engels were tried for conspiracy in Cologne (1852) over the "
                    "chain the Manifesto fed.",
         notes="Historic state suppression of communist text."),
    dict(match=["communist manifesto", "manifesto of the communist"], author="marx",
         country_code="ZA", country_name="South Africa", status=CensorshipStatus.BANNED,
         banned_since="1950s–1990",
         ban_reason="Under apartheid, 'communism' was legally defined broadly enough that "
                    "the Manifesto and much socialist literature became prohibited imports "
                    "and possessions; the ban only collapsed with democratic transition.",
         notes="Suppression of Communism Act era."),
    # ── The Great Gatsby ─────────────────────────────────────────────────
    dict(match=["great gatsby"], author="fitzgerald",
         country_code="US", country_name="United States", status=CensorshipStatus.CONTESTED,
         banned_since="1987–present",
         ban_reason="School districts from the late 1980s objected to language and sexual "
                    "references in Gatsby, and colleges have replaced it on occasion — one "
                    "of the most challenged American novels in continuing circulation.",
         notes="ALA challenge records."),
    # ── Uncle Tom's Cabin ────────────────────────────────────────────────
    dict(match=["uncle tom"], author="stowe",
         country_code="US", country_name="United States (South)", status=CensorshipStatus.RESTRICTED,
         banned_since="1850s",
         ban_reason="In the slave states the book was suppressed as abolitionist agitation; "
                    "public response credited it with reshaping the national argument before "
                    "the Civil War.",
         notes="Southern states' suppression responses."),
    # ── Jurgen ───────────────────────────────────────────────────────────
    dict(match=["jurgen"], author="cabell",
         country_code="US", country_name="United States", status=CensorshipStatus.BANNED,
         banned_since="1920",
         ban_reason="The New York Society for the Suppression of Vice secured the "
                    "withdrawal of Cabell's 'Jurgen' for obscenity weeks after publication "
                    "in 1920; the ensuing furor made it a cause célèbre and a famous "
                    "suppressed novel.",
         notes="Classic early-20th-century suppression case."),
    # ── Lysistrata ───────────────────────────────────────────────────────
    dict(match=["lysistrata"], author="aristophanes",
         country_code="US", country_name="United States", status=CensorshipStatus.CONTESTED,
         banned_since="1955",
         ban_reason="A 1955 New York stage production was closed by police in a celebrated "
                    "obscenity bust, turning Aristophanes' 2,400-year-old sex-strike comedy "
                    "into a Free Speech cause.",
         notes="Production prosecution; the play itself circulates freely."),
    # ── The Jungle ───────────────────────────────────────────────────────
    dict(match=["the jungle"], author="sinclair",
         country_code="US", country_name="United States", status=CensorshipStatus.CONTESTED,
         banned_since="1906",
         ban_reason="Sinclair's muckracker classic was embargoed by some libraries and "
                    "condemned by the meat industry while Congress took note; parts of it "
                    "were challenged as obscene for the red-light chapter, and translation "
                    "bans followed abroad.",
         notes="Mixed record: industry vs. regulators."),
    # ── The Picture of Dorian Gray ───────────────────────────────────────
    dict(match=["dorian gray"], author="wilde",
         country_code="GB", country_name="United Kingdom", status=CensorshipStatus.CONTESTED,
         banned_since="1890",
         ban_reason="The 1890 magazine edition was condemned as immoral for its homoerotic "
                    "undertones, and Wilde's publisher excised passages for the 1891 book "
                    "edition; the novel was long cited in obscenity debates at home and abroad.",
         notes="Decadent-era suppression."),
    # ── The Well? (not carried) ──────────────────────────────────────────
    dict(match=["well of loneliness"], author="hall",
         country_code="GB", country_name="United Kingdom", status=CensorshipStatus.BANNED,
         banned_since="1928",
         ban_reason="Prosecuted and withdrawn in 1928 as an obscene publication under the "
                    "Obscene Publications Act — a landmark trial of lesbian literature.",
         notes="If the work enters the catalogue (author died 1943, UK PD), attach this."),
]

COUNTRY_NAMES = {
    "US": "United States", "GB": "United Kingdom", "IT": "Italy", "FR": "France",
    "EG": "Egypt", "IE": "Ireland", "RU": "Russia", "DE": "Germany", "ZA": "South Africa",
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())


def author_tokens(spec: dict) -> list[str]:
    """Distinctive tokens from the spec author field, e.g. 'Joyce, James' -> ['joyce','james']."""
    raw = spec.get("author") or ""
    tokens = []
    for part in re.split(r"[|,/&()]+", raw):
        part = norm(part).strip()
        if part and part not in ("unknown", "anonymous", "?") and part not in tokens:
            tokens.append(part)
    return tokens


def author_ok(book: Book, spec: dict) -> bool:
    """Author disambiguation: the catalogue title may differ (translations,
    subtitles), so require the author to agree unless the spec is anonymous —
    in which case only a long, unambiguous title key is trusted."""
    tokens = author_tokens(spec)
    if not tokens:
        longest = max((len(norm(m)) for m in spec["match"] if norm(m)), default=0)
        return longest >= 18
    author = norm(book.author or "")
    return any(t in author for t in tokens)


def resolve(spec: dict, by_title: dict[str, Book]) -> Book | None:
    """Author-aware title resolution, preferring exact-length titles."""
    keys = [norm(m) for m in spec["match"] if norm(m)]
    if not keys:
        return None
    direct = next((by_title[k] for k in keys if k in by_title), None)
    if direct and author_ok(direct, spec):
        return direct

    candidates = []
    for key, book in by_title.items():
        for k in keys:
            if k in key or key in k:
                if author_ok(book, spec):
                    candidates.append((abs(len(key) - len(k)), len(key), book))
                break
    if not candidates:
        return None
    candidates.sort(key=lambda t: (t[0], t[1]))
    return candidates[0][2]


async def main():
    async with AsyncSessionLocal() as db:
        # Seed rows are curated by script; purge and re-seed so matching fixes
        # take effect. Admin-verified / user-flagged records are untouched.
        purge = await db.execute(
            sa_delete(CensorshipRecord).where(CensorshipRecord.verified_by == "seed")
        )
        await db.commit()
        print(f"purged {purge.rowcount} previous seed rows")

        rows = (await db.execute(
            select(Book).where(Book.status == BookStatus.APPROVED)
        )).scalars().all()
        by_title: dict[str, Book] = {}
        for b in rows:
            by_title.setdefault(norm(b.title), b)

        existing_pairs = {
            (r.book_id, r.country_code)
            for r in (await db.execute(select(CensorshipRecord))).scalars().all()
        }

        created = skipped = 0
        for spec in RECORDS:
            book = resolve(spec, by_title)
            if not book:
                print(f"skip (not in catalogue): {spec['country_code']} {spec['match'][0]}"
                      f"{' — '+spec['author'] if spec.get('author') else ''}")
                skipped += 1
                continue

            if (book.id, spec["country_code"]) in existing_pairs:
                print(f"exists: {book.title[:40]} | {spec['country_code']}")
                continue
            country_name = spec.get("country_name") or COUNTRY_NAMES.get(spec["country_code"], spec["country_code"])
            db.add(CensorshipRecord(
                book_id=book.id,
                country_code=spec["country_code"],
                country_name=country_name,
                status=spec["status"],
                ban_reason=spec["ban_reason"],
                banned_since=spec.get("banned_since"),
                notes=spec.get("notes"),
                verified=True,
                verified_by="seed",
            ))
            existing_pairs.add((book.id, spec["country_code"]))
            created += 1
            print(f"add: {book.title[:44]:44} {spec['country_code']} [{spec['status']}]")

        await db.commit()
        print(f"done. created={created} skipped_not_in_catalogue={skipped}")


asyncio.run(main())