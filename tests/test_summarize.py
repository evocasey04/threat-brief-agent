from datetime import UTC, datetime

import pytest

from agent.render import render_html, render_markdown, render_text, subject_line
from agent.sources import Item
from agent.summarize import _extract_json, _parse_brief, build_brief, heuristic_brief


def make_item(title: str) -> Item:
    return Item(
        title=title,
        link=f"https://example.com/{abs(hash(title))}",
        source="Test Feed",
        category="security",
        published=datetime.now(UTC),
        summary="Some detail about the story.",
    )


PAYLOAD = {
    "headline": "One critical exploit dominates the day.",
    "top_stories": [
        {
            "title": "Fortinet flaw exploited",
            "severity": "critical",
            "why_it_matters": "Internet-facing and pre-auth.",
            "action": "Patch FortiOS today.",
            "sources": [1, 99],
        }
    ],
    "also_notable": [{"title": "Chrome update", "note": "Sandbox escape fixed.", "sources": [2]}],
}


def test_extract_json_handles_markdown_fences():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_handles_surrounding_prose():
    assert _extract_json('Here you go:\n{"a": 1}\nHope that helps.') == {"a": 1}


def test_extract_json_raises_when_there_is_no_object():
    with pytest.raises(ValueError):
        _extract_json("sorry, I cannot help with that")


def test_parse_brief_resolves_source_indexes_and_drops_out_of_range():
    items = [make_item("first"), make_item("second")]
    brief = _parse_brief(PAYLOAD, items)
    assert brief.top_stories[0].items == [items[0]]  # index 99 discarded
    assert brief.also_notable[0].items == [items[1]]


def test_parse_brief_normalises_unknown_severity():
    payload = {
        "headline": "x",
        "top_stories": [{"title": "y", "severity": "apocalyptic", "sources": []}],
    }
    assert _parse_brief(payload, []).top_stories[0].severity == "medium"


def test_parse_brief_rejects_a_response_with_no_stories():
    with pytest.raises(ValueError):
        _parse_brief({"headline": "x", "top_stories": []}, [])


def test_build_brief_falls_back_when_the_llm_is_disabled():
    brief = build_brief([make_item("Zero-day exploited")], api_key="", model="m", use_llm=False)
    assert brief.generated_by == "heuristic"
    assert brief.top_stories


def test_build_brief_handles_an_empty_day():
    brief = build_brief([], api_key="key", model="m", use_llm=True)
    assert brief.top_stories == []
    assert "quiet" in brief.headline.lower()


def test_heuristic_brief_reports_counts_via_build():
    items = [make_item(f"Story {n}") for n in range(8)]
    brief = build_brief(items, api_key="", model="m", use_llm=False)
    assert brief.item_count == 8
    assert brief.source_count == 1


def test_renderers_produce_output_for_every_format():
    items = [make_item("first"), make_item("second")]
    brief = _parse_brief(PAYLOAD, items)

    text = render_text(brief)
    html = render_html(brief)
    markdown = render_markdown(brief)

    assert "Fortinet flaw exploited" in text
    assert "Patch FortiOS today." in text
    assert "Fortinet flaw exploited" in html
    assert html.startswith("<div")
    assert "# Threat Brief" in markdown
    assert items[0].link in markdown


def test_html_escapes_untrusted_titles():
    items = [make_item("x")]
    payload = {
        "headline": "safe",
        "top_stories": [{"title": "<script>alert(1)</script>", "sources": [1]}],
    }
    html = render_html(_parse_brief(payload, items))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_subject_line_flags_critical_days():
    items = [make_item("x")]
    assert "[CRITICAL]" in subject_line(_parse_brief(PAYLOAD, items))


def test_subject_line_defaults_to_daily():
    payload = {"headline": "quiet", "top_stories": [{"title": "y", "severity": "low"}]}
    assert "[Daily]" in subject_line(_parse_brief(payload, []))


def test_heuristic_brief_on_empty_input_is_safe_to_render():
    brief = heuristic_brief([])
    assert render_text(brief)
    assert render_html(brief)
