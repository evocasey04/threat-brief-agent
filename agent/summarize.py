"""Turn the ranked shortlist into an editorial brief.

Primary path is Groq's OpenAI-compatible chat API on the free tier. The model is
asked for strict JSON and is given numbered items so it can cite sources by index
rather than inventing URLs — hallucinated links are the main failure mode for
this kind of agent.

If the key is missing, the API errors, or the response won't validate, we fall
back to a heuristic brief built from the scores. The job still delivers.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date

import requests

from .sources import Item

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
REQUEST_TIMEOUT = 90

SEVERITIES = ("critical", "high", "medium", "low")

SYSTEM_PROMPT = """You are a senior threat intelligence analyst writing the morning \
brief for a security engineer. You are terse, concrete and sceptical of hype.

Rules:
- Only use the numbered items provided. Never invent stories, CVEs, vendors or URLs.
- Lead with what is actively exploited or has the widest blast radius.
- Merge duplicate coverage of the same story into one entry.
- "why_it_matters" explains impact and blast radius, not what the article says.
- "action" is one concrete step a defender can take today, or "" if there is none.
- Skip marketing, funding rounds and product launches unless genuinely significant.
- Reply with JSON only. No markdown fences, no commentary."""

USER_TEMPLATE = """Date: {today}

Write today's brief from these {count} items.

{items}

Return JSON exactly in this shape:
{{
  "headline": "one sentence summarising the day",
  "top_stories": [
    {{
      "title": "short title",
      "severity": "critical|high|medium|low",
      "why_it_matters": "2-3 sentences",
      "action": "one concrete step, or empty string",
      "sources": [1, 4]
    }}
  ],
  "also_notable": [
    {{"title": "short title", "note": "one sentence", "sources": [7]}}
  ]
}}

Include 3-6 top_stories and up to 6 also_notable. "sources" holds item numbers \
from the list above."""


@dataclass
class Story:
    title: str
    severity: str = "medium"
    why_it_matters: str = ""
    action: str = ""
    items: list[Item] = field(default_factory=list)


@dataclass
class Brief:
    headline: str
    top_stories: list[Story] = field(default_factory=list)
    also_notable: list[Story] = field(default_factory=list)
    generated_by: str = "heuristic"
    item_count: int = 0
    source_count: int = 0


def format_items(items: list[Item]) -> str:
    lines = []
    for index, item in enumerate(items, start=1):
        summary = item.summary[:280] if item.summary else "(no summary)"
        lines.append(f"[{index}] {item.title}\n    source: {item.source}\n    {summary}")
    return "\n\n".join(lines)


def _extract_json(text: str) -> dict:
    """Models occasionally wrap JSON in prose or fences despite instructions."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("no JSON object found in model response")


def _resolve_sources(raw_sources, items: list[Item]) -> list[Item]:
    """Map 1-based indexes back to items, dropping anything out of range."""
    resolved: list[Item] = []
    for value in raw_sources or []:
        try:
            index = int(value) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(items) and items[index] not in resolved:
            resolved.append(items[index])
    return resolved


def _parse_brief(payload: dict, items: list[Item]) -> Brief:
    headline = str(payload.get("headline") or "").strip()
    if not headline:
        raise ValueError("model response had no headline")

    top: list[Story] = []
    for entry in payload.get("top_stories") or []:
        title = str(entry.get("title") or "").strip()
        if not title:
            continue
        severity = str(entry.get("severity") or "medium").strip().lower()
        top.append(
            Story(
                title=title,
                severity=severity if severity in SEVERITIES else "medium",
                why_it_matters=str(entry.get("why_it_matters") or "").strip(),
                action=str(entry.get("action") or "").strip(),
                items=_resolve_sources(entry.get("sources"), items),
            )
        )

    if not top:
        raise ValueError("model response had no usable stories")

    notable: list[Story] = []
    for entry in payload.get("also_notable") or []:
        title = str(entry.get("title") or "").strip()
        if not title:
            continue
        notable.append(
            Story(
                title=title,
                why_it_matters=str(entry.get("note") or "").strip(),
                items=_resolve_sources(entry.get("sources"), items),
            )
        )

    return Brief(headline=headline, top_stories=top, also_notable=notable)


def call_groq(items: list[Item], api_key: str, model: str) -> Brief:
    """Ask the model for a brief. Raises on any failure so callers can fall back."""
    body = {
        "model": model,
        "temperature": 0.3,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_TEMPLATE.format(
                    today=date.today().isoformat(),
                    count=len(items),
                    items=format_items(items),
                ),
            },
        ],
    }

    response = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Groq returned {response.status_code}: {response.text[:300]}")

    content = response.json()["choices"][0]["message"]["content"]
    brief = _parse_brief(_extract_json(content), items)
    brief.generated_by = f"groq:{model}"
    return brief


def heuristic_brief(items: list[Item]) -> Brief:
    """Score-ranked fallback. Plainer, but never empty and never wrong."""
    if not items:
        return Brief(headline="No stories in the window — feeds were quiet or unreachable.")

    def severity_for(item: Item) -> str:
        if item.score >= 18:
            return "critical"
        if item.score >= 11:
            return "high"
        if item.score >= 5:
            return "medium"
        return "low"

    top = [
        Story(
            title=item.title,
            severity=severity_for(item),
            why_it_matters=item.summary or "See the linked article for detail.",
            items=[item],
        )
        for item in items[:5]
    ]
    notable = [
        Story(title=item.title, why_it_matters=item.summary[:160], items=[item])
        for item in items[5:11]
    ]

    return Brief(
        headline=f"{len(items)} stories in the last window; top item: {items[0].title}",
        top_stories=top,
        also_notable=notable,
        generated_by="heuristic",
    )


def build_brief(items: list[Item], api_key: str, model: str, use_llm: bool = True) -> Brief:
    """Synthesise a brief, degrading to heuristics rather than failing."""
    brief: Brief

    if not items:
        brief = heuristic_brief(items)
    elif use_llm and api_key:
        try:
            brief = call_groq(items, api_key, model)
            log.info("brief synthesised by %s", brief.generated_by)
        except Exception as exc:
            log.warning("LLM synthesis failed (%s) — falling back to heuristics", exc)
            brief = heuristic_brief(items)
    else:
        log.info("LLM disabled or no API key — using heuristic brief")
        brief = heuristic_brief(items)

    brief.item_count = len(items)
    brief.source_count = len({item.source for item in items})
    return brief
