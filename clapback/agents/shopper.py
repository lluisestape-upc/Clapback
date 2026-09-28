"""Shopper agent: reads excerpts of shop pages found by Tavily and lists the
products of one kind with their price, size and pack.

It copies, it doesn't compute: the price exactly as written, the size numbers
and their unit as written, and short passages from the page that show them.
shop.verify() checks every passage against the page and every number against
the passages, and works out the price per m² itself.

Model: Nemotron 3 Super, reasoning off, one call per treatment type.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..llm import nemotron


class Found(BaseModel):
    name: str
    url: str
    price_text: str = Field(description="the price exactly as written on the page")
    pieces: int = Field(1, description="how many pieces that price buys")
    width_cm: float | None = None
    height_cm: float | None = None
    thickness_cm: float | None = None
    unit: Literal["cm", "mm", "m"] = "cm"
    thickness_unit: Literal["cm", "mm", "m"] | None = None
    evidence: list[str] = Field(default_factory=list)


class Products(BaseModel):
    products: list[Found] = Field(default_factory=list)


SYSTEM = """You read excerpts of shop pages and list products of one kind with their price and size.

Kind: {what}.
Size means the {size}.{thickness}

For each product give:
- name: as written on the page
- url: the url in the header of the excerpt it comes from
- price_text: the price exactly as written, for what one purchase buys (for example "89,90 €")
- pieces: how many pieces that price buys (a pack of 6 is 6); 1 if the page doesn't say
- width_cm, height_cm{thickness_field}: the size numbers exactly as written on the page
- unit: the unit those size numbers are written in: "cm", "mm" or "m"
  ("358 × 310 mm" is width 358, height 310, unit "mm"; never 35.8 cm){thickness_unit}
- evidence: 1 to 3 short passages copied character for character from the excerpt, which
  together show the name, the price, the size and the pack

Only list products of this kind whose price and size both appear in the excerpt, at most 3 per page.
A page may list several products; take each one's own price and size, not a neighbour's.
Skip prices that are a starting point ("desde", "from") unless the size they buy is stated with them.
Never convert units, add, multiply or estimate. If nothing qualifies, return an empty list."""


def run(kind: dict, pages: dict[str, str]) -> list[Found]:
    thick = kind.get("thickness")
    system = SYSTEM.format(
        what=kind["what"], size=kind["size"],
        thickness=" Thickness matters: give it, as written." if thick else "",
        thickness_field=", thickness_cm" if thick else "",
        thickness_unit=("\n- thickness_unit: the unit the thickness is written in, when it differs from the size's"
                        " (\"60x60cm, 40mm de espesor\" is 60, 60, unit \"cm\", thickness 40, thickness_unit \"mm\")"
                        if thick else ""),
    )
    text = "\n\n".join(f"=== PAGE: {url}\n{body}" for url, body in pages.items())
    out = nemotron.chat_json(
        [{"role": "system", "content": system}, {"role": "user", "content": text}],
        schema=Products, model=nemotron.SUPER, max_tokens=3000, thinking=False,
    )
    return out.products
