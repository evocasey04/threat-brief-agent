from datetime import UTC, datetime, timedelta

from agent.sources import Item, canonical_url, clean_text, dedupe, title_key, within_window


def make_item(title: str, link: str, hours_old: float = 1.0) -> Item:
    return Item(
        title=title,
        link=link,
        source="Test Feed",
        category="security",
        published=datetime.now(UTC) - timedelta(hours=hours_old),
    )


def test_clean_text_strips_html_and_entities():
    assert clean_text("<p>Hello &amp; <b>welcome</b></p>") == "Hello & welcome"


def test_clean_text_truncates_on_a_word_boundary():
    result = clean_text("word " * 200, limit=40)
    assert len(result) <= 41
    assert result.endswith("…")


def test_canonical_url_drops_tracking_and_normalises():
    assert canonical_url(
        "https://WWW.Example.com/story/?utm_source=rss&id=7#top"
    ) == "https://example.com/story?id=7"


def test_canonical_url_ignores_trailing_slash():
    assert canonical_url("https://example.com/a/") == canonical_url("https://example.com/a")


def test_title_key_ignores_stopwords():
    assert title_key("The new zero-day in Chrome") == title_key("A zero day Chrome")


def test_dedupe_collapses_same_url_with_different_tracking():
    items = [
        make_item("Story one", "https://example.com/a?utm_source=feed"),
        make_item("Different words entirely here", "https://example.com/a"),
    ]
    assert len(dedupe(items)) == 1


def test_dedupe_collapses_same_story_from_two_outlets():
    items = [
        make_item("Fortinet zero-day exploited by ransomware crew", "https://a.com/1"),
        make_item("Fortinet zero day exploited by ransomware crew", "https://b.com/2"),
    ]
    assert len(dedupe(items)) == 1


def test_dedupe_keeps_distinct_stories():
    items = [
        make_item("Chrome patches sandbox escape", "https://a.com/1"),
        make_item("Cisco warns of firewall backdoor", "https://b.com/2"),
    ]
    assert len(dedupe(items)) == 2


def test_within_window_excludes_stale_items():
    items = [make_item("Fresh", "https://a.com/1", 2), make_item("Stale", "https://a.com/2", 50)]
    kept = within_window(items, hours=24)
    assert [i.title for i in kept] == ["Fresh"]
