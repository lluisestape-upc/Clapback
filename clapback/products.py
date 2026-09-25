"""Real products for a plan, via Tavily web search.

Optional: without TAVILY_API_KEY in .env this returns nothing and the app
shows the plan without shopping links. One search per treatment type,
cached for the life of the server, so a demo costs a handful of credits.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from .llm.nemotron import ENV_FILE

log = logging.getLogger("uvicorn.error")

URL = "https://api.tavily.com/search"

QUERIES = {
    "panel_50": "buy 5 cm acoustic absorption panels for home studio, price in euros",
    "panel_100": "buy 10 cm acoustic panels bass traps for home studio, price in euros",
    "curtain": "buy heavy thick velvet curtains sound absorbing, price in euros",
    "rug": "buy large thick rug with felt underlay, price in euros",
    "bookshelf": "buy tall wide bookshelf for living room, price in euros",
}


def enabled() -> bool:
    load_dotenv(ENV_FILE)
    return bool(os.environ.get("TAVILY_API_KEY"))


@lru_cache(maxsize=32)
def search(treatment_id: str, max_results: int = 3) -> tuple[dict, ...]:
    query = QUERIES.get(treatment_id)
    if not query or not enabled():
        return ()
    try:
        r = httpx.post(
            URL,
            headers={"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"},
            json={"query": query, "max_results": max_results, "search_depth": "basic"},
            timeout=15,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("tavily search failed: %s", e)
        return ()
    return tuple(
        {"title": x.get("title", "")[:90], "url": x["url"], "site": urlparse(x["url"]).netloc.removeprefix("www.")}
        for x in r.json().get("results", [])
        if x.get("url", "").startswith("https://")
    )


def for_plan(treatment_ids: list[str]) -> dict[str, list[dict]]:
    return {tid: list(search(tid)) for tid in dict.fromkeys(treatment_ids)}
