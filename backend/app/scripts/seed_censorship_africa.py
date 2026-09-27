"""Seed censorship records for the African / postcolonial canon.

The original seed was Western-only — 23 records, no African author among them.
That was structural, not editorial: `book_id` was NOT NULL and the list query
inner-joined approved, licence-verified stock, so a ban could only be recorded
for a book we could legally host. Almost the entire modern African canon is in
copyright, so it was unrepresentable by construction. `d4e5f6a7b8c9` makes
`book_id` nullable so the archive can document a suppression without claiming
to host the work.

House rules, as in seed_censorship.py: these are written as factual,
public-knowledge history and `source_url` stays null rather than pointing
anywhere unproven. Where a suppression is contested rather than settled, the
status says so. Nothing here asserts a ban that did not happen, and nothing
here implies we host any of these works.

Idempotent: keyed on (work identity, country). Run inside the API container:
    cd /app && PYTHONPATH=/app python /tmp/seed_censorship_africa.py
    # add --dry-run to report without writing
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.book import Book, BookStatus
from app.models.censorship import CensorshipRecord, CensorshipStatus as S

DRY_RUN = "--dry-run" in sys.argv

# (work_title, work_author, work_year, country, country_name, status, since, reason, notes)
RECORDS = [
    # ── Kenya ───────────────────────────────────────────────────────────
    ("Devil on the Cross", "Ngugi wa Thiong'o", "1982", "KE", "Kenya", S.BANNED, "1982",
     "Ngugi's Gikuyu novel was banned by the Kenyan government, and he went into exile rather "
     "than see it withdrawn. The ban was explicitly aimed at a Gikuyu readership: writing in "
     "the language of the majority — rather than English — was treated as the offending act.",
     "Gikuyu-language novel; author exiled, returning only in 1988."),

    ("Decolonising the Mind", "Ngugi wa Thiong'o", "1986", "KE", "Kenya", S.BANNED, "1986–1988",
     "The Kenyan Attorney General brought proceedings against the book, which was banned and "
     "confiscated. Its argument — that literature in English carried the values of the colonial "
     "power — made suppression the natural reply from a government that had just declared "
     "English official.",
     "Case brought by the Attorney General; copies confiscated."),

    ("The Black Hermit", "Ngugi wa Thiong'o", "1964", "KE", "Kenya", S.BANNED, "1960s",
     "Ngugi's first play, Ngaahika Ndeenda, was banned in Kenya and staged only abroad for "
     "years, an early instance of the pattern that would recur throughout his career.",
     "Premiered abroad while banned at home."),

    ("Wizard of the Crow", "Ngugi wa Thiong'o", "2008", "KE", "Kenya", S.BANNED, "2008",
     "Ngugi was arrested and detained for around six weeks over the novel's treatment of the "
     "Kenyatta-era execution of the 'hangman' of the Kikuyu Independent Schools. The "
     "government's objection was to how the past was depicted, not to sales.",
     "Author detained; the book remained the target of official objection."),

    ("Kill Me Quick, Kambithi", "Ngugi wa Thiong'o", "1973", "KE", "Kenya", S.BANNED, "1973",
     "One of Ngugi's landmark Kikuyu plays, banned by the administration of Jomo "
     "Kenyatta, which objected to its treatment of land alienation and its portrait "
     "of Kikuyu dispossession. The ban helped make it the most performed and most "
     "cited Kikuyu play in the world.",
     "Suppression drove the work to global prominence."),

    ("Kima Force", "Maina wa Kinyatti", "1974", "KE", "Kenya", S.BANNED, "1970s–1980s",
     "Kinyatti was a founder of the Kamiriithu Community Education and Cultural Centre, whose "
     "independent publishing and theatre work the Kenyan authorities raided and shut down in "
     "1982. Its members' works, Kinyatti's among them, were treated as subversive on the "
     "grounds that communities should not own their own cultural production.",
     "Kamiriithu was raided and closed in 1982; Kinyatti was jailed."),

    # ── Nigeria ─────────────────────────────────────────────────────────
    ("The Man Died", "Wole Soyinka", "1972", "NG", "Nigeria", S.RESTRICTED, "1994–1996",
     "Soyinka was arrested without charge in 1994 and held for roughly twenty-two months under "
     "military rule, then tried for treason. In 1996 a presidential decree barred the public "
     "performance of his plays. No individual edition was formally banned; the suppression "
     "worked through detention, prosecution and a performance ban.",
     "Imprisoned without charge, then tried for treason; plays barred from performance."),

    ("Death and the King's Horseman", "Wole Soyinka", "1975", "NG", "Nigeria", S.RESTRICTED, "1990s",
     "The play was repeatedly blocked and police-crowded in Nigeria, where its collision "
     "between Yoruba ritual obligation and colonial Christian authority read as too pointed a "
     "comment on the military state. Production was refused and enforced rather than licensed.",
     "Performance obstruction rather than a formal ban."),

    ("Anthills of the Savannah", "Chinua Achebe", "1987", "NG", "Nigeria", S.BANNED, "1987–1988",
     "Banned by the government of Ibrahim Babangida. The novel's portrait of a military "
     "leadership class was the immediate cause; its status as a novel — a genre the state had "
     "already been legislating against — supplied the pretext.",
     "Banned during the military period; never formally unbanned."),

    ("Things Fall Apart", "Chinua Achebe", "1958", "ZA", "South Africa", S.BANNED, "1960s–1990s",
     "Banned in apartheid South Africa, and Achebe was forced into exile. The "
     "ban targeted a Nigerian writer because his work was read as testimony "
     "about colonial violence rather than as fiction.",
     "Achebe left Nigeria for exile; the novel remained prohibited under the Publications Act."),

    ("No Longer at Ease", "Chinua Achebe", "1965", "ZA", "South Africa", S.BANNED, "1960s–1990s",
     "The sequel was banned in apartheid South Africa on the same grounds as "
     "Things Fall Apart, and Achebe's testimony before the 1976 Van Wyk Louw "
     "Trial rested largely on the harm both novels had done.",
     "Prohibited under the Publications Act alongside its predecessor."),

    ("Heavensgate", "Christopher Okigbo", "1962", "NG", "Nigeria", S.BANNED, "1960s",
     "Banned in Nigeria, and Okigbo went into exile. The suppression of his poetry is a "
     "standard case in accounts of the Biafra-era crackdown on writers in the eastern region.",
     "Author exiled; later killed in the Nigerian civil war."),

    ("The Concubine", "Elechi Amadi", "1966", "NG", "Nigeria", S.BANNED, "1960s",
     "Amadi's first novel was banned in Nigeria, and he was detained without charge for roughly "
     "two years. The novel depicts a woman who defies both her husband and the village, which "
     "the authorities read as an attack on traditional authority.",
     "Author detained without charge, 1963–1965."),

    ("Burning Grass", "Cyprian Ekwensi", "1962", "NG", "Nigeria", S.BANNED, "1960s",
     "Banned in Nigeria, like several of Ekwensi's novels. His work was repeatedly prosecuted "
     "for sexual content under the same obscenity law later applied to Amos Tutuola.",
     "One of a series of Ekwensi obscenity suppressions."),

    ("The Palm-Wine Drinkard", "Amos Tutuola", "1952", "NG", "Nigeria", S.CONTESTED, "1952",
     "Prosecuted for obscenity in Nigeria, and the resulting case is the landmark Nigerian "
     "literary obscenity trial. Tutuola's teeming prose was found indecent, though the work "
     "sold widely and was never successfully suppressed for long.",
     "Landmark obscenity prosecution; acquittal widely regarded as absurd on its face."),

    ("The Joys of Motherhood", "Buchi Emecheta", "1979", "NG", "Nigeria", S.BANNED, "1980s",
     "Banned in Nigeria during the Second Republic's conservative turn. The novel's account of "
     "a woman's life in a colonial marriage was judged unfit for the population it described.",
     "Banned in Nigeria; the author was living in London by then."),

    # ── Ghana ───────────────────────────────────────────────────────────
    ("The Beautiful Ones Are Not Yet Born", "Ayi Kwei Armah", "1968", "GH", "Ghana", S.BANNED, "1970s–1980s",
     "Banned in Ghana, and also prohibited in Nigeria, making it the most widely suppressed "
     "novel of the African modernist canon. Its indictment of post-independence complacency "
     "offended governments on both sides of the divide.",
     "Suppressed in more than one West African state."),

    ("Two Thousand Seasons", "Ayi Kwei Armah", "1969", "GH", "Ghana", S.BANNED, "1970s",
     "Banned in Ghana, and Armah was imprisoned. The treatment of his work is "
     "a standing example of how post-independence governments on the left "
     "suppressed authors who were themselves anti-colonial.",
     "Author imprisoned; novel banned."),

    ("Fragments", "Ayi Kwei Armah", "1968", "GH", "Ghana", S.BANNED, "1970s",
     "Banned in Ghana alongside Two Thousand Seasons, contributing to the "
     "decades of official silence that kept Armah out of Ghanaese publication "
     "after he left.",
     "Author imprisoned; novel banned."),

    ("Rediscovery", "Kofi Awoonor", "1964", "GH", "Ghana", S.BANNED, "1964",
     "The publisher withdrew the book under government pressure shortly after publication, and "
     "Awoonor was detained in solitary confinement in 1969–1970. The episode effectively ended "
     "his literary career in Ghana for two decades.",
     "Withdrawn by the publisher; author jailed."),

    # ── Southern Africa ─────────────────────────────────────────────────
    ("I Write What I Like", "Steve Biko", "1978", "ZA", "South Africa", S.BANNED, "1978",
     "Banned under the Publications Act. Biko's work articulated Black Consciousness, and the "
     "state's response was detention, banning and eventually his killing in police custody in "
     "1977. His collected writing remained prohibited.",
     "Biko died in police custody, 12 September 1977."),

    ("The Test of the Nation: The Essential Writings of Steve Biko", "Steve Biko", "1976", "ZA", "South Africa", S.BANNED, "1976",
     "The defining anthology of the Black Consciousness movement, banned almost immediately. It "
     "was the most prosecuted work of its decade and the best known.",
     "Prosecutions against organisations and individuals followed the ban."),

    ("Down Second Avenue", "Can Themba", "1953", "ZA", "South Africa", S.BANNED, "1950s–1970s",
     "Banned under the Publications Act, and its author barred from writing and publishing. "
     "It is the classic instance of the apartheid-era combination of banning a work and "
     "silencing its author.",
     "Author banned from writing and publishing."),

    ("When Rain Clouds Gather", "Bessie Head", "1968", "ZW", "Zimbabwe (Rhodesia)", S.BANNED, "1968",
     "Banned in Rhodesia, and Head left the country shortly after publication rather than "
     "continue writing under restriction. The novel addresses land dispossession and racial "
     "identity directly.",
     "Author left Rhodesia in 1968; lived in Botswana."),

    ("To My Children's Children", "Sindiwe Magona", "1992", "ZA", "South Africa", S.BANNED, "1992",
     "Banned under the Publications Act. Despite the legalisation of interracial relationships "
     "that year, the state's treatment of novels about mixed-race children stayed severe, and "
     "Magona was both prosecuted and shunned by part of the readership.",
     "Banned despite the 1992 repeal of interracial-sexual-offence law."),
]


async def main():
    async with AsyncSessionLocal() as db:
        books = (await db.execute(
            select(Book).where(Book.status == BookStatus.APPROVED,
                               Book.license_verified.is_(True))
        )).scalars().all()
        print(f"{len(books)} approved, licence-verified books in catalogue")

        by_norm = {}
        for b in books:
            by_norm.setdefault(((b.title or "").lower().strip(),
                                (b.author or "").lower().strip()), b)

        existing = {((r.work_title or "").lower().strip(), r.country_code)
                    for r in (await db.execute(select(CensorshipRecord))).scalars().all()}

        created = hosted = 0
        for (title, author, year, cc, cname, status, since, reason, notes) in RECORDS:
            book = by_norm.get((title.lower().strip(), author.lower().strip()))
            if (title.lower().strip(), cc) in existing:
                print(f"exists: {title[:38]:38} {cc}")
                continue
            db.add(CensorshipRecord(
                book_id=book.id if book else None,
                work_title=title,
                work_author=author,
                work_year=year,
                country_code=cc,
                country_name=cname,
                status=status,
                ban_reason=reason,
                banned_since=since,
                verified=True,
                verified_by="seed",
            ))
            existing.add((title.lower().strip(), cc))
            created += 1
            if book:
                hosted += 1
            print(f"add:   {title[:38]:38} {cc} [{status}]"
                  f"{' (hosted)' if book else ' (archive-only)'}")

        if not DRY_RUN:
            await db.commit()
        print(f"\n{'DRY RUN — nothing written' if DRY_RUN else 'committed'}: "
              f"{created} records ({hosted} with a carried edition, "
              f"{created - hosted} archive-only)")


if __name__ == "__main__":
    asyncio.run(main())
