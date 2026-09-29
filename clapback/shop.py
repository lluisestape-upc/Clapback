"""Real product prices for the treatment plan.

    Tavily Search    per treatment type: an advanced search limited to shops
                     whose pages carry price and size, and an open one (Spain,
                     euros), both returning the page text
    Tavily Extract   the text of the result pages that came back without it
    Nemotron         reads the pages: name, price as written, size, pieces per
                     pack, and short passages copied from the page
                     (agents/shopper.py)
    verify()         every passage must be on the page and every number in a
                     passage; panels must have the treatment's thickness; the
                     price per m², computed here and never by the model, must
                     be plausible for that kind of product

The cheapest verified product of each type prices the plan, and to_units()
turns the planned areas into whole pieces of it. Without a Tavily key, or
with no verified product, the catalogue's typical price is used and the app
says so.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from .acoustics import treat
from .acoustics.treat import Treatment
from .llm.nemotron import ENV_FILE
from .room import Room

log = logging.getLogger("uvicorn.error")

SEARCH_URL = "https://api.tavily.com/search"
EXTRACT_URL = "https://api.tavily.com/extract"
COUNTRY = "spain"
# Marketplaces without a clean price and size, sites outside the euro area,
# and shops whose pages Tavily Extract can't fetch (tested 2026-09-28).
EXCLUDE = ["amazon.es", "amazon.com", "youtube.com", "idealo.es", "pinterest.com", "pinterest.es",
           "wallapop.com", "milanuncios.com", "facebook.com", "instagram.com", "aliexpress.com",
           "leroymerlin.es", "maisonsdumonde.com", "alibaba.com", "made-in-china.com", "ebay.com",
           "etsy.com", "tiktok.com"]
# Country domains outside the euro area that Spanish-language searches bring up.
OTHER_TLDS = (".mx", ".cl", ".co", ".ar", ".uy", ".pe", ".ec", ".ve", ".bo", ".py", ".cr", ".gt", ".do")
# Shops whose product pages Tavily Extract reads with price and size.
PANEL_SHOPS = ["skumacoustics.com", "latiendaacustica.es", "addictivesound.es", "diaterm.com", "manomano.es",
               "sineco-acustica.com"]
HOME_SHOPS = ["ikea.com", "kavehome.com", "jysk.es", "conforama.es", "zarahome.com"]
PAGES = 6
TTL_S = 6 * 3600

# What to look for per treatment, and what a real product of that kind looks
# like: thickness range (panels), area of one piece and price per m². Each
# kind has an open search and one limited to shops known to work.
KINDS: dict[str, dict] = {
    "panel_50": {
        "query": "panel acústico absorbente 60x60x5 cm precio", "shops": PANEL_SHOPS,
        # Pages that list fixed prices per size; searches for panels mostly
        # find "from €X" configurators, so these are always read as well.
        "seeds": ["https://www.skumacoustics.com/es/espuma-acustica/61-svart-panel-acustico-negro.html",
                  "https://tienda.lyricaudio.com/producto/panel-100x100x5-cm"],
        "what": "sound-absorbing acoustic panels about 5 cm thick (foam, mineral wool or polyester fibre)",
        "size": "width and height of one panel",
        "thickness": (3.5, 7.0), "piece_m2": (0.05, 3.0), "eur_m2": (5, 300),
    },
    "panel_100": {
        "query": "panel acústico absorbente 10 cm grosor precio", "shops": PANEL_SHOPS,
        "what": "sound-absorbing acoustic panels or bass traps about 10 cm thick",
        "size": "width and height of one panel",
        "thickness": (8.0, 15.0), "piece_m2": (0.05, 3.0), "eur_m2": (10, 400),
    },
    "curtain": {
        "query": "cortinas opacas gruesas 1 par 145x250 cm precio", "shops": HOME_SHOPS,
        "what": "heavy curtains (velvet, blackout or thermal)",
        "size": "width and drop (length) of one curtain panel",
        # The absorption data for heavy curtains assumes them drawn at double
        # fullness, so each m² of window takes two m² of fabric.
        "fullness": 2.0,
        "thickness": None, "piece_m2": (0.5, 8.0), "eur_m2": (4, 300),
    },
    "rug": {
        "query": "alfombra 200x300 cm precio", "shops": HOME_SHOPS,
        "what": "large rugs",
        "size": "width and length of the rug",
        "thickness": None, "piece_m2": (0.8, 20.0), "eur_m2": (3, 250),
    },
    "bookshelf": {
        "query": "librería estantería 80x200 cm precio", "shops": HOME_SHOPS,
        "what": "tall open bookshelves",
        "size": "width and height of the front of the shelf",
        "thickness": None, "piece_m2": (0.3, 5.0), "eur_m2": (15, 600),
    },
}

TO_CM = {"cm": 1.0, "mm": 0.1, "m": 100.0}
READERS = 4   # shop pages read by the model at the same time, per treatment type


def covers_m2(tid: str, pieces: int, piece_m2: float) -> float:
    """Surface one purchase treats: its area, less the fullness of curtains."""
    return pieces * piece_m2 / KINDS[tid].get("fullness", 1.0)


def enabled() -> bool:
    load_dotenv(ENV_FILE)
    return bool(os.environ.get("TAVILY_API_KEY"))


# ---------- page text ----------

SIZE_RE = re.compile(r"\d{2,4}(?:[.,]\d)?\s?[x×]\s?\d{2,4}", re.I)
PRICE_RE = re.compile(r"€\s?\d{1,3}(?:[.\s]\d{3})*(?:,\d{2}|\.\d{2})?|\d{1,3}(?:[.\s]\d{3})*(?:,\d{2}|\.\d{2})?\s?€")


def clean(text: str) -> str:
    """Page text without images, link targets or bare URLs, whitespace collapsed."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = text.replace("\xa0", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ").replace(" ", " ")).strip().lower()


def excerpt(text: str, radius: int = 350, limit: int = 6000) -> str:
    """The parts of a page around its prices, which is where name, size and
    pack are, so the model reads a few thousand characters, not the page."""
    spans: list[list[int]] = []
    for m in PRICE_RE.finditer(text):
        a, b = max(0, m.start() - radius), min(len(text), m.end() + radius)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = b
        else:
            spans.append([a, b])
    out = " … ".join(text[a:b] for a, b in spans)
    return out[:limit]


def parse_price(text: str) -> float | None:
    """'1.234,56 €', '€70,95', '4,490.00', '89.90€', '1 299 €' → euros."""
    s = re.sub(r"[^\d.,]", "", text.replace(" ", ""))
    if not s or not any(c.isdigit() for c in s):
        return None
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s:
        head, tail = s.rsplit(",", 1)
        s = f"{head.replace(',', '')}.{tail}" if len(tail) == 2 else s.replace(",", "")
    elif "." in s:
        head, tail = s.rsplit(".", 1)
        s = s.replace(".", "") if len(tail) == 3 else f"{head.replace('.', '')}.{tail}"
    try:
        return float(s)
    except ValueError:
        return None


def _number_in(value: float, text: str) -> bool:
    """Is this number written in the text (as 120, 2.5 or 2,5)?"""
    forms = {f"{value:g}", f"{value:g}".replace(".", ",")}
    if float(value).is_integer():
        forms.add(str(int(value)))
    return any(re.search(rf"(?<![\d]){re.escape(f)}(?![\d])", text) for f in forms)


# ---------- verification ----------

@dataclass
class Offer:
    treatment: str
    name: str
    url: str
    site: str
    price_eur: float
    pieces: int
    piece_m2: float
    covers_m2: float
    eur_per_m2: float
    width_cm: float
    height_cm: float
    thickness_cm: float | None
    evidence: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def verify(tid: str, found, page: str) -> tuple[Offer | None, str]:
    """Check one product the model read off a page. Returns (offer, "") or (None, reason)."""
    kind = KINDS[tid]
    page_n = norm(page)
    evidence = [e for e in (found.evidence or []) if 8 <= len(e) <= 400]
    if not evidence:
        return None, "no evidence"
    if not all(norm(e) in page_n for e in evidence):
        return None, "evidence not on the page"
    joined = norm(" ".join(evidence))

    price = parse_price(found.price_text or "")
    if price is None or price <= 0:
        return None, "no price"
    price_digits = re.sub(r"[^\d.,]", "", found.price_text)
    if norm(found.price_text) not in page_n or price_digits not in joined.replace(" ", ""):
        return None, "price not quoted"

    scale = TO_CM.get(found.unit or "cm")
    if scale is None or not found.width_cm or not found.height_cm:
        return None, "no size"
    numbers = [found.width_cm, found.height_cm]
    if kind["thickness"]:
        if not found.thickness_cm:
            return None, "no thickness"
        numbers.append(found.thickness_cm)
    if found.pieces and found.pieces > 1:
        numbers.append(found.pieces)
    if not all(_number_in(v, joined) for v in numbers):
        return None, "numbers not quoted"

    w, h = found.width_cm * scale, found.height_cm * scale
    thick_scale = TO_CM.get(found.thickness_unit or found.unit or "cm", scale)
    thick = found.thickness_cm * thick_scale if found.thickness_cm else None
    if kind["thickness"] and not kind["thickness"][0] <= thick <= kind["thickness"][1]:
        return None, "wrong thickness"
    piece_m2 = w * h / 1e4
    if not kind["piece_m2"][0] <= piece_m2 <= kind["piece_m2"][1]:
        return None, "implausible size"
    pieces = max(1, int(found.pieces or 1))
    covers = covers_m2(tid, pieces, piece_m2)
    eur_m2 = price / covers
    if not kind["eur_m2"][0] <= eur_m2 <= kind["eur_m2"][1]:
        return None, "implausible price per m²"

    return Offer(
        treatment=tid, name=found.name.strip()[:120], url=found.url,
        site=urlparse(found.url).netloc.removeprefix("www."), price_eur=round(price, 2),
        pieces=pieces, piece_m2=round(piece_m2, 4), covers_m2=round(covers, 4), eur_per_m2=round(eur_m2, 2),
        width_cm=round(w, 1), height_cm=round(h, 1),
        thickness_cm=round(thick, 1) if thick else None, evidence=evidence[:3],
    ), ""


# ---------- Tavily ----------

def _tavily(url: str, body: dict, timeout: float) -> dict:
    r = httpx.post(url, headers={"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"}, json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


def useful(text: str) -> bool:
    """A page can only yield a checked product if it shows a price and a size."""
    return bool(PRICE_RE.search(text) and SIZE_RE.search(text))


def search(tid: str) -> dict[str, str]:
    """Result pages with their text (empty when the search didn't return it):
    the shops search first, then the open search."""
    kind = KINDS[tid]
    bodies = [
        {"query": kind["query"], "max_results": 10, "search_depth": "advanced",
         "include_domains": kind["shops"], "include_raw_content": True},
        {"query": kind["query"], "max_results": 10, "search_depth": "basic", "country": COUNTRY,
         "exclude_domains": EXCLUDE, "include_raw_content": True},
    ]
    with ThreadPoolExecutor(2) as ex:
        results = list(ex.map(lambda b: _tavily(SEARCH_URL, b, 30).get("results", []), bodies))
    pages: dict[str, str] = {}
    for r in (x for res in results for x in res):
        u = r.get("url", "")
        host = urlparse(u).netloc.removeprefix("www.")
        foreign = host.endswith(OTHER_TLDS) or "mercadolibre" in host
        if u.startswith("https://") and u not in pages and not foreign and not any(host.endswith(d) for d in EXCLUDE):
            pages[u] = clean(r.get("raw_content") or "")
    return pages


def gather(tid: str) -> dict[str, str]:
    """Up to PAGES pages with a price and a size, fetching the text of the
    ones the search returned without it."""
    pages = {**{u: "" for u in KINDS[tid].get("seeds", [])}, **search(tid)}
    missing = [u for u, t in pages.items() if not t][:5]
    if missing:
        pages.update(extract(missing))
    return dict(list(((u, t) for u, t in pages.items() if useful(t)))[:PAGES])


def extract(urls: list[str]) -> dict[str, str]:
    if not urls:
        return {}
    res = _tavily(EXTRACT_URL, {"urls": urls, "extract_depth": "advanced"}, 40)
    return {r["url"]: clean(r.get("raw_content") or "") for r in res.get("results", []) if r.get("raw_content")}


def discover(tid: str) -> dict:
    """Search, read and verify products of one treatment type."""
    from .agents import shopper  # model calls live with the other agents

    report = {"pages": 0, "proposed": 0, "verified": 0, "rejected": {}, "offers": [], "error": None}
    try:
        pages = gather(tid)
    except httpx.HTTPError as e:
        log.warning("tavily failed for %s: %s", tid, e)
        report["error"] = f"tavily: {type(e).__name__}"
        return report
    report["pages"] = len(pages)
    if not pages:
        return report
    # One page per call: with several pages at once the model tends to
    # return nothing, while a single page gets read properly.
    def read(url: str) -> list:
        try:
            return shopper.run(KINDS[tid], {url: excerpt(pages[url])})
        except Exception as e:  # noqa: BLE001 - one unreadable page doesn't stop the others
            log.warning("shopper failed for %s on %s: %s", tid, url, e)
            report["error"] = f"model: {type(e).__name__}"
            return []

    with ThreadPoolExecutor(READERS) as ex:
        found = [f for fs in ex.map(read, pages) for f in fs]
    report["proposed"] = len(found)
    offers = []
    for f in found:
        page = pages.get(f.url) or next((t for u, t in pages.items() if u.rstrip("/") == f.url.rstrip("/")), "")
        offer, why = verify(tid, f, page) if page else (None, "unknown page")
        if offer:
            offers.append(offer)
        else:
            report["rejected"][why] = report["rejected"].get(why, 0) + 1
    offers = list({(o.site, o.price_eur, o.piece_m2): o for o in offers}.values())   # same product twice
    offers.sort(key=lambda o: o.eur_per_m2)
    report["verified"] = len(offers)
    report["offers"] = [o.to_dict() for o in offers[:3]]
    return report


_cache: dict = {}
_lock = threading.Lock()


def prices() -> dict:
    """Verified offers for every treatment type, cached for a few hours."""
    if not enabled():
        return {"checked_at": None, "items": {}}
    with _lock:
        if _cache.get("at") and time.time() - _cache["at"] < TTL_S:
            return _cache["data"]
    with ThreadPoolExecutor(len(KINDS)) as ex:
        reports = dict(zip(KINDS, ex.map(discover, KINDS)))
    data = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "items": reports}
    if any(r["offers"] for r in reports.values()):
        with _lock:
            _cache.update(at=time.time(), data=data)
    return data


# ---------- whole pieces ----------

def to_units(room: Room, measured_rt: list[float | None], plan: list[Treatment], offers: dict[str, dict],
             budget_eur: float, prices: dict[str, float]) -> tuple[list[Treatment], dict[str, int]]:
    """Round each planned area to whole purchases of the real product, then
    remove purchases while the plan is over budget or over the space."""
    buys: dict[int, int] = {}
    per_buy_m2 = {}
    for i, t in enumerate(plan):
        o = offers.get(t.id)
        if o:
            per_buy_m2[i] = covers_m2(t.id, o["pieces"], o["piece_m2"])
            buys[i] = max(1, round(t.area_m2 / per_buy_m2[i]))

    def build() -> list[Treatment]:
        out = []
        for i, t in enumerate(plan):
            if i in buys:
                if buys[i] > 0:
                    out.append(Treatment(id=t.id, where=t.where, area_m2=round(buys[i] * per_buy_m2[i], 3)))
            else:
                out.append(t)
        return out

    for _ in range(500):
        fitted = build()
        if not treat.validate(room, fitted, budget_eur, prices):
            break
        # drop one purchase of the costliest real-product item
        i = max((j for j in buys if buys[j] > 0), key=lambda j: offers[plan[j].id]["price_eur"], default=None)
        if i is None:
            break
        buys[i] -= 1
    fitted = build()
    return fitted, {plan[i].id + "@" + plan[i].where: n for i, n in buys.items() if n > 0}
