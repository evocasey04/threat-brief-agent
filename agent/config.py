"""Environment-driven configuration.

Every knob is an env var so the same code runs identically on a laptop with a
`.env` file and in GitHub Actions with repository secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
FEEDS_FILE = REPO_ROOT / "feeds.yaml"
ARCHIVE_DIR = REPO_ROOT / "archive"

load_dotenv(REPO_ROOT / ".env")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    weight: float = 1.0
    category: str = "general"


@dataclass
class Settings:
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_to: list[str] = field(default_factory=list)
    mail_from: str = ""

    hours: int = 24
    max_items: int = 25

    @classmethod
    def from_env(cls) -> Settings:
        user = os.getenv("SMTP_USER", "").strip()
        raw_to = os.getenv("MAIL_TO", "").strip() or user
        recipients = [addr.strip() for addr in raw_to.split(",") if addr.strip()]

        return cls(
            groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
            groq_model=os.getenv("GROQ_MODEL", "").strip() or "llama-3.3-70b-versatile",
            smtp_host=os.getenv("SMTP_HOST", "").strip() or "smtp.gmail.com",
            smtp_port=_int("SMTP_PORT", 587),
            smtp_user=user,
            smtp_password=os.getenv("SMTP_PASSWORD", "").strip(),
            mail_to=recipients,
            mail_from=os.getenv("MAIL_FROM", "").strip() or user,
            hours=_int("BRIEF_HOURS", 24),
            max_items=_int("BRIEF_MAX_ITEMS", 25),
        )

    @property
    def can_send_email(self) -> bool:
        return bool(self.smtp_user and self.smtp_password and self.mail_to)

    @property
    def can_use_llm(self) -> bool:
        return bool(self.groq_api_key)


def load_feeds(path: Path | None = None) -> list[Feed]:
    """Read `feeds.yaml`. Malformed entries are skipped rather than fatal."""
    path = path or FEEDS_FILE
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []

    feeds: list[Feed] = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("url"):
            continue
        feeds.append(
            Feed(
                name=str(entry.get("name") or entry["url"]),
                url=str(entry["url"]),
                weight=float(entry.get("weight", 1.0)),
                category=str(entry.get("category", "general")),
            )
        )
    return feeds
