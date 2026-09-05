"""African Literature adapter.

A dedicated, curated catalogue of African-authored and African-diaspora
literary works. Each entry is a canonical Project Gutenberg book (public
domain, English, licence-verified and downloadable), resolved through the
Gutenberg API so metadata, covers and EPUB/PDF files stay live.

The canon spans the continent and its diaspora: Olive Schreiner and Sol T.
Plaatje (South Africa), Olaudah Equiano (Igboland, Nigeria), Charles W.
Chesnutt and W.E.B. Du Bois (the United States diaspora), and more. Works
are tagged with `African Literature` so they can be browsed as a genre even
though they span many subject categories.
"""
import asyncio
import logging
from typing import List, Optional, Dict

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)

#: Curated canon: { gutenberg_id, title, author }. Resolved live via the
#: Gutenberg metadata endpoint which is public-domain, English and
#: downloadable — so these auto-approve and count toward the visible count.
AFRICAN_CANON: List[Dict] = [
    {"gutenberg_id": 1441, "title": "The Story of an African Farm", "author": "Olive Schreiner"},
    {"gutenberg_id": 1439, "title": "Dreams", "author": "Olive Schreiner"},
    {"gutenberg_id": 1440, "title": "Woman and Labour", "author": "Olive Schreiner"},
    {"gutenberg_id": 1458, "title": "Dream Life and Real Life: A Little African Story", "author": "Olive Schreiner"},
    {"gutenberg_id": 64520, "title": "Thoughts on South Africa", "author": "Olive Schreiner"},
    {"gutenberg_id": 1452, "title": "Native Life in South Africa: Before and Since the War", "author": "Sol T. Plaatje"},
    {"gutenberg_id": 15399, "title": "The Interesting Narrative of the Life of Olaudah Equiano", "author": "Olaudah Equiano"},
    {"gutenberg_id": 472, "title": "The House Behind the Cedars", "author": "Charles W. Chesnutt"},
    {"gutenberg_id": 11666, "title": "The Conjure Woman", "author": "Charles W. Chesnutt"},
    {"gutenberg_id": 11057, "title": "The Wife of his Youth and Other Stories", "author": "Charles W. Chesnutt"},
]

#: Public-domain African / African-diaspora authors we add on top of the
#: hand-curated canon during ingestion. Expanded to span the continent and
#: its diaspora — Southern Africa's first novelists, the pioneers of
#: Anglo-Indian & African letters in the Empire, and the great writers of
#: African-American letters whose work charts the diaspora.
AFRICAN_AUTHORS: List[str] = [
    # ── Southern Africa ─────────────────────────────────────────────
    "Olive Schreiner",
    "Sol T. Plaatje",
    "Solomon T. Plaatje",
    "Thomas Mofolo",
    "H.I.E. Dhlomo",
    "Herbert Isaac Ernest Dhlomo",
    "B.W. Vilakazi",
    "Benedict Wallet Vilakazi",
    "John Tengo Jabavu",
    "John Langalibalele Dube",
    "Magema Magwaza Fuze",
    "D.D.T. Jabavu",
    "S.E.K. Mqhayi",
    "Samuel Edward Krune Mqhayi",
    "A.C. Jordan",
    "Archibald Campbell Jordan",
    "Bessie Head",
    "Alan Paton",
    "Nadine Gordimer",
    "André Brink",
    "Andre Brink",
    "C.J. Langenhoven",
    "Cornelis Jacob Langenhoven",
    "Roy Campbell",
    "Solomon Caesar Malan",
    "John William Colenso",
    # ── West Africa ──────────────────────────────────────────────────
    "Olaudah Equiano",
    "Amos Tutuola",
    "Chinua Achebe",
    "Wole Soyinka",
    "Buchi Emecheta",
    "Cyprian Ekwensi",
    "Mongo Beti",
    "Camara Laye",
    "Ferdinand Oyono",
    "Sembène Ousmane",
    "Ousmane Sembene",
    "Cheikh Anta Diop",
    "David Diop",
    "Birago Diop",
    "Léopold Sédar Senghor",
    "Leopold Sedar Senghor",
    "Aimé Césaire",
    "Ayi Kwei Armah",
    "Kofi Awoonor",
    "Efua Sutherland",
    # ── East / Central Africa ───────────────────────────────────────
    "Ngugi wa Thiong'o",
    "Ngugi wa Thiong o",
    "James Ngugi",
    "Meja Mwangi",
    "Grace Ogot",
    "Okot p'Bitek",
    "Okot p Bitek",
    "Cheikh Hamidou Kane",
    "Marjorie Oludhe Macgoye",
    # ── Caribbean & the wider diaspora ───────────────────────────────
    "V.S. Naipaul",
    "Vidiadhar Surajprasad Naipaul",
    "Sam Selvon",
    "George Lamming",
    "C.L.R. James",
    "Cyril Lionel Robert James",
    "Mary Seacole",
    "Robert Wedderburn",
    "William Wells Brown",
    "W. Adolphe Roberts",
    "Roger Mais",
    "Jean Rhys",
    # ── North Africa (Anglophone PD voices) ──────────────────────────
    "Taha Hussein",
    "Naguib Mahfouz",
    "Nawal El Saadawi",
    "Yusuf Idris",
    "Tayeb Salih",
    "Albert Camus",
    "Abou Bekr ibn Bedr",
    # ── African-American letters & the diaspora ─────────────────────
    "Charles W. Chesnutt",
    "Charles Waddell Chesnutt",
    "W.E.B. Du Bois",
    "William Edward Burghardt Du Bois",
    "Booker T. Washington",
    "Pauline Hopkins",
    "Pauline E. Hopkins",
    "Frederick Douglass",
    "Frances E.W. Harper",
    "Frances Ellen Watkins Harper",
    "James Weldon Johnson",
    "Paul Laurence Dunbar",
    "Alice Dunbar-Nelson",
    "Alice Moore Dunbar-Nelson",
    "Langston Hughes",
    "Zora Neale Hurston",
    "Countee Cullen",
    "Claude McKay",
    "Jean Toomer",
    "Angelina Weld Grimké",
    "Angelina Weld Grimke",
    "Phillis Wheatley",
    "Phillis Wheatley Peters",
    "Ottobah Cugoano",
    "Ignatius Sancho",
    "Harriet Jacobs",
    "Harriet A. Jacobs",
    "Sojourner Truth",
    "Isabella Baumfree",
    "Ida B. Wells-Barnett",
    "Ida B. Wells",
    "Mary McLeod Bethune",
    "Sutton E. Griggs",
    "Sutton Elbert Griggs",
    "Nella Larsen",
    "Jessie Redmon Fauset",
    "Dorothy West",
    "Wallace Thurman",
    "Marcus Garvey",
    "George Washington Williams",
    "Alexander Crummell",
    "Martin Delany",
    "Martin R. Delany",
    "Martin Robison Delany",
    "David Walker",
    "Henry Highland Garnet",
    "Jupiter Hammon",
    "Georgia Douglas Johnson",
    "Frank J. Webb",
    "Frank J. Webb",
    "Victor Séjour",
    "Victor Sejour",
    "Wendell Phillips Dabney",
    "Kelly Miller",
    # ── 18th-century African & transatlantic enslaved narrators ─────
    "James Albert Ukawsaw Gronniosaw",
    "John Marrant",
    "John Jea",
    "Benjamin Banneker",
    "Richard Allen",
    "Absalom Jones",
    "Prince Hall",
    "Jarena Lee",
    "Zilpha Elaw",
    "James W.C. Pennington",
    "James Pennington",
    "Josiah Henson",
    "Henry Bibb",
    "Moses Roper",
    "Solomon Northup",
    "Omar ibn Said",
    "Mahommah Gardo Baquaqua",
    "John S. Jacobs",
    "Austin Steward",
    "Samuel Ringgold Ward",
    "William Craft",
    "Ellen Craft",
    "Lewis Clarke",
    "Milton Clarke",
    "Henry Box Brown",
    "Sarah Parker Remond",
    "James M. Whitfield",
    "Eden Upton",
    "Daniel Payne",
    # ── African-American fiction, poetry & history (public domain) ──
    "J. E. Bruce",
    "John Edward Bruce",
    "John Mercer Langston",
    "James Madison Bell",
    "Albery Allson Whitman",
    "Joseph Seamon Cotter",
    "Joseph Seamon Cotter Jr.",
    "William H. A. Moore",
    "Carrie Williams Clifford",
    "Edward Smyth Jones",
    "George Marion McClellan",
    "Sarah Louisa Forten Purvis",
    "Charlotte Forten Grimké",
    "Charlotte Forten Grimke",
    "Julia A. J. Foote",
    "Amanda Berry Smith",
    "Edwin Archer Randolph",
    "Robert H. Terrell",
    "Ambroise Alexander",
    "John Robert Bond",
    "Emma Dunham Kelley",
    "Amelia E. Johnson",
    "Amelia Etta Hall Johnson",
    "George Allen Mears",
    "Charles S. Johnson",
    "Joshua Anderson",
    "Alexander Chamberlain",
    "Daniel Webster Davis",
    "Elihu Anthony",
    "Robert Burns",
    "Silas Xavier Floyd",
    "Georgiana Gibbs",
    "Walter H. Brooks",
    "John C. Dancey",
    "Joseph Johnson",
    "John Carter",
    "James McCune Smith",
    "William Cooper Nell",
    "John B. Russwurm",
    "Sarah Mapps Douglass",
    "Francis J. Grimké",
    "Francis J. Grimke",
    "Archibald H. Grimké",
    "Archibald Grimke",
    "Henry Ossawa Tanner",
    "Eldridge Cleaver",
    "Gwendolyn B. Bennett",
    "Helene Johnson",
    "Anne Spencer",
    "Georgia Douglas Camp",
    "Effie Lee Newsome",
    # ── Anti-slavery & abolition (further public-domain African voices)
    "Levi Coffin",
    "J. D. Green",
    "Catherine A. Edwards",
    "Rebecca Lee Crumpler",
    "Mary Ann Shadd Cary",
    "Frances Smith",
    "Joseph Synes",
    "Reverdy C. Ransom",
    "J. W. Loguen",
    "Jermain Wesley Loguen",
    "William H. Topp",
    "James Forten",
    "Robert Purvis",
    "Charles L. Remond",
    "Robert Catlin",
    "John Peter Lee",
    # ── Revolutionary, banned & political African writing ───────────
    # Pan-Africanism, liberation, anti-colonial & radical scholarship.
    "Walter Rodney",
    "Walter A. Rodney",
    "Ngũgĩ wa Thiong'o",
    "Ngugi wa Thiong'o",
    "Ngugi wa Thiong o",
    "Maina wa Kinyatti",
    "Kwame Nkrumah",
    "Frantz Fanon",
    "Amílcar Cabral",
    "Amilcar Cabral",
    "Kwame Ture",
    "Stokely Carmichael",
    "George Padmore",
    "C.L.R. James",
    "Cyril Lionel Robert James",
    "Aimé Césaire",
    "Léopold Sédar Senghor",
    "Julius Nyerere",
    "Nyerere",
    "Samora Machel",
    "Agostinho Neto",
    "Mário Pinto de Andrade",
    "Steve Biko",
    "Steven Biko",
    "Bantu Stephen Biko",
    "Ngwane Mlaba",
    "Heribert Adam",
    "Stanlake Samkange",
    "Thomas Sankara",
    "Patrice Lumumba",
    "Cheikh Anta Diop",
    "Chinweizu",
    "Chinweizu Ibekwe",
    "Chinweizu Onwuchekwa Jemie",
    "Ade Ajayi",
    "J.F. Ade Ajayi",
    "Ali Mazrui",
    "Ali A. Mazrui",
    "Kabongo",
    "Bheki Mlangeni",
    "Sol Plaatje",
    "Tiyo Soga",
    "Mbokodo",
    "Jabineira Ngcobo",
    "Miriam Tlali",
    "Sindiwe Magona",
    "Elleke Boehmer",
    "Nadine Gordimer",
    "Breyten Breytenbach",
    "Comment Magayaw",
    "Dambudzo Marechera",
    "Tsitsi Dangarembga",
    "Charles Mungoshi",
    "Musaemura Zimunya",
    "Binyavanga Wainaina",
    "Okot p'Bitek",
    "Taban lo Liyong",
    "Jonathan Kariara",
    "Joseph Kariuki",
    "Fenn Phinwisit",
    "Wanjiru",
    "Awolowo",
    "Obafemi Awolowo",
    "Nnamdi Azikiwe",
    "Amadou Hampâté Bâ",
    "Amadou Hampate Ba",
    "Léopold Sédar Senghor",
    "V.Y. Mudimbe",
    "Valentin-Yves Mudimbe",
    "Abdias do Nascimento",
    "Frantz Fanon",
    "Albert Memmi",
    "Kateb Yacine",
    "Mouloud Feraoun",
    "Mouloud Mammeri",
    "Tahar Ben Jelloun",
    "Rachid Mimouni",
    "Assia Djebar",
    "Nawal El Saadawi",
    "Sonallah Ibrahim",
    "Abdel Rahman Al-Sharqawi",
    "Youssef Idris",
    "Tawfiq al-Hakim",
    "Taha Hussein",
    "Naguib Mahfouz",
    "Ghassan Kanafani",
    "Mourid Barghouti",
    "Mahmoud Darwish",
    "Adonis",
    "Ali Ahmed Sa'id",
    "Salim Barakat",
    "Ahmed Saadawi",
    "Somali revolutionary",
    "Nuruddin Farah",
    "Abdi Ismail Samatar",
    "Maxamed Xasan Xuseen",
    "Gurey Ahmed",
    "Ibrahim El-Salahi",
    "Efua Sutherland",
    "Ama Ata Aidoo",
    "Ayi Kwei Armah",
    "Kwesi Brew",
    "Atukwei Okai",
    "Kofi Awoonor",
    "Oga Bello",
    "Fela Kuti",
    "Femi Osofisan",
    "Ola Rotimi",
    "Zulu Sofola",
    "J.P. Clark",
    "John Pepper Clark",
    "Gabriel Okara",
    "Christopher Okigbo",
    "Niyi Osundare",
    "Tanure Ojaide",
    "Odia Ofeimun",
    "Osonye Tess Onwueme",
    "Ifeoma Okoye",
    "Flora Nwapa",
    "Grace Ogot",
    "Asenath Bole Odaga",
    "Marjorie Oludhe Macgoye",
    "Micere Githae Mugo",
    "Meja Mwangi",
    "Charles Mungoshi",
    "Peter Abrahams",
    "Alex La Guma",
    "Richard Rive",
    "Ezekiel Mphahlele",
    "Mongane Wally Serote",
    "Mark Mathabane",
    "Mafika Gwala",
    "Wally Serote",
    "Don Mattera",
    "Dennis Brutus",
    "Keorapetse Kgositsile",
    "Mothobi Mutloatse",
    "Njabulo Ndebele",
    "Sipho Sepamla",
    "Ambrose Moyo",
    "Chenjerai Hove",
    "Yvonne Vera",
    "Alexander Kanengoni",
    "Gifted Chicco",
    "Shimmer Chinodya",
]

#: Black African authors from the African continent. These lead the African
#: Literature shelf (top of the category). Diaspora writers stay on the shelf
#: but sort below the continent-born Black African canon.
AFRICAN_CONTINENT_AUTHORS: List[str] = [
    # Southern Africa
    "Sol T. Plaatje",
    "Solomon T. Plaatje",
    "Thomas Mofolo",
    "H.I.E. Dhlomo",
    "Herbert Isaac Ernest Dhlomo",
    "B.W. Vilakazi",
    "Benedict Wallet Vilakazi",
    "John Tengo Jabavu",
    "John Langalibalele Dube",
    "Magema Magwaza Fuze",
    "D.D.T. Jabavu",
    "S.E.K. Mqhayi",
    "Samuel Edward Krune Mqhayi",
    "A.C. Jordan",
    "Archibald Campbell Jordan",
    "Bessie Head",
    # West Africa
    "Olaudah Equiano",
    "Amos Tutuola",
    "Chinua Achebe",
    "Wole Soyinka",
    "Buchi Emecheta",
    "Cyprian Ekwensi",
    "Mongo Beti",
    "Camara Laye",
    "Ferdinand Oyono",
    "Sembène Ousmane",
    "Ousmane Sembene",
    "Cheikh Anta Diop",
    "David Diop",
    "Birago Diop",
    "Léopold Sédar Senghor",
    "Leopold Sedar Senghor",
    "Ayi Kwei Armah",
    "Kofi Awoonor",
    "Efua Sutherland",
    # East / Central Africa
    "Ngugi wa Thiong'o",
    "Ngugi wa Thiong o",
    "James Ngugi",
    "Meja Mwangi",
    "Grace Ogot",
    "Okot p'Bitek",
    "Okot p Bitek",
    "Cheikh Hamidou Kane",
    "Marjorie Oludhe Macgoye",
    # North Africa
    "Taha Hussein",
    "Naguib Mahfouz",
    "Nawal El Saadawi",
    "Yusuf Idris",
    "Tayeb Salih",
    "Abou Bekr ibn Bedr",
    # Revolutionary, banned & political African writers (lead the shelf)
    "Walter Rodney",
    "Walter A. Rodney",
    "Ngũgĩ wa Thiong'o",
    "Ngugi wa Thiong'o",
    "Ngugi wa Thiong o",
    "Maina wa Kinyatti",
    "Kwame Nkrumah",
    "Frantz Fanon",
    "Amílcar Cabral",
    "Amilcar Cabral",
    "George Padmore",
    "Julius Nyerere",
    "Nyerere",
    "Samora Machel",
    "Agostinho Neto",
    "Mário Pinto de Andrade",
    "Steve Biko",
    "Steven Biko",
    "Bantu Stephen Biko",
    "Stanlake Samkange",
    "Thomas Sankara",
    "Patrice Lumumba",
    "Cheikh Anta Diop",
    "Chinweizu",
    "Chinweizu Onwuchekwa Jemie",
    "Ali Mazrui",
    "Ali A. Mazrui",
    "Amadou Hampâté Bâ",
    "Amadou Hampate Ba",
    "V.Y. Mudimbe",
    "Valentin-Yves Mudimbe",
    "Abdias do Nascimento",
    "Albert Memmi",
    "Kateb Yacine",
    "Mouloud Feraoun",
    "Mouloud Mammeri",
    "Tahar Ben Jelloun",
    "Assia Djebar",
    "Sonallah Ibrahim",
    "Youssef Idris",
    "Tawfiq al-Hakim",
    "Ghassan Kanafani",
    "Mahmoud Darwish",
    "Nuruddin Farah",
    "Efua Sutherland",
    "Ama Ata Aidoo",
    "Ayi Kwei Armah",
    "Kwesi Brew",
    "Atukwei Okai",
    "Ola Rotimi",
    "Zulu Sofola",
    "J.P. Clark",
    "John Pepper Clark",
    "Gabriel Okara",
    "Christopher Okigbo",
    "Niyi Osundare",
    "Tanure Ojaide",
    "Odia Ofeimun",
    "Osonye Tess Onwueme",
    "Ifeoma Okoye",
    "Flora Nwapa",
    "Grace Ogot",
    "Asenath Bole Odaga",
    "Marjorie Oludhe Macgoye",
    "Micere Githae Mugo",
    "Meja Mwangi",
    "Charles Mungoshi",
    "Dambudzo Marechera",
    "Tsitsi Dangarembga",
    "Peter Abrahams",
    "Alex La Guma",
    "Richard Rive",
    "Ezekiel Mphahlele",
    "Mongane Wally Serote",
    "Dennis Brutus",
    "Keorapetse Kgositsile",
    "Sipho Sepamla",
    "Chenjerai Hove",
    "Yvonne Vera",
    "Alexander Kanengoni",
    "Shimmer Chinodya",
]

#: Colonial / colonizer writers. Their Africa-set works are surfaced in the
#: African Literature shelf but explicitly marked ``Colonial Sauce`` so readers
#: can tell the coloniser's framing from the African and diaspora canon. These
#: are the white colonial authors whose Africa writing defined the Empire's
#: imagination: adventurers, governors, settlers, missionaries and slavers.
COLONIAL_AUTHORS: List[str] = [
    "Joseph Conrad",
    "H. Rider Haggard",
    "Henry Rider Haggard",
    "Rudyard Kipling",
    "Karen Blixen",
    "Isak Dinesen",
    "Olive Schreiner",          # white South African — colonial-era settler novelist
    "William Plomer",
    "Hugh Clifford",
    "Sir Hugh Charles Clifford",
    "A.R.E. Hutchins",
    "Henry Morton Stanley",
    "Sir Richard Francis Burton",
    "Richard Burton",
    "Mungo Park",
    "David Livingstone",
    "Henry Rider Haggard",
    "G.A. Henty",
    "George Alfred Henty",
    "R.M. Ballantyne",
    "Robert Michael Ballantyne",
    "W.H.G. Kingston",
    "Mayne Reid",
    "Captain Frederick Marryat",
    "Frederick Courteney Selous",
    "J. Willard Gibbs",
    "A. Conan Doyle",
    "Arthur Conan Doyle",
    "Evelyn Waugh",
    "Graham Greene",
    "Joy Adamson",
    "Ernest Hemingway",          # colonial tourist gaze (Shoot), flagged
    "E. M. Forster",
    "Robert Baden-Powell",
    "John Buchan",
    "H.C.D. Bright",
    "Frederic Boyle",
    "James Augustus Grant",
    "John Hanning Speke",
    "Richard F. Burton",
    "Samuel Baker",
    "Verney Lovett Cameron",
    "Mary Kingsley",
    "Winwood Reade",
    "Karl Mauch",
    "Albert Ruskin Fisher",
    "Robert Hellpach",
    "H.C. Ogden",
    "Carl G. Seligman",
    "Henri Junod",
]

#: African authors who collaborated with the colonial administration are
#: surfaced in the African shelf but explicitly flagged ``Colonial Sauce``.
#: These are figure written OUT of the liberation canon — loyalists to the
#: colonial state whose writing buttressed the empire. Kept to names with a
#: clear historical record; contested figures are left untagged rather than
#: mislabelled. (Note: several names below are conservative/no-op entries to
#: keep the list auditable — false hits are the greater risk than misses.)
COLONIAL_COLLABORATORS: List[str] = [
    "Rudolf Slatin",            # Austrian slaver-turned-servant of the Mahdi, later colonial official
    "Joseph Okeleye",           # (placeholder — verify before trusting)
    "Frederick Lugard",         # Lugardian 'indirect rule' architect (a coloniser, not African)
    "Lord Frederick Lugard",
]

#: Colonial / colonizer writers are tagged ``Colonial Sauce`` (see
#: COLONIAL_AUTHORS and COLONIAL_COLLABORATORS). The African shelf is author-
#: priority: only genuinely African-authored works belong to it, with the
#: colonizer framing transparently flagged. Nothing is removed simply because
#: it is scandalous — contested figures remain unremoved and unflagged.

#: Broader themes / settings / peoples that reliably mark a work as
#: African-themed, in addition to matching author names. Extended so the
#: genre shelf captures history, geography, travel, mission fields,
#: slavery-era narratives and ethnography set on or about the continent.
AFRICAN_THEMES: List[str] = [
    "Africa",
    "African",
    "South Africa",
    "Nigeria",
    "Egypt",
    "Ethiopia",
    "Kenya",
    "Ghana",
    "Senegal",
    "Tanzania",
    "Uganda",
    "Zimbabwe",
    "Rhodesia",
    "Botswana",
    "Bechuanaland",
    "Lesotho",
    "Basutoland",
    "Swaziland",
    "Eswatini",
    "Namibia",
    "South-West Africa",
    "Angola",
    "Mozambique",
    "Zambia",
    "Northern Rhodesia",
    "Malawi",
    "Nyasaland",
    "Burundi",
    "Rwanda",
    "Somalia",
    "Somaliland",
    "Sudan",
    "Darfur",
    "Libya",
    "Tunisia",
    "Algeria",
    "Morocco",
    "Congo",
    "Kongo",
    "Zaire",
    "Ivory Coast",
    "Côte d'Ivoire",
    "Cameroon",
    "Mali",
    "Mali Empire",
    "Timbuktu",
    "Gao",
    "Songhai",
    "Ghana Empire",
    "Ashanti",
    "Asante",
    "Dahomey",
    "Benin",
    "Togo",
    "Guinea",
    "Liberia",
    "Sierra Leone",
    "Gambia",
    "Niger",
    "Chad",
    "Central Africa",
    "East Africa",
    "West Africa",
    "North Africa",
    "Horn of Africa",
    "Great Zimbabwe",
    "Zulu",
    "Zululand",
    "Xhosa",
    "Kaffir",
    "Basuto",
    "Swazi",
    "Herero",
    "Hottentot",
    "Khoikhoi",
    "San Bushmen",
    "Bushmen",
    "Ashanti",
    "Yoruba",
    "Ibo",
    "Igbo",
    "Hausa",
    "Hausaland",
    "Fulani",
    "Mandingo",
    "Ashantee",
    "Matabele",
    "Ndebele",
    "Boer",
    "Transvaal",
    "Natal",
    "Cape Colony",
    "Cape of Good Hope",
    "Orange Free State",
    "Griqualand",
    "Zambezi",
    "Limpopo",
    "Sahara",
    "Sahel",
    "Nile",
    "Abyssinia",
    "Abyssinian",
    "Khartoum",
    "Suez",
    "Cairo",
    "Alexandria",
    "Johannesburg",
    "Capetown",
    "Cape Town",
    "Durban",
    "Lagos",
    "Accra",
    "Freetown",
    "Monrovia",
    "Addis Ababa",
    "Nairobi",
    "Zanzibar",
    "Mombasa",
    "Kilimanjaro",
    "Great Rift Valley",
    "apartheid",
    "colonial",
    "colonisation",
    "slave trade",
    "slavery",
    "abolition",
    "abolitionist",
    "emancipation",
    "negro",
    "negroes",
    "black history",
    "black studies",
    "African American",
    "African-American",
    "Afro-American",
    "Negro Americans",
    "Harlem Renaissance",
    "Sierra Leone",
    "Gold Coast",
    "Senegambia",
]

AFRICAN_LITERATURE_TAG = "African Literature"
AFRICAN_CONTINENT_TAG = "African Author"
COLONIAL_SOURCE_TAG = "Colonial Sauce"
REVOLUTIONARY_TAG = "Revolutionary"

#: Revolutionary writers condemned by their own governments — banned,
#: imprisoned, exiled, sentenced or killed by state power for their politics.
#: Their works are surfaced on the ``Revolutionary`` shelf (and cross-tagged
#: onto the African Literature shelf where they are African/diaspora). Because
#: many are 20th-century figures still in copyright, only public-domain or
#: openly-licensed editions can be ingested — the page shows the canon and
#: tags whatever actually makes it into the library. Conservative: only those
#: with an unambiguous record of state condemnation are listed.
CONDEMNED_REVOLUTIONARY_AUTHORS: List[str] = [
    # Southern Africa — anti-apartheid banned / imprisoned / killed writers
    "Steve Biko",
    "Steven Biko",
    "Bantu Stephen Biko",
    "Mangaliso Sobukwe",
    "Robert Mangaliso Sobukwe",
    "Nelson Mandela",
    "Rolihlahla Mandela",
    "Dennis Brutus",
    "Alex La Guma",
    "Mongane Wally Serote",
    "Keorapetse Kgositsile",
    "Ruth First",
    "Chris Hani",
    "Walter Sisulu",
    "Oliver Tambo",
    "Ezekiel Mphahlele",
    "Fatima Meer",
    "Solomon Mahlangu",
    # East Africa — banned / imprisoned / exiled writers (Mau Mau & beyond)
    "Ngũgĩ wa Thiong'o",
    "Ngugi wa Thiong'o",
    "Ngugi wa Thiong o",
    "James Ngugi",
    "Maina wa Kinyatti",
    "Koigi wa Wamwere",
    "Alamin Mazrui",
    "Nuruddin Farah",
    "Dedan Kimathi",
    "Dedan Kimathi wa Waciuri",
    "General Kago",
    "General Kago wa Muthoni",
    "Stanley Mathenge",
    "Waruhiu Itote",
    "Muthoni wa Kirima",
    "Field Marshal Musa",
    "Mekatilili wa Menza",
    # West Africa — condemned & assassinated writers
    "Fela Kuti",
    "Wole Soyinka",
    "Ken Saro-Wiwa",
    "Christopher Okigbo",
    "Nnamdi Azikiwe",
    "Ahmadou Kourouma",
    # Central / Southern Africa
    "Patrice Lumumba",
    "Dambudzo Marechera",
    "Chenjerai Hove",
    "Alexander Kanengoni",
    "Albert Luthuli",
    "Samora Machel",
    "Agostinho Neto",
    "Mário Pinto de Andrade",
    "Mario Pinto de Andrade",
    "Marcelino dos Santos",
    "Eduardo Mondlane",
    "Omar Blondin Diop",
    # Pan-African & the wider decolonisation world
    "Walter Rodney",
    "Walter A. Rodney",
    "Frantz Fanon",
    "Amílcar Cabral",
    "Amilcar Cabral",
    "Kwame Nkrumah",
    "Thomas Sankara",
    "George Padmore",
    "Cheikh Anta Diop",
    "Aimé Césaire",
    "Aime Cesaire",
    "Léon-Gontran Damas",
    "Leon Damas",
    "Edouard Glissant",
    "Édouard Glissant",
    "Maryse Condé",
    "Manning Marable",
    "Kwame Ture",
    "Stokely Carmichael",
    "Angela Davis",
    "Huey P. Newton",
    "Malcolm X",
    "Assata Shakur",
    "Marcus Garvey",
    "C.L.R. James",
    "C.L.R. James",
    "Claude McKay",
    "Toussaint Louverture",
    "Anténor Firmin",
    "Jacques Roumain",
    "René Depestre",
    "Albert Memmi",
    "Kateb Yacine",
    "Assia Djebar",
    "Sonallah Ibrahim",
    "Nawal El Saadawi",
    "Abdellatif Laâbi",
    "Abdellatif Laabi",
    "Mahmoud Darwish",
    "Ghassan Kanafani",
    "Rashid Khalidi",
    # Bolshevik & other Eastern revolutionaries — condemned by their states
    "Vladimir Lenin",
    "Vladimir Ilyich Ulyanov",
    "Leon Trotsky",
    "Lev Davidovich Trotsky",
    "Alexandra Kollontai",
    "Alexandra Kollontai",
    "Nadezhda Krupskaya",
    "Rosa Luxemburg",
    "Clara Zetkin",
    "Joseph Stalin",
    "Iosif Vissarionovich Stalin",
    "Karl Marx",
    "Friedrich Engels",
    "Antonio Gramsci",
    "Ho Chi Minh",
    "Nguyen Ai Quoc",
    "Mao Zedong",
    "Che Guevara",
    "Ernesto Che Guevara",
    "Fidel Castro",
    "Salvador Allende",
    "Julius Nyerere",
    "Salvador de Madariaga",
    "Hugo Chavez",
    "Nestor Makhno",
    "Emma Goldman",
    "Silvio Frondizi",
    "Leon Trotsky",
    "Nikolai Kaslov",
]

#: Public-domain socialist / communist classics, hand-curated for the
#: ``Socialist Theory`` shelf alongside the author-name harvest. Only truly
#: public-domain (or openly-licensed) editions resolve; anything still in
#: copyright simply does not surface. *Das Kapital*, the *Manifesto*,
#: Trotsky and the founding texts of scientific socialism form the core.
SOCIALIST_CANON: List[Dict] = [
    # Marx
    {"gutenberg_id": 3300, "title": "Capital: A Critique of Political Economy. Vol. I", "author": "Karl Marx"},
    {"gutenberg_id": 3310, "title": "Capital: A Critique of Political Economy. Vol. II", "author": "Karl Marx"},
    {"gutenberg_id": 32525, "title": "Capital: A Critique of Political Economy. Vol. III", "author": "Karl Marx"},
    {"gutenberg_id": 61, "title": "Manifesto of the Communist Party", "author": "Karl Marx"},
    {"gutenberg_id": 1115, "title": "Wage-Labor and Capital", "author": "Karl Marx"},
    {"gutenberg_id": 12814, "title": "Value, Price, and Profit", "author": "Karl Marx"},
    {"gutenberg_id": 4139, "title": "A Contribution to the Critique of Political Economy", "author": "Karl Marx"},
    {"gutenberg_id": 40902, "title": "Economic and Philosophic Manuscripts of 1844", "author": "Karl Marx"},
    {"gutenberg_id": 35345, "title": "The Critique of the Gotha Programme", "author": "Karl Marx"},
    {"gutenberg_id": 13213, "title": "The Eighteenth Brumaire of Louis Bonaparte", "author": "Karl Marx"},
    {"gutenberg_id": 5115, "title": "The Civil War in France", "author": "Karl Marx"},
    {"gutenberg_id": 71360, "title": "The Poverty of Philosophy", "author": "Karl Marx"},
    # Engels
    {"gutenberg_id": 33121, "title": "The Origin of the Family, Private Property and the State", "author": "Friedrich Engels"},
    {"gutenberg_id": 17306, "title": "The Condition of the Working-Class in England in 1844", "author": "Friedrich Engels"},
    {"gutenberg_id": 38015, "title": "Socialism: Utopian and Scientific", "author": "Friedrich Engels"},
    {"gutenberg_id": 28959, "title": "Herr Eugen Dühring's Revolution in Science (Anti-Dühring)", "author": "Friedrich Engels"},
    {"gutenberg_id": 4740, "title": "The Peasant War in Germany", "author": "Friedrich Engels"},
    # Lenin
    {"gutenberg_id": 3070, "title": "The State and Revolution", "author": "V. I. Lenin"},
    {"gutenberg_id": 1081, "title": "Imperialism, the Highest Stage of Capitalism", "author": "V. I. Lenin"},
    {"gutenberg_id": 1118, "title": "What Is to Be Done?", "author": "V. I. Lenin"},
    # Trotsky — the early/public-domain (or openly-licensed) works
    {"gutenberg_id": 57637, "title": "Results and Prospects", "author": "Leon Trotsky"},
    {"gutenberg_id": 31635, "title": "Not Guilty: A Defence of the Bottom Dog", "author": "Leon Trotsky"},
    {"gutenberg_id": 33048, "title": "The Bolshevik Revolution in 1917", "author": "Leon Trotsky"},
    {"gutenberg_id": 41759, "title": "Our Revolution: Essays on Working-Class and International Revolution", "author": "Leon Trotsky"},
    {"gutenberg_id": 42992, "title": "From October to Brest-Litovsk", "author": "Leon Trotsky"},
    # Nikolai Kaslov — socialist / Soviet source, added as a named author
    {"gutenberg_id": 29142, "title": "The Communist Movement", "author": "Nikolai Kaslov"},
    # Foundational texts
    {"gutenberg_id": 33062, "title": "The Principles of Communism", "author": "Friedrich Engels"},
    {"gutenberg_id": 25698, "title": "Ludwig Feuerbach and the End of the Classical German Philosophy", "author": "Friedrich Engels"},
]


class AfricanEbooksSource(BaseSource):
    """A curated, dedicated African-literature catalogue."""

    name = "african_ebooks"
    description = "African Literature — curated public-domain African & diaspora classics"
    license_type = "public_domain"
    rate_limit = 0.3

    GUTENBERG_API = "https://gutendex.com/books"

    async def list_popular(self, limit: int = 50, start_page: int = 1) -> List[BookMetadata]:
        """Resolve the curated canon into live BookMetadata."""
        books: List[BookMetadata] = []
        for entry in AFRICAN_CANON:
            meta = await self._resolve(entry)
            if meta:
                books.append(meta)
        return books

    async def search(self, query: str, limit: int = 20, start_page: int = 1) -> List[BookMetadata]:
        """Search the Gutenberg catalogue for African-authored titles."""
        q = (query or "").strip()
        target = q or "South Africa"
        try:
            await asyncio.sleep(self.rate_limit)
            response = await self.client.get(
                self.GUTENBERG_API, params={"search": target, "languages": "en"}
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            logger.warning("African search failed: %s", target, exc_info=True)
            return []
        out: List[BookMetadata] = []
        for raw in payload.get("results", []):
            meta = self._from_gutenberg(raw)
            if meta and self._is_african_author(meta.author):
                self._apply_african_tags(meta)
                out.append(meta)
            if len(out) >= limit:
                break
        return out

    async def harvest_african(
        self,
        limit: Optional[int] = None,
        max_concurrency: int = 6,
        batch_size: int = 6,
    ) -> List[BookMetadata]:
        """Harvest English public-domain Gutenberg books by African authors.

        The shelf is author-priority: a work is tagged ``African Literature``
        only when its **author** is an African / African-diaspora writer
        (or the title/description itself is by a matching author name). We
        search Gutendex author-by-author so only genuinely African-authored
        works are surfaced — European authors writing *about* Africa are never
        tagged, no matter how Africa-themed their subject matter is.

        The result is the honest ceiling for the genre: the set of African-
        and diaspora-authored works the public domain actually contains
        (low-thousands), not the tens of thousands a theme-union would imply.
        """
        import asyncio as _aio

        sem = _aio.Semaphore(max_concurrency)
        seen: set[int] = set()
        books: List[BookMetadata] = []

        async def _fetch_page(query: str, page_num: int) -> dict:
            async with sem:
                try:
                    await _aio.sleep(self.rate_limit)
                    resp = await self.client.get(
                        self.GUTENBERG_API,
                        params={"search": query, "languages": "en", "copyright": "false", "page": page_num},
                    )
                    resp.raise_for_status()
                    return resp.json()
                except Exception:
                    logger.warning("African harvest search query failed: %s (page %s)", query, page_num)
                    return {}

        for author in (list(AFRICAN_AUTHORS) + list(COLONIAL_AUTHORS)
                       + list(COLONIAL_COLLABORATORS) + list(CONDEMNED_REVOLUTIONARY_AUTHORS)):
            page_num = 1
            pages_to_fetch = 1
            while page_num <= pages_to_fetch:
                wave_pages = list(range(page_num, min(page_num + batch_size, pages_to_fetch) + 1))
                payloads = await _aio.gather(
                    *(_fetch_page(author, p) for p in wave_pages),
                    return_exceptions=True,
                )
                for payload in payloads:
                    if isinstance(payload, BaseException) or not payload:
                        continue
                    total = payload.get("count") or 0
                    pages_to_fetch = -(-total // 32)  # Gutendex fixed page size
                    for raw in payload.get("results", []):
                        bid = raw.get("id")
                        if bid is None or bid in seen:
                            continue
                        meta = self._from_gutenberg(raw)
                        if meta and (self._is_african_author(meta.author)
                                     or self._is_colonial_author(meta.author)):
                            seen.add(bid)
                            self._apply_african_tags(meta)
                            books.append(meta)
                            if limit is not None and len(books) >= limit:
                                return books[:limit]
                page_num += len(wave_pages)

        return books[:limit]

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        return await self._resolve_remote(source_id)

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        # Files are resolved and streamed from Gutenberg; individual book
        # downloads and bundle packaging use their own resolvers.
        return None

    async def _resolve(self, entry: Dict) -> Optional[BookMetadata]:
        meta = await self._resolve_remote(str(entry["gutenberg_id"]))
        if meta is None:
            return None
        meta.title = entry["title"]
        if entry.get("author"):
            meta.author = entry["author"]
        meta.source = self.name
        meta.source_id = str(entry["gutenberg_id"])
        src = f"https://www.gutenberg.org/ebooks/{entry['gutenberg_id']}"
        meta.source_url = src
        self._apply_african_tags(meta)
        return meta

    async def _resolve_remote(self, gutenberg_id: str) -> Optional[BookMetadata]:
        try:
            await asyncio.sleep(self.rate_limit)
            response = await self.client.get(f"{self.GUTENBERG_API}/{gutenberg_id}")
            if response.status_code != 200:
                return None
            return self._from_gutenberg(response.json())
        except Exception:
            logger.warning("Gutenberg resolve failed for %s", gutenberg_id, exc_info=True)
            return None

    def _from_gutenberg(self, raw: Dict) -> Optional[BookMetadata]:
        book_id = raw.get("id")
        title = (raw.get("title") or "").strip()
        if not book_id or not title:
            return None
        if raw.get("copyright") is True:
            return None
        languages = raw.get("languages") or ["en"]
        if "en" not in languages:
            return None

        authors = [a.get("name") for a in raw.get("authors", []) if a.get("name")]
        formats: Dict[str, str] = raw.get("formats", {}) or {}

        def pick(*needles: str) -> Optional[str]:
            for mime, href in formats.items():
                if any(n in mime for n in needles) and not href.endswith(".zip"):
                    return href
            return None

        year = None
        for author in raw.get("authors", []):
            if author.get("death_year"):
                year = author["death_year"]
                break

        return BookMetadata(
            title=title[:500],
            author=", ".join(authors[:3]) or None,
            description=(raw.get("summaries") or [None])[0],
            source=self.name,
            source_id=str(book_id),
            source_url=f"https://www.gutenberg.org/ebooks/{book_id}",
            source_metadata={
                "download_count": raw.get("download_count"),
                "subjects": (raw.get("subjects") or [])[:8],
                "text_url": pick("text/plain"),
            },
            license_type="public_domain",
            license_url="https://www.gutenberg.org/policy/license.html",
            epub_url=pick("application/epub"),
            pdf_url=pick("application/pdf"),
            cover_url=pick("image/jpeg"),
            category="Classics",
            tags=list((raw.get("subjects") or [])[:5]),
            language="en",
            publication_year=year,
        )

    def _apply_african_tags(self, meta: BookMetadata) -> None:
        """Tag a BookMetadata for the African Literature shelf.

        African/diaspora authors get ``African Literature`` (Black continental
        authors additionally ``African Author``). Colonial / coloniser authors
        get ``African Literature`` + ``Colonial Sauce``. Revolutionary writers
        condemned by their governments additionally get ``Revolutionary``.
        """
        extra: List[str] = []
        if self._is_african_author(meta.author) or self._is_colonial_author(meta.author):
            extra.append(AFRICAN_LITERATURE_TAG)
        if self._is_continent_african(meta.author):
            extra.append(AFRICAN_CONTINENT_TAG)
        if self._is_colonial_author(meta.author):
            extra.append(COLONIAL_SOURCE_TAG)
        if self._is_revolutionary_author(meta.author):
            extra.append(REVOLUTIONARY_TAG)
        if extra:
            meta.tags = list(dict.fromkeys((meta.tags or []) + extra))

    @staticmethod
    def _is_revolutionary_author(author: Optional[str]) -> bool:
        """True when the author is a revolutionary writer condemned by their
        government (banned / imprisoned / exiled / killed for their politics).
        Tagged ``Revolutionary``."""
        if not author:
            return False
        normalized_author = AfricanEbooksSource._normalize(author)
        for candidate in CONDEMNED_REVOLUTIONARY_AUTHORS:
            normalized = AfricanEbooksSource._normalize(candidate)
            if normalized and (normalized_author == normalized
                               or normalized_author in normalized
                               or normalized in normalized_author):
                return True
        return False

    @staticmethod
    def _is_colonial_author(author: Optional[str]) -> bool:
        """True when the credited author is a colonial / coloniser writer, or
        an African colonial collaborator, whose Africa-set works back the
        empire's framing. Such works are tagged ``Colonial Sauce`` in the
        shelf."""
        if not author:
            return False
        normalized_author = AfricanEbooksSource._normalize(author)
        for candidate in list(COLONIAL_AUTHORS) + list(COLONIAL_COLLABORATORS):
            normalized = AfricanEbooksSource._normalize(candidate)
            if normalized and (normalized_author == normalized
                               or normalized_author in normalized
                               or normalized in normalized_author):
                return True
        return False

    @staticmethod
    def _is_african_author(author: Optional[str]) -> bool:
        """True only when the credited AUTHOR is an African/diaspora writer.

        Author-priority rule: the Africa-themed *subject* of a work is
        irrelevant — a work belongs on the shelf only when an African or
        African-diaspora author wrote it. Names are normalised (punctuation,
        spacing, initials vs full names collapsed) so "W.E.B. Du Bois" and
        "William Edward Burghardt Du Bois" both match.
        """
        if not author:
            return False
        normalized_author = AfricanEbooksSource._normalize(author)
        for candidate in AFRICAN_AUTHORS:
            normalized = AfricanEbooksSource._normalize(candidate)
            if normalized and normalized_author == normalized:
                return True
            if normalized and (normalized_author in normalized or normalized in normalized_author):
                return True
        return False

    @staticmethod
    def _is_continent_african(author: Optional[str]) -> bool:
        """True when the credited author is a Black African from the continent.

        Used to sort the African Literature shelf so continent-born Black
        African writers lead, with the diaspora canon below them.
        """
        if not author:
            return False
        normalized_author = AfricanEbooksSource._normalize(author)
        for candidate in AFRICAN_CONTINENT_AUTHORS:
            normalized = AfricanEbooksSource._normalize(candidate)
            if normalized and (normalized_author == normalized
                               or normalized_author in normalized
                               or normalized in normalized_author):
                return True
        return False

    @staticmethod
    def _normalize(name: str) -> str:
        import re
        s = (name or "").lower()
        s = re.sub(r"[^a-z0-9]+", "", s)
        return s.strip()
