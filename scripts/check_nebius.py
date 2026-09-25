"""Check the Nebius key: list the NVIDIA models and make one short call.

    python scripts/check_nebius.py
"""

from clapback.llm import nemotron


def main() -> None:
    models = sorted(m.id for m in nemotron.client().models.list().data)
    nvidia = [m for m in models if m.lower().startswith("nvidia/")]
    print(f"{len(models)} models, NVIDIA ones:")
    for m in nvidia:
        print("  ", m)

    resp = nemotron.chat(
        [{"role": "user", "content": "Reply with exactly: ok"}],
        model=nemotron.NANO,
        max_tokens=1024,
    )
    print("Nano says:", repr(resp.choices[0].message.content))
    print("usage:", resp.usage)


if __name__ == "__main__":
    main()
