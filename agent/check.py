"""Preflight for the LLM path: `python -m agent.check`.

The synthesis step degrades to heuristics on any failure, which is right for a
06:00 cron job but means a bad key or a retired model shows up as a slightly
duller email rather than an error. This command makes those failures loud.

It verifies, in order:
  1. the API key is present and accepted,
  2. the configured model id still exists on Groq,
  3. a real synthesis call returns JSON this codebase can parse.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import requests

from .config import Settings
from .sources import Item
from .summarize import call_groq

MODELS_URL = "https://api.groq.com/openai/v1/models"

# Three plausible stories, so the smoke test exercises the real prompt.
SAMPLE_ITEMS = [
    Item(
        title="SonicWall warns of actively exploited SMA1000 zero-day flaws",
        link="https://example.com/sonicwall",
        source="Sample Feed",
        category="security",
        published=datetime.now(UTC),
        summary="Two zero-days are being chained for pre-auth remote code execution.",
    ),
    Item(
        title="Chrome ships emergency update for sandbox escape",
        link="https://example.com/chrome",
        source="Sample Feed",
        category="security",
        published=datetime.now(UTC),
        summary="CVE-2026-11111 is fixed in the stable channel.",
    ),
    Item(
        title="Startup raises $12M to build an AI notetaker",
        link="https://example.com/startup",
        source="Sample Feed",
        category="tech",
        published=datetime.now(UTC),
        summary="Series A funding round announced this morning.",
    ),
]

OK = "  OK   "
FAIL = " FAIL  "
WARN = " WARN  "


def _explain_http_error(status: int, body: str) -> str:
    if status == 401:
        return "the API key was rejected. Check GROQ_API_KEY in .env for typos or a stale key."
    if status == 404 or "model_not_found" in body or "does not exist" in body:
        return "that model id no longer exists on Groq. Pick one from the list above."
    if status == 429:
        return "rate limited. The free tier has per-minute caps; wait a minute and retry."
    return f"HTTP {status}: {body[:200]}"


def list_models(api_key: str) -> list[str]:
    """Return the model ids Groq currently serves. Raises on HTTP failure."""
    response = requests.get(
        MODELS_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=30
    )
    if response.status_code != 200:
        raise RuntimeError(_explain_http_error(response.status_code, response.text))
    return sorted(m["id"] for m in response.json().get("data", []))


def suggest(models: list[str]) -> list[str]:
    """Chat models worth defaulting to, biggest-looking first.

    Groq serves whisper/guard/TTS models through the same endpoint; those can't
    write a brief, so filter them out before recommending anything.
    """
    excluded = ("whisper", "guard", "tts", "embed", "distil")
    return [m for m in models if not any(word in m.lower() for word in excluded)]


def main() -> int:
    settings = Settings.from_env()

    print("Groq preflight\n" + "-" * 60)

    if not settings.groq_api_key:
        print(f"[{FAIL}] No GROQ_API_KEY found.")
        print("\n  1. Sign in at https://console.groq.com (Google login, no card needed)")
        print("  2. API Keys -> Create API Key, copy it (shown once)")
        print("  3. Put it in .env:  GROQ_API_KEY=gsk_...")
        print("  4. Re-run: python -m agent.check")
        return 1

    masked = f"{settings.groq_api_key[:7]}...{settings.groq_api_key[-4:]}"
    print(f"[{OK}] Key found ({masked})")

    try:
        models = list_models(settings.groq_api_key)
    except Exception as exc:
        print(f"[{FAIL}] Could not list models: {exc}")
        return 2

    print(f"[{OK}] Key accepted; Groq is serving {len(models)} models")

    chat_models = suggest(models)
    if settings.groq_model in models:
        print(f"[{OK}] Configured model '{settings.groq_model}' is live")
    else:
        print(f"[{FAIL}] Configured model '{settings.groq_model}' is NOT available.")
        print("\n  Chat models currently on your account:")
        for model in chat_models:
            print(f"    - {model}")
        print("\n  Set one in .env:  GROQ_MODEL=<id from above>")
        return 3

    print(f"[{'  ..   '}] Running a real synthesis call...")
    try:
        brief = call_groq(SAMPLE_ITEMS, settings.groq_api_key, settings.groq_model)
    except requests.HTTPError as exc:  # pragma: no cover - network dependent
        print(f"[{FAIL}] Request failed: {exc}")
        return 4
    except Exception as exc:
        print(f"[{FAIL}] Synthesis failed: {exc}")
        print("\n  The brief would still send, using the heuristic fallback.")
        return 4

    print(f"[{OK}] Model returned valid, parseable JSON")
    print(f"\n  Headline:  {brief.headline}")
    for story in brief.top_stories:
        print(f"  [{story.severity}] {story.title}")

    funding = [s for s in brief.top_stories if "12M" in s.title or "notetaker" in s.title.lower()]
    if funding:
        print(f"\n[{WARN}] The funding story made the top stories — the prompt asks the")
        print("         model to skip those. Harmless, but a sign this model follows")
        print("         instructions loosely. A larger model id will do better.")

    print(f"\n[{OK}] LLM path verified end to end. Run: python -m agent.main --dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
