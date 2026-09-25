"""Nemotron on Nebius Token Factory (OpenAI-compatible API).

Model ids as served to this account on 2026-09-25 (GET /v1/models).
Nano Omni is not served there, so nothing in this project sends images or
audio to a model.

Nemotron 3 models reason before answering and the reasoning counts against
max_tokens. With a small max_tokens the whole budget can go to reasoning and
`content` comes back empty, so defaults here are generous.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import TypeVar

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
LIGHTNING = "nvidia/Nemotron-3_5-Lightning"
SUPER = "nvidia/nemotron-3-super-120b-a12b"
ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1"

T = TypeVar("T", bound=BaseModel)


class EmptyAnswer(RuntimeError):
    """The model spent max_tokens on reasoning and returned no content."""


@lru_cache
def client() -> OpenAI:
    load_dotenv()
    key = os.environ.get("NEBIUS_API_KEY")
    if not key:
        raise RuntimeError("NEBIUS_API_KEY is not set (copy .env.example to .env)")
    return OpenAI(api_key=key, base_url=os.environ.get("NEBIUS_BASE_URL", DEFAULT_BASE_URL))


def chat(messages: list[dict], model: str = SUPER, max_tokens: int = 4096, **kw):
    """Raw chat completion. Returns the full response (usage included)."""
    return client().chat.completions.create(
        model=model, messages=messages, max_tokens=max_tokens, **kw
    )


def chat_json(messages: list[dict], schema: type[T], model: str = SUPER, max_tokens: int = 4096) -> T:
    """Ask for JSON matching `schema` and validate it.

    The schema is also put in the system prompt, so this works even if the
    endpoint ignores response_format.
    """
    system = {
        "role": "system",
        "content": "Answer with a single JSON object matching this JSON Schema, and nothing else:\n"
        + json.dumps(schema.model_json_schema()),
    }
    resp = chat(
        [system, *messages],
        model=model,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    if not content:
        raise EmptyAnswer(f"no content from {model}; usage={resp.usage}")
    return schema.model_validate_json(content)
