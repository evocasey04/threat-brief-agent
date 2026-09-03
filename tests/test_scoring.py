from datetime import UTC, datetime, timedelta

from agent.scoring import (
    PENALTY_PATTERNS,
    SIGNAL_PATTERNS,
    VENDOR_PATTERNS,
    rank,
    recency_multiplier,
    score_item,
)
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

# --- Word-boundary matching -------------------------------------------------
#
# Matching used to be plain substring containment, which scored "flaws" as aws,
# "scenarios" and "FortiOS" as ios, and "adapt" as apt. Those words are ordinary
# security prose, so nearly every item picked up bonuses it had not earned.


def phrase_hits(text: str) -> set[str]:
    """Every signal/vendor/penalty phrase that fires on some text."""
    haystack = text.lower()
    return {
        key
        for table in (SIGNAL_PATTERNS, VENDOR_PATTERNS, PENALTY_PATTERNS)
        for key, pattern in table.items()
        if pattern.search(haystack)
    }


def test_substrings_of_ordinary_words_do_not_score():
    assert phrase_hits("Fortinet discloses two flaws in FortiOS") == {"fortinet"}
    assert phrase_hits("Researchers adapt previous scenarios for various attacks") == set()
    assert phrase_hits("New laws capture a chapter of the privacy debate") == set()


def test_real_mentions_still_score():
    assert "aws" in phrase_hits("AWS S3 bucket misconfiguration exposes records")
    assert "ios" in phrase_hits("Apple ships iOS 19 emergency update")
    assert "microsoft" in phrase_hits("Microsoft patches 60 flaws")


def test_apt_matches_numbered_threat_groups_but_not_adapt():
    assert "apt" in phrase_hits("APT29 backdoors European embassies")
    assert "apt" in phrase_hits("APT41 members indicted")
    assert "apt" in phrase_hits("The apt group shifted infrastructure")
    assert "apt" not in phrase_hits("Defenders adapt to the new tooling")
    assert "apt" not in phrase_hits("An aptitude for evasion")


def test_hyphens_spaces_and_plurals_are_interchangeable():
    for variant in ("zero-day", "zero day", "zero-days", "Zero Day"):
        assert "zero-day" in phrase_hits(f"A {variant} is being exploited")

    assert "data breach" in phrase_hits("Three data breaches disclosed")
    assert "supply chain" in phrase_hits("A supply-chain compromise at the vendor")


def test_phrases_ending_in_punctuation_still_match():
    assert "raises $" in phrase_hits("Startup raises $12M in Series A")


def test_scores_reflect_the_corrected_matching():
    """A plain vendor-free headline should no longer inherit an aws/ios bonus."""
    plain = score_item(make_item(title="Researchers describe flaws in various scenarios"))
    assert plain.score == 0.0
    assert plain.reasons == []
