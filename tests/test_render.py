"""Renderer tests: escaping, severity routing, and graceful empties.

The renderers are the last thing to touch model output before it reaches an
inbox, so the cases that matter are the hostile ones -- a title with an angle
bracket in it, a story with no sources, a brief with nothing notable.
"""

from datetime import UTC, date, datetime

from agent.render import render_html, render_markdown, render_text, subject_line
from agent.sources import Item
from agent.summarize import Brief, Story

TODAY = date(2026, 3, 14)


def make_item(title: str = "Example", link: str = "https://example.com/a") -> Item:
    return Item(
        title=title,
        link=link,
        source="Example Feed",
        category="security",
        published=datetime(2026, 3, 14, 6, 0, tzinfo=UTC),
    )


def make_brief(**overrides) -> Brief:
    defaults = dict(
        headline="One critical bug, everything else is quiet.",
        top_stories=[
            Story(
                title="Fortinet SSL-VPN under active exploitation",
                severity="critical",
                why_it_matters="Internet-facing and pre-auth.",
                action="Patch FortiOS today.",
                items=[make_item()],
            )
        ],
        also_notable=[Story(title="Minor Chrome update", why_it_matters="Low risk.")],
        item_count=12,
        source_count=4,
    )
    defaults.update(overrides)
    return Brief(**defaults)


def test_subject_line_escalates_to_the_worst_severity():
    critical = make_brief()
    assert subject_line(critical, TODAY).startswith("[CRITICAL]")

    high = make_brief(top_stories=[Story(title="x", severity="high")])
    assert subject_line(high, TODAY).startswith("[High]")

    quiet = make_brief(top_stories=[Story(title="x", severity="low")])
    assert subject_line(quiet, TODAY).startswith("[Daily]")


def test_html_escapes_titles_and_urls():
    hostile = make_brief(
        top_stories=[
            Story(
                title='Bug in <script>alert("x")</script> parser',
                severity="high",
                items=[make_item(link="https://example.com/?a=1&b=2")],
            )
        ]
    )
    html = render_html(hostile, TODAY)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "a=1&amp;b=2" in html


def test_html_and_text_survive_a_story_with_no_sources():
    brief = make_brief(top_stories=[Story(title="Unsourced", severity="medium")])

    html = render_html(brief, TODAY)
    text = render_text(brief, TODAY)

    assert "Unsourced" in html
    assert "Unsourced" in text


def test_empty_brief_still_renders_every_format():
    empty = Brief(headline="Feeds were quiet.")

    for rendered in (
        render_text(empty, TODAY),
        render_html(empty, TODAY),
        render_markdown(empty, TODAY),
    ):
        assert "Feeds were quiet." in rendered

    # No "Also notable" heading when there is nothing notable.
    assert "Also notable" not in render_html(empty, TODAY)
    assert "Also notable" not in render_markdown(empty, TODAY)


def test_markdown_archive_has_a_dated_heading_and_links():
    markdown = render_markdown(make_brief(), TODAY)

    assert markdown.startswith("# Threat Brief — 2026-03-14")
    assert "[Example Feed](https://example.com/a)" in markdown
    assert "**Do this:** Patch FortiOS today." in markdown


def test_text_includes_action_and_provenance_footer():
    text = render_text(make_brief(generated_by="groq:openai/gpt-oss-120b"), TODAY)

    assert "Action: Patch FortiOS today." in text
    assert "12 stories from 4 sources" in text
    assert "groq:openai/gpt-oss-120b" in text
