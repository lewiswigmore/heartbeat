#!/usr/bin/env python3
"""
Daily idea generator

Writes an idea entry to ideas/YYYY-MM.md if not already present for today.
Offline generator by default; if OPENAI_API_KEY is set, will attempt to
generate via OpenAI Chat Completions API.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


ROOT = Path(__file__).resolve().parents[1]
IDEAS_DIR = ROOT / "ideas"
DOCS_DIR = ROOT / "docs"
# Auto-load local.env for local runs (no-op in CI if not present)
try:
    from .util_env import load_local_env  # type: ignore
except Exception:
    try:
        from util_env import load_local_env  # type: ignore
    except Exception:
        load_local_env = None  # type: ignore

THEMES = [
    "security",
    "data",
    "devtools",
    "automation",
    "observability",
    "productivity",
    "ml",
]


def day_theme(d: dt.date) -> str:
    # Deterministic rotation by day of year
    return THEMES[(d.timetuple().tm_yday - 1) % len(THEMES)]


def limit_words(text: str, max_words: int) -> str:
    words = re.split(r"\s+", text.strip())
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(",.;:!?")


def clean_tags(tags: list[str], max_tags: int = 5) -> list[str]:
    out = []
    seen = set()
    for t in tags:
        t2 = re.sub(r"[^a-z0-9\-]+", "-", t.lower()).strip("-")
        if t2 and t2 not in seen:
            out.append(t2)
            seen.add(t2)
        if len(out) >= max_tags:
            break
    return out


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def offline_idea_seed(today: str) -> dict:
    random.seed(today)  # deterministic per day
    adjectives = [
        "quantum",
        "minimal",
        "serverless",
        "edge",
        "ambient",
        "streaming",
        "fuzzy",
        "semantic",
        "temporal",
        "realtime",
        "zero-trust",
        "privacy-first",
        "offline-first",
        "federated",
    ]
    domains = [
        "notes",
        "search",
        "scheduler",
        "webhooks",
        "etl",
        "dashboard",
        "observability",
        "vector-store",
        "recommendations",
        "graphql-gateway",
        "audio-transcribe",
        "image-annotator",
        "feature-flags",
        "secrets-rotator",
    ]
    modalities = ["cli", "webapp", "service", "sdk", "agent", "daemon", "extension"]
    verbs = [
        "generate",
        "synchronize",
        "monitor",
        "summarize",
        "classify",
        "transcode",
        "index",
        "simulate",
        "scrape",
        "normalize",
        "visualize",
    ]
    targets = [
        "github issues",
        "rss feeds",
        "email",
        "log files",
        "browser history",
        "api responses",
        "pdfs",
        "screenshots",
        "terminal sessions",
        "config files",
    ]

    adj = random.choice(adjectives)
    dom = random.choice(domains)
    mod = random.choice(modalities)
    verb = random.choice(verbs)
    tgt = random.choice(targets)

    title = f"{adj} {dom} {mod}"
    summary = f"A {mod} that can {verb} and manage {tgt} with a focus on {adj} {dom}."
    tags = sorted({adj, dom, mod})
    return {"title": title, "summary": summary, "tags": tags}


def openai_idea(today: str, api_key: str) -> dict | None:
    """Use OpenAI Chat Completions to generate an idea. Returns None on failure."""
    try:
        prompt = (
            "You are an expert product ideation assistant. Generate one concise, original "
            "open-source repository idea that likely does not already exist. Return ONLY: "
            "title (<= 8 words) and summary (<= 35 words) and 3-5 tags. Avoid controversial topics."
        )
        body = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "Be practical and inventive."},
                {"role": "user", "content": f"Date: {today}. {prompt}"},
            ],
            "temperature": 0.8,
            "max_tokens": 180,
        }
        req = Request(
            url="https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        content = data["choices"][0]["message"]["content"].strip()
        # crude parse: look for lines like Title:, Summary:, Tags:
        title_match = re.search(r"(?i)title\s*[:\-]\s*(.+)", content)
        summary_match = re.search(r"(?i)summary\s*[:\-]\s*(.+)", content)
        tags_match = re.search(r"(?i)tags\s*[:\-]\s*(.+)", content)
        title = title_match.group(1).strip() if title_match else content.splitlines()[0][:60]
        summary = summary_match.group(1).strip() if summary_match else ""
        tags = []
        if tags_match:
            tags = [t.strip().strip("#") for t in re.split(r"[,|]", tags_match.group(1)) if t.strip()]
        return {"title": title, "summary": summary, "tags": tags[:5]}
    except (URLError, HTTPError, KeyError, IndexError, TimeoutError, Exception):
        return None


def azure_openai_idea(
    today: str,
    endpoint: str,
    deployment: str,
    api_version: str,
    api_key: str,
) -> dict | None:
    """Use Azure OpenAI Chat Completions to generate an idea. Returns None on failure.

    Expects endpoint like 'https://your-resource.openai.azure.com', deployment name, and api_version.
    """
    try:
        endpoint = endpoint.rstrip("/")
        url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
        prompt = (
            "You are an expert product ideation assistant. Generate one concise, original "
            "open-source repository idea that likely does not already exist. Return ONLY: "
            "title (<= 8 words) and summary (<= 35 words) and 3-5 tags. Avoid controversial topics."
        )
        body = {
            # For Azure, omit 'model' when targeting a deployment
            "messages": [
                {"role": "system", "content": "Be practical and inventive."},
                {"role": "user", "content": f"Date: {today}. {prompt}"},
            ],
            "temperature": 0.8,
            "max_tokens": 180,
        }
        req = Request(
            url=url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "api-key": api_key,
            },
            method="POST",
        )
        with urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        content = data["choices"][0]["message"]["content"].strip()
        title_match = re.search(r"(?i)title\s*[:\-]\s*(.+)", content)
        summary_match = re.search(r"(?i)summary\s*[:\-]\s*(.+)", content)
        tags_match = re.search(r"(?i)tags\s*[:\-]\s*(.+)", content)
        title = title_match.group(1).strip() if title_match else content.splitlines()[0][:60]
        summary = summary_match.group(1).strip() if summary_match else ""
        tags = []
        if tags_match:
            tags = [t.strip().strip("#") for t in re.split(r"[,|]", tags_match.group(1)) if t.strip()]
        return {"title": title, "summary": summary, "tags": tags[:5]}
    except (URLError, HTTPError, KeyError, IndexError, TimeoutError, Exception):
        return None


def list_existing_idea_slugs() -> set[str]:
    """Scan ideas/*.md and collect slugs from all existing idea headings."""
    slugs: set[str] = set()
    if not IDEAS_DIR.exists():
        return slugs
    for p in sorted(IDEAS_DIR.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line in text.splitlines():
            # Match lines like: ### YYYY-MM-DD — Title
            m = re.match(r"^###\s+\d{4}-\d{2}-\d{2}\s+[—-]\s+(.+)$", line.strip())
            if m:
                title = m.group(1).strip()
                slugs.add(slugify(title))
    return slugs


def github_repo_name_exists(slug: str, token: str | None) -> bool:
    """Naive GitHub search for an existing repo with the same name.

    Returns True if a repo named exactly `slug` is found. Requires a token.
    """
    if not token:
        return False
    try:
        q = f"{slug} in:name"
        url = f"https://api.github.com/search/repositories?q={q}&per_page=5"
        req = Request(
            url=url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
            },
            method="GET",
        )
        with urlopen(req, timeout=15) as resp:
            data = json.load(resp)
        for item in data.get("items", [])[:5]:
            name = str(item.get("name", "")).lower()
            if name == slug.lower():
                return True
        return False
    except Exception:
        # Fail open: if search fails, don't block idea creation
        return False


def main() -> int:
    # Load local env if available
    if callable(load_local_env):  # type: ignore
        load_local_env()
    # Allow overriding date for backfill
    if os.getenv("FORCE_DATE"):
        today_dt = dt.date.fromisoformat(os.environ["FORCE_DATE"])  # type: ignore[arg-type]
    else:
        today_dt = dt.datetime.utcnow().date()
    today = today_dt.isoformat()
    month_path = IDEAS_DIR / f"{today[:7]}.md"
    month_jsonl = IDEAS_DIR / f"{today[:7]}.jsonl"
    IDEAS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # Idempotency: if today's date already in file, skip
    if month_path.exists() and today in month_path.read_text(encoding="utf-8", errors="ignore"):
        print("Idea already logged for today; skipping.")
        return 0

    idea = None

    # Build seen slugs set for de-duplication inside this repo
    seen_slugs = list_existing_idea_slugs()
    gh_token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("GREEN_PAT")
    validate_gh = os.getenv("IDEA_VALIDATE_GITHUB", "true").lower() not in {"0", "false", "no"}

    def is_unique(slug: str) -> bool:
        if slug in seen_slugs:
            return False
        if validate_gh and github_repo_name_exists(slug, gh_token):
            return False
        return True

    # Try multiple attempts to obtain a unique idea
    attempts = 6
    for attempt in range(attempts):
        # Prefer Azure OpenAI if configured
        az_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        az_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        az_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        az_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

        candidate = None
        if az_api_key and az_endpoint and az_deployment:
            # Optionally guide the model to avoid seen titles
            candidate = azure_openai_idea(today, az_endpoint, az_deployment, az_api_version, az_api_key)

        if not candidate:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                candidate = openai_idea(today, api_key)

        if not candidate:
            # Offline fallback with small perturbation per attempt
            candidate = offline_idea_seed(f"{today}-{attempt}")

        title_try = candidate.get("title", "Untitled Idea").strip()
        slug_try = slugify(title_try) or f"idea-{attempt}"

        if is_unique(slug_try):
            idea = candidate
            break
        else:
            # Nudge uniqueness by appending a subtle qualifier
            candidate["title"] = f"{title_try} ({attempt+1})"
            slug_try2 = slugify(candidate["title"])
            if is_unique(slug_try2):
                idea = candidate
                break

    if not idea:
        # As a last resort create a unique slug with a small random suffix
        base = offline_idea_seed(today)
        suffix = ("".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(4)))
        base["title"] = f"{base['title']} {suffix}"
        idea = base
    if not idea:
        idea = offline_idea_seed(today)

    # Normalize and constrain fields
    raw_title = idea.get("title", "Untitled Idea").strip()
    title = limit_words(raw_title, 8)
    raw_summary = idea.get("summary", "").strip()
    summary = limit_words(raw_summary, 35)
    tags = clean_tags(idea.get("tags", []))
    theme = day_theme(today_dt)

    # Ensure a mostly-unique repo name suggestion
    slug = slugify(title) or "idea"
    repo_name = f"{slug}-{today}"

    entry = [
        f"### {today} — {title}",
        "",
        f"Theme: `{theme}`",
        f"Repo: `{repo_name}`",
        ("Tags: " + ", ".join(f"`{t}`" for t in tags)) if tags else "",
        "",
        f"Summary: {summary}" if summary else "",
        "",
    ]
    # Remove empty lines produced by optional fields
    entry = [line for line in entry if line != ""]

    if not month_path.exists():
        header = [
            f"# Idea Log — {today[:7]}",
            "",
            "Daily repository ideas (generated automatically).",
            "",
        ]
        month_path.write_text("\n".join(header + entry) + "\n", encoding="utf-8")
    else:
        with month_path.open("a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(entry) + "\n")

    # Write JSON artifacts
    record = {
        "date": today,
        "concept": title,
        "summary": summary,
        "tags": tags,
        "theme": theme,
        "slug": slug,
        "repo_name": repo_name,
        "source": ("azure" if os.getenv("AZURE_OPENAI_API_KEY") else ("openai" if os.getenv("OPENAI_API_KEY") else "offline")),
    }
    # .green/todays_idea.json for downstream steps
    green_json = ROOT / ".green" / "todays_idea.json"
    green_json.parent.mkdir(parents=True, exist_ok=True)
    green_json.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    # Append to JSONL for the month
    already = False
    if month_jsonl.exists():
        try:
            for line in month_jsonl.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("date") == today:
                    already = True
                    break
        except Exception:
            pass
    if not already:
        with month_jsonl.open("a", encoding="utf-8") as jf:
            jf.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Also write a public latest.json for consumers (usable as a tiny API)
    (DOCS_DIR / "latest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote idea to {month_path} and updated JSON outputs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
