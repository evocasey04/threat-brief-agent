# Threat Brief Agent

An autonomous agent that reads the day's cybersecurity and tech news, decides what
actually matters, and emails you a prioritised morning brief.

It runs itself on a GitHub Actions cron schedule, costs nothing to operate, and
archives every brief it has ever written into [`archive/`](archive/).

```
RSS sources ──► normalise ──► dedupe ──► score ──► top N ──► LLM synthesis ──► email + archive
                                                              (Groq, free tier)
```

## Why this isn't just an RSS reader

A feed reader hands you 120 headlines. This hands you six paragraphs.

- **Heuristic pre-filter.** Items are scored on exploitation signals
  (`actively exploited`, `zero-day`, `CVE-`, `ransomware`, `supply chain`), source
  reliability, and recency, so the language model only ever sees the top slice.
  That keeps token use — and cost — near zero.
- **Synthesis, not summarisation.** The model is asked to group related stories,
  assign a severity, and explain *why it matters* and *what to do*, then return
  strict JSON that the renderer validates.
- **Degrades gracefully.** No API key, rate limit, or malformed response? The agent
  falls back to a heuristic brief and still ships. A scheduled job that fails
  silently is worse than a plainer email.

## Sample output

> **Top story — Critical**
> A Fortinet SSL-VPN flaw is under active exploitation and CISA has added it to KEV.
> *Why it matters:* internet-facing, pre-auth, and already weaponised — this is the
> class of bug that becomes a ransomware entry point within days.
> *What to do:* inventory FortiOS versions and patch before the weekend.

Full renders live in [`archive/`](archive/).

## Quick start

```bash
git clone https://github.com/<you>/threat-brief-agent
cd threat-brief-agent
python -m venv .venv && .venv/Scripts/activate   # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                             # fill in the values below

python -m agent.check                            # verify the LLM key and model
python -m agent.main --dry-run                   # prints the brief, sends nothing
python -m agent.main                             # renders, emails, archives
```

### Preflight

Synthesis degrades to a heuristic brief on any failure — right for an unattended
cron job, but it means a bad key or a retired model id shows up as a duller email
rather than an error. `python -m agent.check` makes those failures loud: it
confirms the key is accepted, that the configured model still exists (listing the
live alternatives if it doesn't), and that a real call returns JSON the renderer
can parse.

### Useful flags

| Flag | Effect |
| --- | --- |
| `--dry-run` | Render to stdout and `archive/`, skip the email |
| `--no-llm` | Skip the model entirely, use the heuristic brief |
| `--hours 48` | Widen the lookback window (default 24) |
| `--max-items 30` | How many scored items reach the model (default 25) |
| `--no-archive` | Don't write a file to `archive/` |

## Configuration

Everything is environment variables — nothing secret is ever committed.

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `GROQ_API_KEY` | for LLM mode | — | Free key from [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL` | no | `llama-3.3-70b-versatile` | Any Groq chat model id |
| `SMTP_HOST` | to send | `smtp.gmail.com` | |
| `SMTP_PORT` | no | `587` | STARTTLS |
| `SMTP_USER` | to send | — | Your Gmail address |
| `SMTP_PASSWORD` | to send | — | Gmail **App Password**, not your login password |
| `MAIL_TO` | to send | falls back to `SMTP_USER` | Comma-separated for several recipients |
| `MAIL_FROM` | no | falls back to `SMTP_USER` | |
| `BRIEF_HOURS` | no | `24` | Lookback window |
| `BRIEF_MAX_ITEMS` | no | `25` | Items sent to the model |

### Gmail app password

Gmail rejects your normal password over SMTP. With 2-Step Verification switched on,
visit **Google Account → Security → App passwords**, generate one for "Mail", and put
the 16-character string in `SMTP_PASSWORD`.

## Sources

Feeds live in [`feeds.yaml`](feeds.yaml) — add or remove entries, no code changes:

```yaml
- name: The Hacker News
  url: https://feeds.feedburner.com/TheHackersNews
  weight: 1.1        # nudges scoring up or down
  category: security
```

Ships with The Hacker News, BleepingComputer, Krebs on Security, CISA advisories,
Google Project Zero, Ars Technica and TechCrunch.

## Scheduling it

[`.github/workflows/daily-brief.yml`](.github/workflows/daily-brief.yml) runs the agent
at 07:00 UTC daily and commits the new archive entry back to the repo.

Add these under **Settings → Secrets and variables → Actions**:

`GROQ_API_KEY`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_TO`

Then trigger a test run from the **Actions** tab via *Run workflow*.

> GitHub disables scheduled workflows on repos with no activity for 60 days.
> The archive commit each morning counts as activity, so it keeps itself alive.

## Development

```bash
pip install -r requirements-dev.txt
pytest            # network-free unit tests
ruff check .
```

## Layout

```
agent/
  check.py       preflight for the LLM key and model id
  config.py      env-driven settings
  sources.py     RSS fetch + normalise + dedupe
  scoring.py     relevance/recency heuristics
  summarize.py   Groq synthesis + JSON validation + fallback
  render.py      HTML, plaintext and markdown renderers
  deliver.py     SMTP delivery
  main.py        orchestration + CLI
tests/           unit tests for scoring, dedupe, parsing
archive/         one markdown brief per day
```

## Licence

MIT — see [LICENSE](LICENSE).
