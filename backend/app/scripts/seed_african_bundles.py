"""African Literature bundles — built from what we can actually license.

Idempotent: creates each bundle if its slug is absent, then tops membership up
by set difference so the set keeps growing as ingestion improves. Run inside
the API container:

    cd /app && PYTHONPATH=/app python /tmp/seed_african_bundles.py
    # add --dry-run to report without writing

An honesty note, learned the hard way from the Foie Gras bundle: these are
evergreen sets that grow as the catalogue improves, so the copy must NOT claim
a fixed count it does not honour. Every selection below is derived from the
author classifiers and the licence audit — nothing is hard-coded, and no work
is included that is not approved and licence-verified. In particular the
modern canon that is still in copyright (Achebe, Soyinka, Ngugi) is
deliberately absent; see seed_censorship_africa.py for the archive that
documents their suppression without hosting them.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.book import Book, BookStatus
from app.models.bundle import Bundle, BundleBook
from app.sources.african_ebooks import (
    AFRICAN_LITERATURE_TAG,
    AFRICAN_CONTINENT_TAG,
    AfricanEbooksSource,
)

DRY_RUN = "--dry-run" in sys.argv
CURRENCY = "gbp"
PRICE = 4900  # £49.00

#: Diaspora surnames present in the classifier's African-American canon.
DIASPORA_MARKERS = (
    "dubois", "du bois", "washington", "brown", "douglass", "harper", "dunbar",
    "chesnutt", "hurston", "wells-barnett", "wells barnett", "wells", "griggs",
    "mckay", "floyd", "johnson", "miller", "delany", "toomer", "henson",
    "hopkins", "thurman", "moore", "cullen", "jones", "grimk", "crummell",
    "garnet", "seacole", "wheatley", "northup", "chamberlain", "steward",
    "payne", "webb", "jacobs", "bibb", "box brown", "sancho", "c-pennington",
    "pennington", "cummings", "larsen", "rhys", "ward", "fauset", "hughes",
    "burns, allan", "allan burns", "cullen", "schomburg", "terrell", "crumpler",
    "nell", "craft", "le armstrong", "armstrong", "giovanni", "angelou",
    "morrison", "baldwin", "king", "wright", "hughes", "harper",
)


def is_african(author: str) -> bool:
    return bool(AfricanEbooksSource._is_african_author(author)
                or AfricanEbooksSource._is_colonial_author(author))


def is_continent(author: str) -> bool:
    return bool(AfricanEbooksSource._is_continent_african(author))


def is_diaspora(author: str) -> bool:
    low = (author or "").lower()
    return any(m in low for m in DIASPORA_MARKERS)


BUNDLES = [
    dict(
        slug="african-literature-canon",
        name="African Literature — The Living Canon",
        description=(
            "The whole African and African-diaspora shelf in one ever-growing set: "
            "the pioneering narratives, the novelists, the poets and the historians. "
            "Every title licence-verified and free to download."
        ),
        long_description=(
            "A curated shelf spanning the continent and the diaspora — Olaudah "
            "Equiano's pioneering narrative, Olive Schreiner and Sol T. Plaatje at "
            "the founding of Southern African letters, and the great African-American "
            "canon: Du Bois, Washington, Douglass, Chesnutt, Hurston, Hughes, the "
            "Harpers, the Grimkés, Wheatley and Mary Seacole.\n\n"
            "This set grows as the catalogue grows. We add only works that are "
            "genuinely public-domain or openly licensed — which is why the modern "
            "African canon is documented in our archive rather than hosted here. "
            "Chinua Achebe, Wole Soyinka and Ngugi wa Thiong'o are still in "
            "copyright; we tell you where to read them legally instead of pretending "
            "otherwise."
        ),
        meta_title="African Literature — The Living Canon | Babes Bookstore",
        meta_description=(
            "Every African and African-diaspora public-domain title we license, in "
            "one growing set. Equiano, Schreiner, Plaatje, Du Bois, Douglass, Chesnutt."
        ),
        category="African Literature",
        tags=["African Literature", "African Author", "evergreen"],
        select_books=lambda b: is_african(b.author),
        featured=True,
    ),
    dict(
        slug="black-african-writers",
        name="Black African Writers — The Continent",
        description=(
            "Works by Black African authors born on the continent, from the earliest "
            "oral-derived narrative to the first African novelists. Small, essential, "
            "and the shelf that leads the canon."
        ),
        long_description=(
            "The continent-born Black African canon: writers who wrote in English, "
            "Portuguese, French and Dutch, and in the continent's own languages, "
            "whose work was carried into print under colonial and postcolonial "
            "constraint alike.\n\n"
            "This is deliberately the smallest bundle we publish, and the copy does "
            "not pretend otherwise. The literature of Africa is overwhelmingly "
            "modern and overwhelmingly in copyright; most of it is not yet free to "
            "redistribute. What is public domain, we carry. What is not, we point to "
            "— see our banned-books archive for the suppression history and our "
            "library finder for legal access."
        ),
        meta_title="Black African Writers — The Continent | Babes Bookstore",
        meta_description=(
            "Public-domain works by Black African authors born on the continent — "
            "the smallest and most essential shelf we publish."
        ),
        category="African Literature",
        tags=["African Literature", "African Author"],
        select_books=lambda b: is_continent(b.author),
        featured=False,
    ),
    dict(
        slug="african-american-diaspora",
        name="The African-American Diaspora Canon",
        description=(
            "Du Bois, Douglass, Washington, Chesnutt, Hurston, Hughes, the Grimkés, "
            "Wheatley, Seacole and more — the Black Atlantic canon in public-domain "
            "editions, free to read and download."
        ),
        long_description=(
            "The African-American canon in one set, from Phillis Wheatley's 1773 "
            "poems to the Harlem Renaissance: Douglass on abolition and the "
            "Constitutional betrayal, Du Bois and Washington on the colour line, "
            "Frances Ellen Watkins Harper, Paul Laurence Dunbar, Charles Chesnutt's "
            "dialect novellas, Ida B. Wells, Zora Neale Hurston, Langston Hughes, "
            "and the enslaved narratives — Equiano, Northup, Jacobs, Bibb, "
            "Box Brown and the rest.\n\n"
            "All public domain, all licence-verified, all free."
        ),
        meta_title="The African-American Diaspora Canon | Babes Bookstore",
        meta_description=(
            "Wheatley, Douglass, Du Bois, Chesnutt, Hurston, Hughes, the Grimkés and "
            "the enslaved narratives — the Black Atlantic canon, free to download."
        ),
        category="African Literature",
        tags=["African Literature", "African-American", "diaspora"],
        select_books=lambda b: is_african(b.author) and is_diaspora(b.author),
        featured=True,
    ),
]


async def main():
    async with AsyncSessionLocal() as db:
        books = (await db.execute(
            select(Book).where(
                Book.status == BookStatus.APPROVED,
                Book.license_verified.is_(True),
            )
        )).scalars().all()
        print(f"scanned {len(books)} approved, licence-verified books\n")

        for spec in BUNDLES:
            members = [b for b in books if spec["select_books"](b)]
            # Stable, readable ordering: author surname, then title.
            members.sort(key=lambda b: ((b.author or "").lower(), (b.title or "").lower()))

            existing = (await db.execute(
                select(Bundle).where(Bundle.slug == spec["slug"])
            )).scalar_one_or_none()

            if existing is None:
                if DRY_RUN:
                    print(f"[dry] would create {spec['slug']:28} {len(members):4} books")
                    continue
                existing = Bundle(
                    slug=spec["slug"],
                    name=spec["name"],
                    description=spec["description"],
                    long_description=spec["long_description"],
                    meta_title=spec["meta_title"],
                    meta_description=spec["meta_description"],
                    category=spec["category"],
                    tags=spec["tags"],
                    price_cents=PRICE,
                    currency=CURRENCY,
                    active=True,
                    featured=spec["featured"],
                    bundle_type="curated",
                )
                db.add(existing)
                await db.flush()
                print(f"created {spec['slug']:28} {len(members):4} books")
            else:
                print(f"exists  {spec['slug']:28} topping up")

            have = {
                r[0] for r in (await db.execute(
                    select(BundleBook.book_id).where(BundleBook.bundle_id == existing.id)
                )).all()
            }
            added = 0
            for i, b in enumerate(members):
                if b.id in have:
                    continue
                db.add(BundleBook(bundle_id=existing.id, book_id=b.id, sort_order=i))
                added += 1
            total = len(have) + added
            if not DRY_RUN:
                await db.commit()
            print(f"         +{added} added -> {total} members "
                  f"({len({b.author for b in members})} distinct authors)\n")


asyncio.run(main())
