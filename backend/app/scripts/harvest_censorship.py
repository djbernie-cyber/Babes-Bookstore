"""Harvest suppression *records* from Wikimedia list articles.

Why this exists
---------------
The catalogue carried 23 hand-curated suppression records. A real censorship
map needs volume, and hand-typing a few hundred entries produces both
fatigue-scale typos and a map that quietly stops at 1950.

Wikimedia's list articles ("List of books banned in India", "Book censorship
in the Republic of Ireland", ...) already are the map: they are curated tables
with exactly the columns this table has -- work, author, year, jurisdiction,
reason. Harvesting them buys volume *and* an audit trail, because every row
carries the revision it came from.

What this is and is not
-----------------------
This records the *fact of suppression*: a work, an author, a date, a
jurisdiction, and the documented reason. That is bibliographic and historical
fact, freely redistributable, and it is not the same thing as shipping the
book. Nothing here attaches a file to a work. A record whose book is still in
copyright stays a record with ``book_id = NULL`` and a link to a legitimate
copy, which is what the archive is for: explain the ban, don't launder it.

Two rules keep this honest, and both are load-bearing:

1. Every record stores the exact revision permalink it was read from, so any
   row can be checked against its source.
2. A row is never given an invented reason. If the source gives notes, they
   are used. If it doesn't, the reason is a neutral locator that asserts
   nothing beyond what the source itself asserts.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
import time
from typing import Iterable, Optional

import httpx
import lxml.html as LH

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "babes-bookstore-censorship-map/1.0 (research; contact ops)"

#: Articles are discovered by search, then filtered -- "List of books banned
#: in the Soviet Union" is in scope, "List of banned films" is not.
ARTICLE_PATTERNS = (
    re.compile(r"list of .*books banned", re.I),
    re.compile(r"list of .*books prohibited", re.I),
    re.compile(r"list of .*challenged books", re.I),
    re.compile(r"list of .*authors banned", re.I),
    re.compile(r"book censorship (?:in|by|across)", re.I),
    re.compile(r"banned books week", re.I),
    re.compile(r"^book banning\b", re.I),
    re.compile(r"censorship of books", re.I),
)
EXCLUDE = re.compile(r"video games|songs|films|movies|tv|comics|magazines|newspapers|"
                     r"plays|paintings|albums|podcast|web ?site|article", re.I)

#: Column synonyms -> canonical field. Wikipedia tables are inconsistently
#: headed, and the same article changes its header over time.
FIELD_SYNONYMS = {
    "work": "work_title", "book": "work_title", "title": "work_title",
    "work s": "work_title", "novel": "work_title", "name of work": "work_title",
    "author": "work_author", "writer": "work_author", "author s": "work_author",
    "by": "work_author", "author name": "work_author",
    "date": "banned_since", "year": "banned_since", "year banned": "banned_since",
    "date banned": "banned_since", "banned": "banned_since", "from": "banned_since",
    "state s": "subdivision", "state": "subdivision", "region": "subdivision",
    "province": "subdivision", "notes": "ban_reason", "note": "ban_reason",
    "reason": "ban_reason", "details": "ban_reason", "comment": "ban_reason",
    "description": "ban_reason", "circumstances": "ban_reason",
}

#: ISO 3166-1 alpha-2. The column is NOT NULL and 2 chars, and the archive
#: already uses "X" for transnational, so unmapped jurisdictions go there
#: rather than being invented.
ISO2 = {
    "US": 1, "GB": 1, "UK": 1, "IN": 1, "ZA": 1, "NG": 1, "KE": 1, "GH": 1,
    "TZ": 1, "UG": 1, "ZW": 1, "ZM": 1, "MW": 1, "BW": 1, "NA": 1, "ET": 1,
    "EG": 1, "FR": 1, "DE": 1, "IT": 1, "ES": 1, "PT": 1, "NL": 1, "BE": 1,
    "RU": 1, "SU": 1, "CN": 1, "JP": 1, "AU": 1, "CA": 1, "NZ": 1, "IE": 1,
    "BR": 1, "MX": 1, "AR": 1, "CL": 1, "CO": 1, "PE": 1, "USSR": 0, "GR": 1,
    "AT": 1, "CH": 1, "UA": 1, "RS": 1, "BG": 1, "HR": 1, "SI": 1, "SK": 1,
    "LT": 1, "LV": 1, "EE": 1, "IS": 1, "SE": 1, "NO": 1, "DK": 1, "FI": 1,
    "PL": 1, "CZ": 1, "SKC": 0, "HU": 1, "RO": 1, "TR": 1, "IL": 1, "IR": 1,
    "SA": 1, "AE": 1, "QA": 1, "KW": 1, "OM": 1, "PK": 1, "BD": 1, "LK": 1,
    "NP": 1, "MM": 1, "TH": 1, "VN": 1, "ID": 1, "MY": 1, "SG": 1, "PH": 1,
    "KR": 1, "KP": 1, "TW": 1, "HK": 1, "AF": 1, "AL": 1, "BA": 1, "MK": 1,
    "ME": 1, "XK": 0, "CY": 1, "MT": 1, "LU": 1, "SI2": 0, "BY": 1, "MD": 1,
    "AM": 1, "AZ": 1, "GE": 1, "KZ": 1, "UZ": 1, "KG": 1, "TJ": 1, "TM": 1,
    "MN": 1, "FJ": 1, "PG": 1, "CR": 1, "PY": 1, "UY": 1, "EC": 1, "BO": 1,
    "CU": 1, "DO": 1, "GT": 1, "HN": 1, "NI": 1, "PA": 1, "SV": 1, "JM": 1,
    "TT": 1, "ZW2": 0, "GQ": 1, "CM": 1, "CI": 1, "SN": 1, "ML": 1, "BF": 1,
    "NE": 1, "TD": 1, "SD": 1, "SS": 1, "SO": 1, "DJ": 1, "ER": 1, "GH2": 0,
    "SC": 1, "MU": 1, "YT": 1, "RE": 1, "MG": 1, "MZ": 1, "AO": 1, "CD": 1,
    "CG": 1, "GA": 1, "GQ2": 0, "CV": 1, "GW": 1, "SL": 1, "LR": 1, "TG": 1,
    "BJ": 1, "MR": 1, "GN": 1, "RW": 1, "BI": 1, "MW2": 0, "SZ": 1, "LS": 1,
}
#: Name -> code, for jurisdiction columns and article titles.
NAME2ISO = {
    "united states": "US", "america": "US", "usa": "US", "u.s.": "US",
    "u.s.a.": "US", "united states of america": "US", "south carolina": "US",
    "california": "US", "new york": "US", "texas": "US", "alabama": "US",
    "united kingdom": "GB", "britain": "GB", "great britain": "GB",
    "england": "GB", "scotland": "GB", "wales": "GB", "northern ireland": "GB",
    "india": "IN", "british india": "IN", "south africa": "ZA", "nigeria": "NG",
    "kenya": "KE", "ghana": "GH", "tanzania": "TZ", "uganda": "UG",
    "zimbabwe": "ZW", "rhodesia": "ZW", "zambia": "ZM", "malawi": "MW",
    "botswana": "BW", "namibia": "NA", "ethiopia": "ET", "eritrea": "ER",
    "egypt": "EG", "sudan": "SD", "somalia": "SO", "liberia": "LR",
    "sierra leone": "SL", "guinea": "GN", "senegal": "SN", "mali": "ML",
    "niger": "NE", "chad": "TD", "cameroon": "CM", "ivory coast": "CI",
    "cote d'ivoire": "CI", "ghana2": "GH", "congo": "CD", "drc": "CD",
    "gabon": "GA", "angola": "AO", "mozambique": "MZ", "madagascar": "MG",
    "france": "FR", "germany": "DE", "west germany": "DE", "east germany": "DE",
    "nazi germany": "DE", "italy": "IT", "vatican": "IT", "holy see": "IT",
    "spain": "ES", "portugal": "PT", "netherlands": "NL", "belgium": "BE",
    "russia": "RU", "soviet union": "RU", "ussr": "RU", "china": "CN",
    "japan": "JP", "australia": "AU", "canada": "CA", "new zealand": "NZ",
    "ireland": "IE", "republic of ireland": "IE", "brazil": "BR",
    "mexico": "MX", "argentina": "AR", "chile": "CL", "colombia": "CO",
    "peru": "PE", "greece": "GR", "austria": "AT", "switzerland": "CH",
    "ukraine": "UA", "serbia": "RS", "yugoslavia": "RS", "bulgaria": "BG",
    "croatia": "HR", "slovenia": "SI", "slovakia": "SK", "lithuania": "LT",
    "latvia": "LV", "estonia": "EE", "iceland": "IS", "sweden": "SE",
    "norway": "NO", "denmark": "DK", "finland": "FI", "poland": "PL",
    "czech republic": "CZ", "czechoslovakia": "CZ", "hungary": "HU",
    "romania": "RO", "turkey": "TR", "israel": "IL", "iran": "IR",
    "saudi arabia": "SA", "united arab emirates": "AE", "qatar": "QA",
    "kuwait": "KW", "oman": "OM", "pakistan": "PK", "bangladesh": "BD",
    "sri lanka": "LK", "nepal": "NP", "myanmar": "MM", "burma": "MM",
    "thailand": "TH", "vietnam": "VN", "indonesia": "ID", "malaysia": "MY",
    "singapore": "SG", "philippines": "PH", "south korea": "KR",
    "north korea": "KP", "taiwan": "TW", "hong kong": "HK",
    "afghanistan": "AF", "albania": "AL", "bosnia": "BA", "macedonia": "MK",
    "montenegro": "ME", "kosovo": "XK", "cyprus": "CY", "malta": "MT",
    "luxembourg": "LU", "belarus": "BY", "moldova": "MD", "armenia": "AM",
    "azerbaijan": "AZ", "georgia": "GE", "kazakhstan": "KZ", "uzbekistan": "UZ",
    "kyrgyzstan": "KG", "tajikistan": "TJ", "turkmenistan": "TM",
    "mongolia": "MN", "fiji": "FJ", "papua new guinea": "PG",
    "costa rica": "CR", "paraguay": "PY", "uruguay": "UY", "ecuador": "EC",
    "bolivia": "BO", "cuba": "CU", "dominican republic": "DO",
    "guatemala": "GT", "honduras": "HN", "nicaragua": "NI", "panama": "PA",
    "el salvador": "SV", "jamaica": "JM", "trinidad and tobago": "TT",
    "equatorial guinea": "GQ", "djibouti": "DJ", "mauritania": "MR",
    "gambia": "GM", "guinea-bissau": "GW", "comoros": "KM", "seychelles": "SC",
    "mauritius": "MU", "eswatini": "SZ", "lesotho": "LS", "burundi": "BI",
    "rwanda": "RW", "benin": "BJ", "togo": "TG", "cabinda": "CD",
    "british empire": "GB", "colonial": "X", "worldwide": "X",
    "global": "X", "international": "X", "transnational": "X",
}
#: Subnational values that imply a parent country we can name precisely.
SUBDIV2ISO = {
    "sindh": "IN", "punjab": "IN", "uttar pradesh": "IN", "maharashtra": "IN",
    "west bengal": "IN", "tamil nadu": "IN", "kerala": "IN", "gujarat": "IN",
    "rajasthan": "IN", "madhya pradesh": "IN", "bihar": "IN", "karnataka": "IN",
    "andhra pradesh": "IN", "telangana": "IN", "assam": "IN", "odisha": "IN",
    "orissa": "IN", "haryana": "IN", "himachal pradesh": "IN", "uttarakhand": "IN",
    "jammu and kashmir": "IN", "goa": "IN", "chhattisgarh": "IN", "jharkhand": "IN",
    "transvaal": "ZA", "orange free state": "ZA", "cape province": "ZA",
    "natal": "ZA", "zuluuland": "ZA", "gold coast": "GH", "ashanti": "GH",
    "northern rhodesia": "ZM", "southern rhodesia": "ZW", "nysaland": "MW",
    "eastern nigeria": "NG", "western nigeria": "NG", "northern nigeria": "NG",
    "southern nigeria": "NG", "kenya colony": "KE", "uganda protectorate": "UG",
    "british east africa": "KE", "swaziland": "SZ", "bechuanaland": "BW",
    "basutoland": "LS", "nyasaland": "MW", "griqualand": "ZA",
    "scotland": "GB", "wales": "GB", "england": "GB", "northern ireland": "GB",
    "yorkshire": "GB", "london": "GB", "manchester": "GB", "birmingham": "GB",
    "california": "US", "new york": "US", "texas": "US", "south carolina": "US",
    "alabama": "US", "kentucky": "US", "georgia": "US", "ohio": "US",
    "illinois": "US", "maine": "US", "iowa": "US", "arizona": "US",
    "connecticut": "US", "nebraska": "US", "new jersey": "US", "utah": "US",
    "washington": "US", "wisconsin": "US", "vermont": "US", "colorado": "US",
    "minnesota": "US", "missouri": "US", "tennessee": "US", "indiana": "US",
}
STATUS_BY_ARTICLE = (
    (re.compile(r"challenged|contested|attempted", re.I), "contested"),
    (re.compile(r"restricted|censored|barred|prohibited from import", re.I), "restricted"),
)


@dataclass
class Harvested:
    work_title: str
    work_author: Optional[str]
    banned_since: Optional[str]
    country_code: str
    ban_reason: str
    source_url: str
    status: str = "banned"
    country_name: Optional[str] = None
    work_year: Optional[str] = None
    notes: Optional[str] = None
    verified_by: str = "harvest:wikipedia"
    extra: dict = field(default_factory=dict)

    def key(self) -> tuple:
        """Identity for idempotent re-runs.

        Deliberately excludes the reason text: articles get reworded, and a
        reworded reason must not create a second copy of the same suppression.
        """
        norm = lambda s: re.sub(r"[^a-z0-9]+", "", (s or "").lower())
        return (norm(self.work_title), self.country_code, norm(self.banned_since))


def _text(el) -> str:
    return " ".join(el.text_content().split()).strip()


def _clean(s: Optional[str]) -> Optional[str]:
    """Strip the wikitable cruft that survives text_content().

    Rowspans leave empty cells, refs render as bracketed numbers, and several
    tables carry a leading footnote marker. None of that is data.
    """
    if not s:
        return None
    s = re.sub(r"\[\s*\d+\s*\]", "", s)          # [1], [12] citation markers
    s = re.sub(r"\[[a-z]\]", "", s)                # [a] lettered refs
    s = re.sub(r"\s+", " ", s).strip(" ;|·,")
    s = s.replace("\xa0", " ")
    return s or None


def _is_junk(s: str) -> bool:
    """Navbox/CSS rows that ``read_html``-style parsers always pick up.

    The navbox table on these pages has a single cell containing an entire
    stylesheet, and the production/consumption boxes are links, not records.
    """
    if not s or len(s) > 200:
        return True
    if "mw-parser-output" in s or "navbar" in s.lower():
        return True
    if s.count("{") > 2 or "background" in s.lower() or "font-size" in s.lower():
        return True
    return False


def _map_header(cells: Iterable[str]) -> dict:
    out = {}
    for idx, raw in enumerate(cells):
        h = re.sub(r"[^a-z' ]+", "", (raw or "").lower()).strip()
        h = re.sub(r"\s+", " ", h)
        for syn, field in FIELD_SYNONYMS.items():
            if h == syn or h == syn.replace("'", "'s"):
                out[idx] = field
                break
        else:
            if h in ("work s", "book s", "title s"):
                out[idx] = "work_title"
    return out


def resolve_iso(name: Optional[str], fallback: str = "X") -> tuple:
    """Return ``(code, display_name)`` for a jurisdiction string."""
    if not name:
        return fallback, None
    n = name.strip().lower().strip(".,")
    n = re.sub(r"\(.*?\)", "", n).strip()
    if not n:
        return fallback, None
    if len(n) == 2 and n.upper() in ISO2 and n.upper() != "XK":
        return n.upper(), None
    if n in NAME2ISO:
        code = NAME2ISO[n]
        return (code, name.strip() if code != "X" else None)
    if n in SUBDIV2ISO:
        return SUBDIV2ISO[n], name.strip()
    # "England and Wales", "United Kingdom and Ireland" style multi-jurisdiction
    for part in re.split(r"\band\b|,|/", n):
        p = part.strip()
        if p in NAME2ISO and NAME2ISO[p] != "X":
            return NAME2ISO[p], p.title()
        if p in SUBDIV2ISO:
            return SUBDIV2ISO[p], p.title()
    return fallback, None


def country_from_article(title: str) -> tuple:
    """Derive the jurisdiction from the article's own title.

    "List of books banned in India" -> IN. This is the article's declared
    scope, so it is a better attribution than guessing from row contents.
    """
    m = re.search(r"\b(?:in|by|of)\s+(.+)$", re.sub(r"^List of\s+", "", title, flags=re.I), re.I)
    cand = m.group(1) if m else title
    cand = re.sub(r"\b(the|a|an)\b", " ", cand, flags=re.I).strip()
    return resolve_iso(cand, "X")


def discover_articles(client: httpx.Client, limit: int = 60) -> list:
    """Find in-scope list articles by search, then filter by title."""
    QUERIES = (
        "list of books banned",
        "book censorship in country",
        "books banned in",
        "authors banned",
        "book banning index",
        "prohibited books",
        "books burned banned",
    )
    found, cont = {}, None
    while len(found) < limit:
        params = {"action": "query", "list": "search",
                  "srsearch": QUERIES[cont % len(QUERIES)] if isinstance(cont, int) else QUERIES[0],
                  "format": "json", "srlimit": "50"}
        if cont:
            params["sroffset"] = cont
        data = (_get(client, params) or {}).get("query")
        if not data:
            break
        for s in data["search"]:
            t = s["title"]
            if EXCLUDE.search(t) or t in found:
                continue
            if any(p.search(t) for p in ARTICLE_PATTERNS):
                found[t] = s.get("pageid")
        if "continue" not in data or not data["continue"]:
            break
        cont = data["continue"]["sroffset"]
    return sorted(found)


def _get(client: httpx.Client, params: dict, tries: int = 5) -> Optional[dict]:
    """One API call, with backoff.

    The first version of this made a request per article and walked straight
    into a 429 that killed the whole harvest. Wikimedia asks for a serial
    request rate and a descriptive User-Agent; both are honoured here, and a
    429 is retried rather than raised, because losing a 13-article run to a
    throttle is the difference between a map and no map.
    """
    delay = 2.0
    for attempt in range(tries):
        r = client.get(API, params=params, timeout=90)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 503, 500):
            wait = float(r.headers.get("Retry-After") or delay)
            time.sleep(min(wait, 30))
            delay *= 2
            continue
        return None
    return None


def _permalinks(client: httpx.Client, titles: list) -> dict:
    """Resolve revision ids for many articles in few calls.

    The API accepts pipe-joined titles, so this is 25 titles per request
    instead of one request per title.
    """
    out = {}
    for i in range(0, len(titles), 25):
        batch = titles[i:i + 25]
        data = _get(client, {"action": "query", "prop": "revisions", "rvprop": "ids",
                             "titles": "|".join(batch), "format": "json",
                             "formatversion": "2", "redirects": "1"})
        if not data:
            continue
        for page in data.get("query", {}).get("pages", []):
            if page.get("missing"):
                continue
            rev = (page.get("revisions") or [{}])[0].get("revid")
            title = page.get("title")
            if rev and title:
                out[title] = (f"https://en.wikipedia.org/w/index.php?"
                              f"title={title.replace(' ', '_')}&oldid={rev}")
        time.sleep(0.4)
    return out


def parse_article(client: httpx.Client, title: str, permalink: str) -> list:
    """Extract suppression records from every usable table on a page."""
    data = _get(client, {"action": "parse", "page": title, "prop": "text",
                         "format": "json", "formatversion": "2"})
    time.sleep(0.6)
    body = (data or {}).get("parse", {}).get("text")
    if not body:
        return []
    doc = LH.fromstring(body)
    base_code, base_name = country_from_article(title)

    out, seen_local = [], set()
    for table in doc.xpath("//table"):
        rows = table.xpath(".//tr")
        if len(rows) < 3:
            continue
        header_cells = rows[0].xpath("./th|./td")
        colmap = _map_header(_text(c) for c in header_cells)
        if "work_title" not in colmap.values():
            continue
        span = max(len(tr.xpath("./td|./th")) for tr in rows)
        if span < 2:
            continue
        status = next((s for pat, s in STATUS_BY_ARTICLE if pat.search(title)), "banned")
        verified_by = f"harvest:wikipedia:{title}"

        for tr in rows[1:]:
            cells = tr.xpath("./td|./th")
            vals = {}
            for idx, field in colmap.items():
                if idx < len(cells):
                    vals[field] = _clean(_text(cells[idx]))
            work = vals.get("work_title")
            if not work or _is_junk(work) or _is_junk(vals.get("ban_reason") or ""):
                continue
            if re.fullmatch(r"[\d\s,.\-–/]+", work):   # a stray year row
                continue

            subdivision = vals.get("subdivision")
            code, disp = resolve_iso(subdivision, base_code) if subdivision else (base_code, base_name)
            author = vals.get("work_author")
            if author and _is_junk(author):
                author = None
            # Authors are sometimes italicised, leaving a blank cell.
            if not author:
                author = _author_from_italic(tr, work)

            reason = vals.get("ban_reason")
            if not reason or _is_junk(reason):
                # Assert nothing the source doesn't. No invented motives.
                where = disp or base_name or "an unnamed jurisdiction"
                reason = (f"Listed as banned in {where}"
                          + (f" ({vals['banned_since']})" if vals.get("banned_since") else "")
                          + " by the cited source; no reason given there.")

            work = re.sub(r"\s*[\(\[](1[0-9]{3}|20[0-9]{2})[\)\]]\s*$", "", work).strip()
            inline_year = _four_digit(re.search(r"[\(\[](1[0-9]{3}|20[0-9]{2})[\)\]]\s*$",
                                                vals.get("work_title") or "").group(0)) \
                if re.search(r"[\(\[](1[0-9]{3}|20[0-9]{2})[\)\]]\s*$", vals.get("work_title") or "") \
                else None
            year = vals.get("banned_since") or inline_year
            rec = Harvested(
                work_title=work[:240],
                work_author=(author or None) and author[:180],
                banned_since=year,
                country_code=code,
                ban_reason=reason,
                source_url=permalink,
                status=status,
                country_name=disp or base_name,
                work_year=_four_digit(year),
                notes=f"Machine-harvested from Wikipedia: {title}",
                verified_by=verified_by,
            )
            if rec.key() in seen_local:
                continue
            seen_local.add(rec.key())
            out.append(rec)
    return out


def _author_from_italic(tr, work: str) -> Optional[str]:
    """Recover the author from the cell's italics.

    The comparison strips any trailing year from the work, because a title that
    reads "The Naked and the Dead (1948)" otherwise fails to match its own
    italicised run and gets written back into the author column.
    """
    bare = re.sub(r"[\(\[](1[0-9]{3}|20[0-9]{2})[\)\]]", "", work or "")
    bare = re.sub(r"[^a-z]+", " ", bare.lower()).strip()
    for el in tr.xpath(".//i|.//em"):
        t = _clean(_text(el))
        if not t or _is_junk(t):
            continue
        norm = re.sub(r"[^a-z]+", " ", t.lower()).strip()
        if not norm or (bare and (norm == bare or norm in bare or bare in norm)):
            continue
        # An author is a person/organisation, not a sentence.
        if len(t.split()) > 8 or t.endswith((".", ";")):
            continue
        return t
    return None


def _four_digit(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    m = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", v)
    return m.group(1) if m else None


def harvest(articles: Optional[list] = None, limit: int = 60,
            client: Optional[httpx.Client] = None) -> list:
    """Harvest every in-scope article, de-duplicated across articles."""
    owns = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT},
                                    follow_redirects=True, timeout=60)
    try:
        titles = articles if articles is not None else discover_articles(client, limit)
        # Wiki redirects can rename a title, so match permalinks back by the
        # canonical title the API echoes rather than the one we asked for.
        perms = _permalinks(client, titles)
        canonical = {t.replace(" ", "_"): t for t in titles}
        out, seen = [], set()
        for t in titles:
            perm = perms.get(t) or perms.get(canonical.get(t.replace(" ", "_"), ""))
            if not perm:
                continue
            for rec in parse_article(client, t, perm):
                k = rec.key()
                if k in seen:
                    continue
                seen.add(k)
                out.append(rec)
        return out
    finally:
        if owns:
            client.close()


def merge(existing_keys: set, records: list) -> list:
    """Drop anything already present. ``existing_keys`` holds ``Harvested.key()``."""
    fresh, seen = [], set(existing_keys)
    for rec in records:
        k = rec.key()
        if k in seen:
            continue
        seen.add(k)
        fresh.append(rec)
    return fresh
