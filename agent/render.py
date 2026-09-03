"""Render a Brief as HTML email, plaintext email, and markdown archive.

The HTML uses inline styles and a table-free layout — Gmail strips <style> blocks,
and every mail client disagrees about everything else.
"""

from __future__ import annotations

from datetime import date
from html import escape

from .summarize import Brief, Story

SEVERITY_COLORS = {
    "critical": "#b3261e",
    "high": "#c05621",
    "medium": "#2b6cb0",
    "low": "#4a5568",
}


def subject_line(brief: Brief, today: date | None = None) -> str:
    today = today or date.today()
    severities = [s.severity for s in brief.top_stories]
    if "critical" in severities:
        tag = "CRITICAL"
    elif "high" in severities:
        tag = "High"
    else:
        tag = "Daily"
    return f"[{tag}] Threat Brief — {today.strftime('%a %d %b %Y')}"


def render_text(brief: Brief, today: date | None = None) -> str:
    today = today or date.today()
    lines = [
        f"THREAT BRIEF — {today.strftime('%A %d %B %Y')}",
        "=" * 58,
        "",
        brief.headline,
        "",
    ]

    for index, story in enumerate(brief.top_stories, start=1):
        lines.append(f"{index}. [{story.severity.upper()}] {story.title}")
        if story.why_it_matters:
            lines.append(f"   {story.why_it_matters}")
        if story.action:
            lines.append(f"   Action: {story.action}")
        for item in story.items:
            lines.append(f"   - {item.source}: {item.link}")
        lines.append("")

    if brief.also_notable:
        lines += ["ALSO NOTABLE", "-" * 58]
        for story in brief.also_notable:
            lines.append(f"* {story.title}")
            if story.why_it_matters:
                lines.append(f"  {story.why_it_matters}")
            for item in story.items:
                lines.append(f"  {item.link}")
        lines.append("")

    lines += [
        "-" * 58,
        f"{brief.item_count} stories from {brief.source_count} sources · "
        f"synthesised by {brief.generated_by}",
        "threat-brief-agent",
    ]
    return "\n".join(lines)


def _story_html(story: Story, index: int) -> str:
    color = SEVERITY_COLORS.get(story.severity, SEVERITY_COLORS["medium"])
    parts = [
        '<div style="margin:0 0 26px;padding:0 0 22px;border-bottom:1px solid #e6e8eb;">',
        f'<div style="font:600 11px/1.4 -apple-system,Segoe UI,sans-serif;'
        f'letter-spacing:.09em;text-transform:uppercase;color:{color};margin-bottom:6px;">'
        f"{escape(story.severity)}</div>",
        f'<h3 style="margin:0 0 10px;font:600 17px/1.35 -apple-system,Segoe UI,sans-serif;'
        f'color:#16181d;">{index}. {escape(story.title)}</h3>',
    ]
    if story.why_it_matters:
        parts.append(
            f'<p style="margin:0 0 10px;font:400 15px/1.6 -apple-system,Segoe UI,sans-serif;'
            f'color:#3c4149;">{escape(story.why_it_matters)}</p>'
        )
    if story.action:
        parts.append(
            f'<p style="margin:0 0 10px;padding:9px 12px;background:#f4f6f8;'
            f'border-left:3px solid {color};font:400 14px/1.55 -apple-system,Segoe UI,sans-serif;'
            f'color:#3c4149;"><strong>Do this:</strong> {escape(story.action)}</p>'
        )
    if story.items:
        links = " · ".join(
            f'<a href="{escape(item.link, quote=True)}" '
            f'style="color:#2b6cb0;text-decoration:none;">{escape(item.source)}</a>'
            for item in story.items
        )
        parts.append(
            f'<p style="margin:0;font:400 13px/1.5 -apple-system,Segoe UI,sans-serif;'
            f'color:#6b7280;">{links}</p>'
        )
    parts.append("</div>")
    return "".join(parts)


def render_html(brief: Brief, today: date | None = None) -> str:
    today = today or date.today()
    body = [
        '<div style="margin:0;padding:24px 12px;background:#f2f3f5;">',
        '<div style="max-width:640px;margin:0 auto;padding:32px;background:#ffffff;'
        'border-radius:10px;">',
        '<p style="margin:0 0 4px;font:600 11px/1.4 -apple-system,Segoe UI,sans-serif;'
        'letter-spacing:.12em;text-transform:uppercase;color:#6b7280;">Threat Brief</p>',
        f'<h1 style="margin:0 0 18px;font:600 22px/1.3 -apple-system,Segoe UI,sans-serif;'
        f'color:#16181d;">{escape(today.strftime("%A %d %B %Y"))}</h1>',
        f'<p style="margin:0 0 28px;padding:14px 16px;background:#eef2f7;border-radius:8px;'
        f'font:400 15px/1.6 -apple-system,Segoe UI,sans-serif;color:#2d3340;">'
        f"{escape(brief.headline)}</p>",
    ]

    for index, story in enumerate(brief.top_stories, start=1):
        body.append(_story_html(story, index))

    if brief.also_notable:
        body.append(
            '<h2 style="margin:26px 0 12px;font:600 12px/1.4 -apple-system,Segoe UI,sans-serif;'
            'letter-spacing:.09em;text-transform:uppercase;color:#6b7280;">Also notable</h2>'
            '<ul style="margin:0;padding-left:18px;">'
        )
        for story in brief.also_notable:
            link = story.items[0].link if story.items else ""
            title = (
                f'<a href="{escape(link, quote=True)}" '
                f'style="color:#16181d;text-decoration:none;">{escape(story.title)}</a>'
                if link
                else escape(story.title)
            )
            note = (
                f' <span style="color:#6b7280;">— {escape(story.why_it_matters)}</span>'
                if story.why_it_matters
                else ""
            )
            body.append(
                f'<li style="margin:0 0 9px;font:400 14px/1.55 -apple-system,Segoe UI,sans-serif;'
                f'color:#3c4149;">{title}{note}</li>'
            )
        body.append("</ul>")

    body += [
        f'<p style="margin:30px 0 0;padding-top:16px;border-top:1px solid #e6e8eb;'
        f'font:400 12px/1.6 -apple-system,Segoe UI,sans-serif;color:#8a9099;">'
        f"{brief.item_count} stories from {brief.source_count} sources · "
        f"synthesised by {escape(brief.generated_by)}<br>"
        f"Generated by threat-brief-agent</p>",
        "</div></div>",
    ]
    return "".join(body)


def render_markdown(brief: Brief, today: date | None = None) -> str:
    """The archived form — readable directly on GitHub."""
    today = today or date.today()
    lines = [
        f"# Threat Brief — {today.isoformat()}",
        "",
        f"> {brief.headline}",
        "",
        "## Top stories",
        "",
    ]

    for index, story in enumerate(brief.top_stories, start=1):
        lines.append(f"### {index}. {story.title}")
        lines.append("")
        lines.append(f"**Severity:** {story.severity}")
        lines.append("")
        if story.why_it_matters:
            lines += [story.why_it_matters, ""]
        if story.action:
            lines += [f"**Do this:** {story.action}", ""]
        for item in story.items:
            lines.append(f"- [{item.source}]({item.link})")
        lines.append("")

    if brief.also_notable:
        lines += ["## Also notable", ""]
        for story in brief.also_notable:
            link = story.items[0].link if story.items else ""
            title = f"[{story.title}]({link})" if link else story.title
            note = f" — {story.why_it_matters}" if story.why_it_matters else ""
            lines.append(f"- {title}{note}")
        lines.append("")

    lines += [
        "---",
        "",
        f"_{brief.item_count} stories from {brief.source_count} sources · "
        f"synthesised by {brief.generated_by}_",
    ]
    return "\n".join(lines)
