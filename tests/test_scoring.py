from datetime import UTC, datetime, timedelta

from agent.scoring import rank, recency_multiplier, score_item
from agent.sources import Item


def make_item(title: str, summary: str = "", hours_old: float = 1.0, weight: float = 1.0) -> Item:
    return Item(
        title=title,
        link=f"https://example.com/{abs(hash(title))}",
        source="Test Feed",
        category="security",
        published=datetime.now(UTC) - timedelta(hours=hours_old),
        summary=summary,
        source_weight=weight,
    )


def test_exploitation_signal_outranks_generic_news():
    exploited = score_item(make_item("Fortinet zero-day actively exploited in the wild"))
    generic = score_item(make_item("Startup launches new dashboard"))
    assert exploited.score > generic.score


def test_cve_identifiers_add_score():
    with_cve = score_item(make_item("Bug fixed", "Tracked as CVE-2026-12345 in the advisory"))
    without = score_item(make_item("Bug fixed", "Tracked in the advisory"))
    assert with_cve.score > without.score


def test_repeated_cves_have_diminishing_returns():
    three = score_item(make_item("Roundup", "CVE-2026-0001 CVE-2026-0002 CVE-2026-0003"))
    ten = score_item(
        make_item("Roundup", " ".join(f"CVE-2026-{n:04d}" for n in range(1, 11)))
    )
    assert ten.score == three.score


def test_promotional_content_is_penalised():
    promo = score_item(make_item("Sponsored: best deals on antivirus this Black Friday"))
    assert promo.score == 0.0


def test_recency_multiplier_decays_but_has_a_floor():
    assert recency_multiplier(0) == 1.0
    assert recency_multiplier(14) < recency_multiplier(0)
    assert recency_multiplier(500) >= 0.35


def test_critical_old_story_beats_fresh_fluff():
    old_critical = score_item(
        make_item("Critical unauthenticated RCE actively exploited", hours_old=23)
    )
    fresh_fluff = score_item(make_item("Company announces rebrand", hours_old=0.1))
    assert old_critical.score > fresh_fluff.score


def test_source_weight_breaks_ties():
    trusted = score_item(make_item("Ransomware group hits hospital", weight=1.5))
    untrusted = score_item(make_item("Ransomware group hits hospital", weight=0.5))
    assert trusted.score > untrusted.score


def test_rank_sorts_descending_and_respects_limit():
    items = [
        make_item("Zero-day actively exploited in Windows"),
        make_item("Minor UI update shipped"),
        make_item("Critical remote code execution in Apache"),
    ]
    ranked = rank(items, limit=2)
    assert len(ranked) == 2
    assert ranked[0].score >= ranked[1].score
