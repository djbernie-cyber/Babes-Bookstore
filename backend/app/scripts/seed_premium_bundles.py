"""Premium bundle creation: Foie Gras (top-1000 bestsellers) + Presidents.

Idempotent: skips bundles whose slug already exists, tops membership up by
set difference. Run inside the API container:
    cd /app && PYTHONPATH=/app python /tmp/seed_premium_bundles.py
"""
import asyncio
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.book import Book
from app.models.bundle import Bundle, BundleBook

FOIE_PRICE = 10000    # £100.00
PRESIDENTS_PRICE = 100000  # £1000.00
CURRENCY = "gbp"

# The shelf is an open-ended evergreen set (the top-up loop keeps it growing),
# so the copy must not claim a fixed count it does not honour.
FOIE_NAME = "The Foie Gras — Evergreen Bestsellers"
FOIE_DESCRIPTION = (
    "Every title the canon insists you have read, and then some. "
    "Foie gras for the shelf: the pretentious non-reader's "
    "favourite status symbol, in one magnificent, ever-growing set."
)
FOIE_LONG_DESCRIPTION = (
    "Every bookseller's '1000 books to read before you die' list, distilled and "
    "bound as one — then topped up with the rest of the approved canon's "
    "greatest hits. Dickens, Tolstoy, Austen, Homer, Hugo, Twain, Dostoevsky, "
    "Eliot, Wells, Doyle and thousands more works of certified importance for "
    "the reader who wants to be seen reading. Display it. Photograph it. "
    "Regret none of it."
)
FOIE_META_TITLE = "The Foie Gras — Evergreen Bestsellers | Babes Bookstore"
FOIE_META_DESCRIPTION = (
    "The snootiest bundle in publishing: the all-time bestsellers and the "
    "approved canon, licence-verified, always growing."
)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# ── All-time bestsellers (public-domain-heavy canon) ────────────────────
BESTSELLER_TITLES = [
    # Dickens & the Victorian giants
    "A Tale of Two Cities", "Great Expectations", "Oliver Twist", "David Copperfield",
    "Bleak House", "Hard Times", "Little Dorrit", "Our Mutual Friend",
    "The Pickwick Papers", "Nicholas Nickleby", "Martin Chuzzlewit",
    "Dombey and Son", "Barnaby Rudge", "Edwin Drood", "A Christmas Carol",
    "The Old Curiosity Shop", "The Mystery of Edwin Drood", "Sketches by Boz",
    # French canon
    "The Count of Monte Cristo", "The Three Musketeers", "Twenty Thousand Leagues Under the Sea",
    "Around the World in Eighty Days", "The Hunchback of Notre Dame", "Les Miserables",
    "The Phantom of the Opera", "Madame Bovary", "The Three Musketeers",
    "The Count of Monte Cristo", "Germinal", "The Strange Case of the Yellow Room",
    # Russian canon
    "War and Peace", "Anna Karenina", "Crime and Punishment", "The Brothers Karamazov",
    "Notes from Underground", "The Idiot", "The Possessed", "Fathers and Sons",
    "The Cherry Orchard", "Three Sisters", "Uncle Vanya", "The Seagull",
    # English classics
    "Pride and Prejudice", "Sense and Sensibility", "Emma", "Persuasion",
    "Mansfield Park", "Northanger Abbey", "Jane Eyre", "Wuthering Heights",
    "Villette", "The Tenant of Wildfell Hall", "Middlemarch", "Silas Marner",
    "The Mill on the Floss", "Adam Bede", "Daniel Deronda", "Romola",
    "Frankenstein", "Dracula", "The Strange Case of Dr Jekyll and Mr Hyde",
    "The Picture of Dorian Gray", "The Importance of Being Earnest",
    "Lady Windermere's Fan", "Salome", "Treasure Island", "Kidnapped",
    "The Master of Ballantrae", "Ivanhoe", "Waverley", "Rob Roy",
    "Quentin Durward", "Kenilworth", "The Heart of Midlothian",
    # American canon
    "The Adventures of Huckleberry Finn", "The Adventures of Tom Sawyer",
    "Life on the Mississippi", "Roughing It", "The Innocents Abroad",
    "A Connecticut Yankee in King Arthur's Court", "The Prince and the Pauper",
    "Moby Dick", "Typee", "Omoo", "Redburn", "White-Jacket", "Billy Budd",
    "The Scarlet Letter", "The House of the Seven Gables", "The Blithedale Romance",
    "The Turn of the Screw", "The Portrait of a Lady", "The Wings of the Dove",
    "The Age of Innocence", "The House of Mirth", "Ethan Frome",
    "The Last of the Mohicans", "The Deerslider", "The Pathfinder",
    "The Pioneers", "The Spy", "The Pilot", "Winged-Head Dick",
    "The Red Badge of Courage", "McTeague", "Sister Carrie", "The Jungle",
    "The Great Gatsby", "This Side of Paradise", "The Beautiful and Damned",
    "Walden", "Leaves of Grass", "Song of Myself", "Leaves of Grass and Selected Poems",
    "The Autobiography of Benjamin Franklin", "Narrative of the Life of Frederick Douglass",
    "Up from Slavery", "The Souls of Black Folk", "Narrative of Sojourner Truth",
    "Incidents in the Life of a Slave Girl", "Uncle Tom's Cabin",
    "The Adventures of Tom Sawyer", "Little Women", "Good Wives",
    "An Old-Fashioned Girl", "Eight Cousins", "Rose in Bloom", "Jo's Boys",
    "Anne of Green Gables", "Anne of Avonlea", "The Story Girl", "Golden Road",
    "The Secret Garden", "A Little Princess", "The Railway Children",
    "The Wonderful Wizard of Oz", "The Marvelous Land of Oz",
    # Philosophy, ideas, science (the shelf-sniffing material)
    "The Republic", "Meditations", "The Prince", "Leviathan",
    "Two Treatises of Government", "The Social Contract", "The Wealth of Nations",
    "The Communist Manifesto", "Das Kapital", "Capital", "The Origin of Species",
    "On the Origin of Species", "The Descent of Man", "The Interpretation of Dreams",
    "Thus Spoke Zarathustra", "Beyond Good and Evil", "Critique of Pure Reason",
    "The Problems of Philosophy", "An Enquiry Concerning Human Understanding",
    "Discourse on Method", "The Ethics", "Nicomachean Ethics", "Politics",
    "Paradise Lost", "The Faerie Queene", "The Canterbury Tales",
    "The Divine Comedy", "Inferno", "Decameron", "Don Quixote",
    "The Pilgrim's Progress", "Robinson Crusoe", "Gulliver's Travels",
    "The Wind in the Willows", "Peter and Wendy", "Alice's Adventures in Wonderland",
    "Through the Looking-Glass", "The Jungle Book", "The Second Jungle Book",
    "Kim", "The Man Who Would Be King", "Captains Courageous",
    "Puck of Pook's Hill", "Rewards and Fairies", "The Call of the Wild",
    "White Fang", "The Sea-Wolf", "Martin Eden", "The Iron Heel",
    "The Time Machine", "The War of the Worlds", "The Invisible Man",
    "The Island of Doctor Moreau", "The Food of the Gods", "Tono-Bungay",
    "The Hound of the Baskervilles", "The Sign of the Four", "A Study in Scarlet",
    "The Valley of Fear", "The Return of Sherlock Holmes", "The Lost World",
    "The Poison Belt", "The Land That Time Forgot",
    "The Call of Cthulhu", "At the Mountains of Madness",
    "The Shadow over Innsmouth", "The Weird Tales of H. P. Lovecraft",
    "Tarzan of the Apes", "The Return of Tarzan", "A Princess of Mars",
    "The Gods of Mars", "The Warlord of Mars",
    "Ulysses", "Dubliners", "A Portrait of the Artist as a Young Man",
    "Mrs Dalloway", "To the Lighthouse", "Orlando", "The Waves",
    "The Metamorphosis", "The Trial", "The Castle", "America",
    "One, Two, Three: Growing Up", "Berlin Alexanderplatz",
    "All Quiet on the Western Front", "The Good Soldier Schweik",
    "The 39 Steps", "Greenmantle", "Mr Standfast", "Kidnapped",
    "Swiss Family Robinson", "The Count of Monte Cristo",
    "Ben Hur", "Quo Vadis", "The Deerslayer",
    "Black Beauty", "The Story of My Life" , "Ten Days That Shook the World",
    "The Confessions of Nat Turner", "The Grapes of Wrath",
    "The Importance of Being Earnest", "Pygmalion", "Arms and the Man",
    "Saint Joan", "Man and Superman", "Candida",
    "The Importance of Being Earnest", "The Wind in the Willows",
    "The Adventures of Augie March", "The Rum Diary",
    "The Diary of a Young Girl", "Night", "If This Is a Man",
    "The Rise and Fall of the Third Reich",
    "Think and Grow Rich", "How to Win Friends and Influence People",
    "The Art of War", "The Richest Man in Babylon", "As a Man Thinketh",
    "The Power of Positive Thinking", "The Landmarks of Thought",
    "Self-Reliance and Other Essays", "The Essays", "Essays: First Series",
    "A Calendar of Wisdom", "The Prophet", "Leaves of Grass",
]


def _presidents_regex():
    return re.compile(
        r"(leadership|president|presidential|inaugural|commander|statesman|"
        r"washington|lincoln|roosevelt|jefferson|madison|monroe|adams|"
        r"jackson|van buren|harrison|tyler|polk|taylor|fillmore|pierce|"
        r"buchanan|grant|hayes|garfield|arthur|cleveland|harrison|mckinley|"
        r"roosevelt|taft|wilson|harding|coolidge|hoover|truman|eisenhower|"
        r"federalist|the prince|meditations|reminiscences|autobiography|"
        r"memoirs|life of|lives of|sayings|maxims|plutarch|marcus aurelius|"
        r"booker t\. washington|frederick douglass|alexander hamilton|"
        r"founders|constitution|democracy in america|the art of war|"
        r"greatest speech|great speeches|war and peace strategy|"
        r"management|executive|ceo|tycoon|mogul|magnate|industrialist)",
        re.I,
    )


async def main():
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Book.id, Book.title, Book.author, Book.tags).where(Book.status == "APPROVED")
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

        by_title = {}
        for b in books:
            by_title.setdefault(_norm(b["title"]), []).append(b)

        # ── Foie Gras: the top-1000 bestsellers ──
        foie = existing.get("foie-gras-best-sellers")
        if foie:
            print(f"foie-gras-best-sellers exists ({len(membership['foie-gras-best-sellers'])}) — topping up")
        chosen = []
        seen = set()

        # 1) exact / contained title matches from the curated bestseller list
        for t in BESTSELLER_TITLES:
            nt = _norm(t)
            hits = by_title.get(nt)
            if not hits:
                hits = [b for nt2, grp in by_title.items() if nt in nt2 or nt2 in nt for b in grp]
            for h in hits:
                if h["id"] not in seen:
                    seen.add(h["id"]); chosen.append(h)
            if len(chosen) >= 1000:
                break
        print(f"foie: curated matches: {len(chosen)}")

        # 2) classics-tagged fill
        if len(chosen) < 1000:
            for b in books:
                if b["id"] in seen: continue
                if any("classic" in (t or "").lower() for t in b["tags"]):
                    seen.add(b["id"]); chosen.append(b)
                    if len(chosen) >= 1000: break
        print(f"foie: after classics fill: {len(chosen)}")

        # 3) any remaining approved book (stable by id) to reach exactly 1000
        if len(chosen) < 1000:
            for b in sorted(books, key=lambda x: x["id"]):
                if b["id"] in seen: continue
                seen.add(b["id"]); chosen.append(b)
                if len(chosen) >= 1000: break
        print(f"foie: final: {len(chosen)}")

        if not foie:
            foie = Bundle(
                name=FOIE_NAME,
                slug="foie-gras-best-sellers",
                description=FOIE_DESCRIPTION,
                long_description=FOIE_LONG_DESCRIPTION,
                price_cents=FOIE_PRICE, currency=CURRENCY,
                category="Classics", tags=["Classics", "Bestsellers"],
                bundle_type="curated", active=True, featured=True,
                meta_title=FOIE_META_TITLE,
                meta_description=FOIE_META_DESCRIPTION,
            )
            db.add(foie); await db.flush()
            existing["foie-gras-best-sellers"] = foie
            membership["foie-gras-best-sellers"] = set()
        else:
            # Keep the on-disk copy honest about how large the shelf actually
            # is (the top-up loop keeps it growing past any fixed count).
            foie.name = FOIE_NAME
            foie.description = FOIE_DESCRIPTION
            foie.long_description = FOIE_LONG_DESCRIPTION
            foie.meta_title = FOIE_META_TITLE
            foie.meta_description = FOIE_META_DESCRIPTION
        have = membership.setdefault("foie-gras-best-sellers", set())
        add = [b["id"] for b in chosen if b["id"] not in have]
        for n, i in enumerate(add):
            db.add(BundleBook(bundle_id=existing["foie-gras-best-sellers"].id,
                              book_id=i, sort_order=len(have) + n))
        have.update(add)
        print(f"foie-gras: +{len(add)} (now {len(have)})")

        # ── Presidents: leadership canon ──
        prez_re = _presidents_regex()
        prez_auth = ["washington, george", "lincoln, abraham", "roosevelt",
                     "jefferson, thomas", "adams, john", "hamilton, alexander",
                     "franklin, benjamin", "booker t", "douglass, frederick",
                     "plutarch", "machiavelli", "aurelius, marcus", "plato",
                     "aristotle", "burke, edmund", "tocqueville"]
        prez = [b for b in books
                if prez_re.search(b["title"] or "")
                or prez_re.search(b["author"] or "")
                or any(p in (b["author"] or "").lower() for p in prez_auth)]
        print(f"presidents: matches: {len(prez)}")

        pb = existing.get("presidents-leadership-library")
        if not pb:
            pb = Bundle(
                name="The Presidents' Cabinet — Leadership of the Free World",
                slug="presidents-leadership-library",
                description="Every leadership classic ever worth quoting at a board "
                    "table — statesmen, founders, field marshals and the books "
                    "CEOs pretend to have read.",
                long_description="From Washington and Lincoln's own words to "
                    "Plutarch, Machiavelli, Marcus Aurelius, the Federalist Papers "
                    "and the canon of presidential biography, this is the £1,000 "
                    "leadership shelf: the greatest management and statesmanship "
                    "books of all time, licence-verified and print-ready. For the "
                    "reader who leads — or intends to.",
                price_cents=PRESIDENTS_PRICE, currency=CURRENCY,
                category="History", tags=["History", "Biography", "Leadership"],
                bundle_type="curated", active=True, featured=True,
                meta_title="The Presidents' Cabinet — £1,000 Leadership Bundle | Babes Bookstore",
                meta_description="The greatest leadership and statesmanship books of all time, one magnificent £1,000 set.",
            )
            db.add(pb); await db.flush()
            existing["presidents-leadership-library"] = pb
            membership["presidents-leadership-library"] = set()
        have_p = membership.setdefault("presidents-leadership-library", set())
        add_p = [b["id"] for b in prez if b["id"] not in have_p]
        for n, i in enumerate(add_p):
            db.add(BundleBook(bundle_id=existing["presidents-leadership-library"].id,
                              book_id=i, sort_order=len(have_p) + n))
        have_p.update(add_p)
        print(f"presidents: +{len(add_p)} (now {len(have_p)})")

        # ── showcase: classics visible too ──
        classic = existing.get("classics-canon")
        if classic and not classic.featured:
            classic.featured = True
            print("classics-canon: featured=True")

        await db.commit()
        print("done.")


asyncio.run(main())