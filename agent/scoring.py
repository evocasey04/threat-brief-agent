"""Heuristic relevance scoring.

The point of this module is cost control and signal. Roughly 100–150 items land
in the window each day; only the top ~25 are worth a language model's attention.
Scoring is deliberately transparent — every item carries the list of reasons it
scored the way it did, which makes the ranking debuggable.
"""

from __future__ import annotations

import math
import re

from .sources import Item

# Phrases that signal something is happening *now*, not being discussed in theory.
SIGNALS: dict[str, float] = {
    "actively exploited": 6.0,
    "exploited in the wild": 6.0,
    "in the wild": 3.5,
    "zero-day": 5.5,
    "0-day": 5.5,
    "emergency patch": 5.0,
    "out-of-band": 4.0,
    "known exploited": 5.0,
    "kev catalog": 5.0,
    "proof-of-concept": 3.0,
    "unauthenticated": 3.5,
    "remote code execution": 4.5,
    "pre-auth": 3.5,
    "privilege escalation": 2.5,
    "critical": 3.0,
    "ransomware": 3.5,
    "data breach": 3.0,
    "supply chain": 3.5,
    "backdoor": 3.5,
    "malware": 2.0,
    "phishing": 1.5,
    "patch tuesday": 3.5,
    "advisory": 2.0,
    "vulnerability": 2.0,
    "leaked": 2.0,
    "credential": 2.0,
    "botnet": 2.0,
    "nation-state": 3.0,
    "apt": 2.5,
}

# Widely deployed technology — a bug here has blast radius.
HIGH_IMPACT_VENDORS: dict[str, float] = {
    "microsoft": 2.0,
    "windows": 2.0,
    "active directory": 2.5,
    "azure": 2.0,
    "aws": 2.0,
    "google": 1.5,
    "chrome": 2.0,
    "linux": 1.5,
    "openssh": 2.5,
    "openssl": 2.5,
    "cisco": 2.0,
    "fortinet": 2.5,
    "ivanti": 2.5,
    "palo alto": 2.2,
    "citrix": 2.2,
    "vmware": 2.0,
    "apache": 2.0,
    "kubernetes": 2.0,
    "docker": 1.5,
    "jenkins": 1.5,
    "wordpress": 1.5,
    "android": 1.5,
    "ios": 1.5,
    "apple": 1.5,
    "sharepoint": 2.0,
    "exchange": 2.2,
}

# Stories that are usually noise in a security brief.
PENALTIES: dict[str, float] = {
    "sponsored": -6.0,
    "webinar": -5.0,
    "deal of the day": -6.0,
    "best deals": -6.0,
    "coupon": -6.0,
    "giveaway": -5.0,
    "black friday": -5.0,
    "hiring": -3.0,
    "funding round": -1.5,
    "raises $": -1.5,
}

# Phrases whose real-world form doesn't fit the generic word-boundary rule.
PATTERN_OVERRIDES: dict[str, re.Pattern[str]] = {
    # Threat groups carry a number -- APT29, APT41 -- so a trailing digit has to
    # be allowed here, while "adapt" and "aptitude" still must not match.
    "apt": re.compile(r"(?<![a-z0-9])apt\d*(?![a-z])"),
}


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    """Compile a phrase into a whole-word matcher.

    Plain substring matching quietly mis-scored ordinary prose: "flaws" counted
    as `aws`, "scenarios" and "FortiOS" as `ios`, "adapt" and "capture" as `apt`.
    Since "flaws" appears in roughly every other security headline, almost every
    item collected a bonus it had not earned -- and `reasons`, which exists to
    make the ranking debuggable, was lying about why.

    Boundaries are alphanumeric lookarounds rather than \\b so a phrase ending in
    punctuation (`raises $`) still works. Internal hyphens and spaces are
    interchangeable and optional, so "zero-day", "zero day" and "zeroday" all hit
    one entry, and a trailing plural is tolerated ("zero-days", "data breaches").
    """
    if phrase in PATTERN_OVERRIDES:
        return PATTERN_OVERRIDES[phrase]

    body = r"[-\s]?".join(re.escape(part) for part in re.split(r"[-\s]+", phrase))
    prefix = r"(?<![a-z0-9])" if phrase[0].isalnum() else ""
    suffix = r"(?:e?s)?(?![a-z0-9])" if phrase[-1].isalnum() else ""
    return re.compile(prefix + body + suffix)


SIGNAL_PATTERNS = {phrase: _phrase_pattern(phrase) for phrase in SIGNALS}
VENDOR_PATTERNS = {vendor: _phrase_pattern(vendor) for vendor in HIGH_IMPACT_VENDORS}
PENALTY_PATTERNS = {phrase: _phrase_pattern(phrase) for phrase in PENALTIES}

CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
CVSS_RE = re.compile(r"\bCVSS[^\d]{0,12}(10(?:\.0)?|9(?:\.\d)?)\b", re.IGNORECASE)

RECENCY_HALF_LIFE_HOURS = 14.0


def recency_multiplier(age_hours: float, half_life: float = RECENCY_HALF_LIFE_HOURS) -> float:
    """Exponential decay in [0.35, 1.0]. Fresh news wins ties, old news survives.

    The floor matters: a genuinely critical story from 23 hours ago should still
    outrank fluff published ten minutes ago.
    """
    decayed = math.pow(0.5, age_hours / half_life)
    return 0.35 + 0.65 * decayed


def score_item(item: Item) -> Item:
    """Score one item in place and record why. Returns the same item for chaining."""
    haystack = f"{item.title} {item.summary}".lower()
    base = 0.0
    reasons: list[str] = []

    for phrase, weight in SIGNALS.items():
        if SIGNAL_PATTERNS[phrase].search(haystack):
            base += weight
            reasons.append(phrase)

    for vendor, weight in HIGH_IMPACT_VENDORS.items():
        if VENDOR_PATTERNS[vendor].search(haystack):
            base += weight
            reasons.append(vendor)

    for phrase, weight in PENALTIES.items():
        if PENALTY_PATTERNS[phrase].search(haystack):
            base += weight
            reasons.append(f"penalty:{phrase.strip()}")

    cves = CVE_RE.findall(haystack)
    if cves:
        # Diminishing returns: a roundup of 40 CVEs isn't 40x a single critical one.
        base += min(len(set(cves)), 3) * 2.0
        reasons.append(f"{len(set(cves))} CVE(s)")

    if CVSS_RE.search(haystack):
        base += 3.0
        reasons.append("CVSS 9+")

    # Title hits count double — headlines are the editor's own signal of importance.
    title_lower = item.title.lower()
    title_bonus = (
        sum(w for p, w in SIGNALS.items() if SIGNAL_PATTERNS[p].search(title_lower)) * 0.5
    )
    if title_bonus:
        base += title_bonus
        reasons.append("headline signal")

    item.score = round(max(base, 0.0) * item.source_weight * recency_multiplier(item.age_hours), 3)
    item.reasons = reasons
    return item


def rank(items: list[Item], limit: int | None = None) -> list[Item]:
    """Score every item and return them highest-first."""
    scored = [score_item(item) for item in items]
    scored.sort(key=lambda i: (-i.score, i.age_hours))
    return scored[:limit] if limit else scored
