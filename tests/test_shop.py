"""Real prices: the checks that keep a model-read price honest. No network."""

import pytest

from clapback import shop
from clapback.acoustics import treat
from clapback.acoustics.treat import Treatment
from clapback.agents import shopper
from tests.test_agents import MEASURED, room

URL = "https://tienda.example/panel-basotect"
PAGE = shop.clean(
    "![foto](https://tienda.example/img.jpg) [Inicio](https://tienda.example/) > Acústica\n"
    "Panel acústico Basotect 60 x 60 x 5 cm, pack de 4 unidades.\n"
    "Precio:\xa089,90 € IVA incluido. Envío gratis en 48 h."
)


def found(**kw):
    base = dict(name="Panel acústico Basotect", url=URL, price_text="89,90 €", pieces=4,
                width_cm=60, height_cm=60, thickness_cm=5, unit="cm",
                evidence=["Panel acústico Basotect 60 x 60 x 5 cm, pack de 4 unidades", "Precio: 89,90 €"])
    return shopper.Found(**{**base, **kw})


@pytest.mark.parametrize("text,value", [
    ("89,90 €", 89.90), ("€70,95", 70.95), ("1.234,56 €", 1234.56), ("4,490.00", 4490.0),
    ("89.90€", 89.90), ("1 299 €", 1299.0), ("537,00€", 537.0), ("81 €", 81.0), ("sin precio", None),
])
def test_prices_are_read_as_written(text, value):
    assert shop.parse_price(text) == (pytest.approx(value) if value else None)


def test_clean_drops_images_and_links_but_keeps_the_words():
    assert "img.jpg" not in PAGE and "https://" not in PAGE
    assert "Inicio" in PAGE and "89,90 €" in PAGE


def test_excerpt_keeps_the_text_around_prices():
    long = "x " * 3000 + PAGE + " y" * 3000
    ex = shop.excerpt(long)
    assert "Basotect" in ex and "89,90 €" in ex and len(ex) < 1000


def test_a_quoted_product_passes_and_the_engine_computes_the_price_per_m2():
    offer, why = shop.verify("panel_50", found(), PAGE)
    assert why == ""
    assert offer.piece_m2 == pytest.approx(0.36)
    assert offer.eur_per_m2 == pytest.approx(89.90 / (4 * 0.36), rel=1e-3)
    assert offer.site == "tienda.example"


@pytest.mark.parametrize("change,reason", [
    (dict(evidence=["Panel acústico Basotect 60 x 60 x 5 cm, pack de 6 unidades"]), "evidence not on the page"),
    (dict(price_text="79,90 €"), "price not quoted"),
    (dict(width_cm=120), "numbers not quoted"),
    (dict(pieces=6), "numbers not quoted"),
    (dict(thickness_cm=None), "no thickness"),
])
def test_anything_not_on_the_page_is_rejected(change, reason):
    offer, why = shop.verify("panel_50", found(**change), PAGE)
    assert offer is None and why == reason


def test_a_5_cm_panel_is_not_a_10_cm_panel():
    offer, why = shop.verify("panel_100", found(), PAGE)
    assert offer is None and why == "wrong thickness"


def test_sizes_in_mm_are_converted_by_the_engine():
    page = shop.clean("Panel fonoabsorbente 600x600x50 mm, caja de 4 uds. 89,90 €")
    f = found(width_cm=600, height_cm=600, thickness_cm=50, unit="mm",
              evidence=["Panel fonoabsorbente 600x600x50 mm, caja de 4 uds. 89,90 €"])
    offer, why = shop.verify("panel_50", f, page)
    assert why == "" and offer.piece_m2 == pytest.approx(0.36) and offer.thickness_cm == 5


def test_thickness_can_be_in_another_unit():
    page = shop.clean("Panel acústico PET, de 40mm de espesor, 60x60cm. 01 a 39 uds. 16,65 €")
    f = found(price_text="16,65 €", pieces=1, width_cm=60, height_cm=60, thickness_cm=40, unit="cm",
              thickness_unit="mm", evidence=["Panel acústico PET, de 40mm de espesor, 60x60cm. 01 a 39 uds. 16,65 €"])
    offer, why = shop.verify("panel_50", f, page)
    assert why == "" and offer.thickness_cm == 4 and offer.eur_per_m2 == pytest.approx(16.65 / 0.36, rel=1e-3)


def test_an_implausible_price_per_m2_is_rejected():
    page = shop.clean("Panel acústico Basotect 60 x 60 x 5 cm, pack de 4 unidades. Precio: 5.400,00 €")
    f = found(price_text="5.400,00 €", evidence=["Panel acústico Basotect 60 x 60 x 5 cm, pack de 4 unidades",
                                                 "Precio: 5.400,00 €"])
    offer, why = shop.verify("panel_50", f, page)
    assert offer is None and why == "implausible price per m²"


def test_discover_reports_what_was_read_and_what_passed(monkeypatch):
    monkeypatch.setattr(shop, "search", lambda tid: {URL: PAGE, "https://other.example/x": "",
                                                       "https://blog.example/y": "Sin precios aquí"})
    monkeypatch.setattr(shop, "extract", lambda urls: {"https://other.example/x": "Mesa 120x60 cm, 12,00 €"})
    monkeypatch.setattr(shopper, "run", lambda kind, pages: [found(), found(price_text="79,90 €")] if URL in pages else [])
    report = shop.discover("panel_50")
    assert report["pages"] == 2 and report["proposed"] == 2 and report["verified"] == 1
    assert report["rejected"] == {"price not quoted": 1}
    assert report["offers"][0]["price_eur"] == 89.90


def test_whole_pieces_within_budget():
    offer, _ = shop.verify("panel_50", found(), PAGE)   # €89.90 per pack of 1.44 m²
    prices = {"panel_50": offer.price_eur / (offer.pieces * offer.piece_m2)}
    plan = [Treatment(id="panel_50", where="wall", area_m2=6.0)]
    fitted, buys = shop.to_units(room(), MEASURED, plan, {"panel_50": offer.to_dict()}, 300, prices)
    assert buys == {"panel_50@wall": 3}                  # 4 packs would be €360
    assert fitted[0].area_m2 == pytest.approx(3 * 1.44)
    assert treat.cost(fitted, prices) == pytest.approx(3 * 89.90)


def test_plan_endpoint_prices_with_the_real_product(monkeypatch):
    from fastapi.testclient import TestClient

    from clapback import server
    from clapback.llm import nemotron

    def boom(*a, **kw):
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(nemotron, "chat", boom)   # greedy fallback plan
    page = shop.clean("Panel acústico Basotect 60 x 60 x 5 cm, pack de 4 unidades. Precio: 19,90 €")
    offer, _ = shop.verify("panel_50", found(price_text="19,90 €", evidence=[
        "Panel acústico Basotect 60 x 60 x 5 cm, pack de 4 unidades", "Precio: 19,90 €"]), page)
    r = room()
    body = {
        "room": r.model_dump(), "goal": "voice", "budget_eur": 300,
        "claps": [[{"band_hz": f, "t20_s": t, "dynamic_range_db": 40}
                   for f, t in zip((125, 250, 500, 1000, 2000, 4000), MEASURED)]],
        "offers": {"panel_50": offer.to_dict()},
    }
    out = TestClient(server.app).post("/api/plan", json=body).json()
    assert out["priced_with"] == "shops"
    panels = [t for t in out["treatments"] if t["id"] == "panel_50"]
    assert panels and panels[0]["product"]["units"] % 4 == 0
    assert panels[0]["cost_eur"] == round(panels[0]["product"]["buys"] * 19.90)
    assert out["cost_eur"] <= 300
