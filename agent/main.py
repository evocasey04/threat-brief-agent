"""Entry point: ingest → rank → synthesise → render → deliver → archive."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from . import use_utf8_stdout
from .config import ARCHIVE_DIR, Settings, load_feeds
from .deliver import send_email
from .render import render_html, render_markdown, render_text, subject_line
from .scoring import rank
from .sources import collect, fetch_feed
from .summarize import build_brief

log = logging.getLogger("agent")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="threat-brief-agent",
        description="Build and email a prioritised daily cybersecurity brief.",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the brief, send no email")
    parser.add_argument("--no-llm", action="store_true", help="skip the model, use heuristics only")
    parser.add_argument("--no-archive", action="store_true", help="don't write to archive/")
    parser.add_argument("--hours", type=int, help="lookback window in hours (default 24)")
    parser.add_argument("--max-items", type=int, help="items sent to the model (default 25)")
    parser.add_argument(
        "--check-feeds",
        action="store_true",
        help="fetch every feed, report entry counts, exit non-zero if any is dead",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser.parse_args(argv)


def write_archive(markdown: str, today: date) -> str:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = ARCHIVE_DIR / f"{today.isoformat()}.md"
    path.write_text(markdown, encoding="utf-8")
    log.info("archived to %s", path)
    return str(path)


def check_feeds(feeds: list) -> int:
    """Report how many entries each feed yields; non-zero if any yields none.

    `fetch_feed` swallows failures by design -- a partial brief beats no brief --
    which means a source can rot and only ever show up as a log line nobody
    reads. This surfaces it. SANS ISC died exactly this way.
    """
    dead: list[str] = []
    for feed in feeds:
        count = len(fetch_feed(feed))
        status = "ok  " if count else "DEAD"
        print(f"[{status}] {count:>3} entries  {feed.name} - {feed.url}")
        if not count:
            dead.append(feed.name)

    if dead:
        print(f"\n{len(dead)} of {len(feeds)} feeds returned nothing: {', '.join(dead)}")
        return 1

    print(f"\nAll {len(feeds)} feeds are live.")
    return 0


def run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    hours = args.hours or settings.hours
    max_items = args.max_items or settings.max_items
    today = date.today()

    feeds = load_feeds()
    if not feeds:
        log.error("no feeds configured in feeds.yaml")
        return 1

    if args.check_feeds:
        return check_feeds(feeds)

    items = collect(feeds, hours)
    shortlist = rank(items, limit=max_items)

    if not shortlist:
        log.warning("no items in the last %dh — nothing to brief", hours)

    for item in shortlist[:5]:
        log.debug("%6.2f  %s (%s)", item.score, item.title[:70], ", ".join(item.reasons[:4]))

    brief = build_brief(
        shortlist,
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        use_llm=not args.no_llm,
    )

    subject = subject_line(brief, today)
    text_body = render_text(brief, today)
    html_body = render_html(brief, today)

    if not args.no_archive:
        write_archive(render_markdown(brief, today), today)

    if args.dry_run:
        print(f"\nSubject: {subject}\n")
        print(text_body)
        return 0

    if not settings.can_send_email:
        log.error(
            "email not configured — set SMTP_USER, SMTP_PASSWORD and MAIL_TO, "
            "or run with --dry-run"
        )
        return 2

    try:
        send_email(
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            sender=settings.mail_from,
            recipients=settings.mail_to,
        )
    except Exception as exc:
        log.error("email delivery failed: %s", exc)
        return 3

    return 0


def main(argv: list[str] | None = None) -> int:
    use_utf8_stdout()
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
