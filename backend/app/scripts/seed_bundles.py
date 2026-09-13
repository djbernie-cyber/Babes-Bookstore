"""Create and top-up curated bundles from the approved catalogue.

Idempotent: existing bundle slugs are skipped, and bundle membership is
checked before adding a book, so re-running never duplicates.

Run inside the API container:
    cd /app && PYTHONPATH=/app python /tmp/seed_bundles.py
"""
import asyncio
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.book import Book
from app.models.bundle import Bundle, BundleBook

PRICE = 1000  # £10.00
CURRENCY = "gbp"


def _finds(substrings, value):
    v = (value or "").lower()
    return any(s in v for s in substrings)


NEW_BUNDLES = [
    dict(
        name="African Literature — The Voice of a Continent",
        slug="african-literature-voice",
        category="African Literature",
        tags=["African Literature"],
        featured=True,
        description="Dozens of works by African and diaspora writers — tales of the Cape, "
            "colonial transition, resistance and the African imagination.",
        long_description="From the Atlantic records of the Black Atlantic to Négritude's "
            "early echo, this bundle gathers the library's African-authored and Africa-shaped "
            "writing: narratives of the Middle Passage, South African and West African fiction, "
            "diaspora poetry and histories of the continent. A rich, urgent reading shelf.",
    ),
    dict(
        name="American Classics — The Great Republic",
        slug="american-classics-republic",
        category="Classics",
        tags=["American literature", "Classics"],
        featured=True,
        description="Twain, Melville, Emerson, Whitman, Dickinson, Wharton and more — the "
            "library of a young republic in full voice.",
        long_description="Huckleberry Finn, Moby-Dick and Walden sit beside the poems and "
            "essays that shaped modern America. A complete, print-ready American canon for "
            "browsers, phones and e-readers.",
    ),
    dict(
        name="Banned & Suppressed Classics — Courageous Words",
        slug="banned-suppressed-classics",
        category="Banned & Suppressed",
        tags=["Suppressed Classics", "Banned Books"],
        featured=True,
        description="Books once banned, burned or censored: Kama Sutra, the Decameron, "
            "Satyricon, Arabian Nights and more — words that survived the fire.",
        long_description="From the thirteenth century's Qhoboshihein to the school-library "
            "wars of the twentieth, censorship has always hunted the same prey: the candid, "
            "the subversive and the truthful. This bundle gathers the library's suppressed "
            "classics and condemned revolutionary writers. Some of history's most important "
            "books are the ones someone tried to destroy.",
    ),
    dict(
        name="Modernist Voices — The New World",
        slug="modernist-voices-new",
        category="Modern & 20th Century",
        tags=["Modernism", "20th century"],
        featured=False,
        description="Joyce, Woolf, Kafka, Mansfield, Yeats, Frost — the century that broke "
            "the old forms.",
        long_description="The interior monologue, the unreliable narrator, the shattered "
            "sonnet: the first decades of the twentieth century redrew literature. This bundle "
            "collects its truest voices, all licence-verified and print-ready.",
    ),
    dict(
        name="Mythology & Legends — Gods and Heroes",
        slug="mythology-legends",
        category="Folklore & Mythology",
        tags=["Mythology", "Folklore"],
        featured=False,
        description="Homer, Ovid, Bulfinch, the Norse Eddas — the oldest stories we tell.",
        long_description="Iliad, Odyssey, Metamorphoses, Myths of the Norsemen: the source "
            "texts behind Western literature, gathered in one elegant, readable shelf.",
    ),
    dict(
        name="Travel & Exploration — Far Roads",
        slug="travel-exploration",
        category="Travel",
        tags=["Travel", "Exploration"],
        featured=False,
        description="Livingstone on the Nile, Park at Timbuktu, and the voyages that mapped "
            "the world.",
        long_description="Classic travel writing and expedition narratives from Mungo Park, "
            "David Livingstone, Richard Burton, James Cook and more — history you can roam.",
    ),
    dict(
        name="Revolutionary Voices — Banned, Condemned, Unsilenced",
        slug="revolutionary-voices",
        category="Banned & Suppressed",
        tags=["Revolutionary", "African Literature"],
        featured=False,
        description="Writers condemned, imprisoned or exiled by their own states for the "
            "crime of telling the truth.",
        long_description="Steve Biko, Nelson Mandela, Ngũgĩ wa Thiong'o and Soyinka's "
            "generation — this bundle collects the library's Revolutionary-tagged works by "
            "African and diaspora writers: the banned, the imprisoned, and the unsilenced.",
    ),
]

TOP_UPS = [
    ("the-sherlock-files", ["doyle, arthur", "conan doyle"], 24),
    ("gothic-collection", [
        "walpole", "radcliffe, ann", "lewis, matthew", "shelley, mary",
        "le fanu", "hogg, james", "stoker, bram", "poe, edgar",
        "stevenson, robert", "oliphant, margaret",
    ], 24),
    ("mystery-whodunit", ["collins, wilkie", "poe, edgar", "doyle, arthur",
                          "green, anna katharine", "orczy", "le queux",
                          "bramah, ernest", "futrelle, jacques",
                          "chesterton, g. k.", "freeman, r. austin"], 36),
    ("children-ever-after", ["carroll, lewis", "grahame, kenneth", "kipling, rudyard",
                             "alcott, louisa", "nesbit, e.", "macdonald, george",
                             "barrie, j. m.", "collodi", "andrew lang"], 36),
    ("poetry-the-voice", ["wordsworth", "keats, john", "shelley, percy", "byron",
                          "burns, robert", "blake, william", "pope, alexander",
                          "tennyson", "browning", "arnold, matthew", "coleridge"], 60),
]

AMERICAN = ["twain, mark", "hawthorne, nathaniel", "melville, herman", "poe, edgar",
            "whitman, walt", "emerson, ralph", "thoreau, henry", "longfellow",
            "dickinson, emily", "wharton, edith", "james, henry", "alcott, louisa",
            "cooper, james", "irving, washington", "crane, stephen", "london, jack",
            "douglass, frederick", "franklin, benjamin"]
MODERN = ["joyce, james", "woolf, virginia", "kafka, franz", "bennett, arnold",
          "wells, h. g.", "lawrence, d. h.", "mansfield, katherine",
          "yeats, william", "frost, robert", "sandburg, carl", "chekhov, anton",
          "pirandello, luigi", "rilke", "gide, andre", "proust, marcel"]
MYTH_KW = re.compile(r"(myth|legend|iliad|odyssey|aeneid|edda|norse|metamorphoses|"
                     r"gilgamesh|fables?|folkl)", re.I)
MYTH_AUTHORS = ["homer", "hesiod", "ovid", "virgil", "apuleius", "bulfinch",
                "guerber", "lang, andrew", "saxo grammaticus", "sturluson"]
TRAVEL_KW = re.compile(r"(travels|voyage|journey|expedition|exploration|explor|"
                       r"nile|timbuktu|sahara|congo|africa|innocents abroad|"
                       r"typee|arabia)", re.I)
TRAVEL_AUTHORS = ["livingstone, david", "park, mungo", "burton, richard",
                  "speke", "baker, s. w.", "barth, heinrich",
                  "dampier", "cook, james", "humboldt, alexander", "kinglake"]


async def main():
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Book.id, Book.title, Book.author, Book.tags)
            .where(Book.status == "APPROVED")
        )).all()
        books = [dict(id=r[0], title=r[1], author=r[2], tags=r[3] or []) for r in rows]
        print(f"approved books loaded: {len(books)}")

        bundles = (await db.execute(select(Bundle))).scalars().all()
        existing = {b.slug: b for b in bundles}
        membership = {
            b.slug: set((await db.execute(select(BundleBook.book_id)
                                          .where(BundleBook.bundle_id == b.id))).scalars().all())
            for b in bundles
        }

        def pick(substrings, cap=None, exclude=None):
            out = []
            for b in books:
                if exclude and b["id"] in exclude:
                    continue
                if not _finds(substrings, b["author"]):
                    continue
                out.append(b)
                if cap and len(out) >= cap:
                    break
            return out

        # ── top-ups ──
        for slug, authors, target in TOP_UPS:
            hold = membership.setdefault(slug, set())
            need = target - len(hold)
            if need <= 0:
                print(f"topup {slug}: already {len(hold)} — skip")
                continue
            pool = pick(authors, exclude=hold)
            add = [b["id"] for b in pool[:need]]
            for n, i in enumerate(add):
                db.add(BundleBook(bundle_id=membership[slug] and existing[slug].id,
                                  book_id=i, sort_order=len(hold) + n))
            hold.update(add)
            print(f"topup {slug}: had {len(hold) - len(add)}, +{len(add)} "
                  f"(pool {len(pool)}, target {target})")

        # ── new bundles ──
        african = [
            b for b in books
            if "African Literature" in b["tags"] and "Colonial Sauce" not in b["tags"]
            and not (b["author"] or "").startswith("Burns, Robert")
            and not (b["author"] or "").startswith("Henry, O.")
        ]
        print(f"African Literature tag count (excl. Colonial Sauce): {len(african)}")

        suppressed = [b for b in books if "Suppressed Classics" in b["tags"]]
        print(f"Suppressed Classics tag count: {len(suppressed)}")

        revolutionary = [b for b in books if "Revolutionary" in b["tags"]]
        print(f"Revolutionary tag count: {len(revolutionary)}")

        for spec in NEW_BUNDLES:
            slug = spec["slug"]
            if slug in existing:
                print(f"create {slug}: already exists — skip")
                continue
            if slug == "african-literature-voice":
                chosen = sorted(african, key=lambda b: b["id"])[:60]
            elif slug == "american-classics-republic":
                chosen = pick(AMERICAN, cap=40)
            elif slug == "banned-suppressed-classics":
                chosen = sorted(suppressed, key=lambda b: b["id"])[:50]
                # Prefer true Suppressed Classics; top up with condemned
                # revolutionary canon so the bundle always has meat.
                if len(chosen) < 20:
                    have = {b["id"] for b in chosen}
                    fill = [b for b in revolutionary if b["id"] not in have]
                    chosen = chosen + fill[: max(0, 40 - len(chosen))]
            elif slug == "revolutionary-voices":
                chosen = sorted(revolutionary, key=lambda b: b["id"])[:40]
            elif slug == "modernist-voices-new":
                chosen = pick(MODERN, cap=40)
            elif slug == "mythology-legends":
                chosen = [b for b in books if MYTH_KW.search(b["title"] or "")
                          or _finds(MYTH_AUTHORS, b["author"])][:40]
            elif slug == "travel-exploration":
                chosen = [b for b in books if TRAVEL_KW.search(b["title"] or "")
                          or _finds(TRAVEL_AUTHORS, b["author"])][:40]
            else:
                chosen = []
            bundle = Bundle(
                name=spec["name"], slug=slug, description=spec["description"],
                long_description=spec.get("long_description"),
                price_cents=PRICE, currency=CURRENCY, category=spec["category"],
                tags=spec["tags"], bundle_type="curated",
                active=True, featured=spec.get("featured", False),
                meta_title=spec["name"], meta_description=spec["description"][:160],
            )
            db.add(bundle)
            await db.flush()
            for n, b in enumerate(chosen):
                db.add(BundleBook(bundle_id=bundle.id, book_id=b["id"], sort_order=n))
            existing[slug] = bundle
            membership[slug] = {b["id"] for b in chosen}
            print(f"create {slug}: pool {len(chosen)}, added {len(chosen)} books")

        await db.commit()
        print("done.")


asyncio.run(main())