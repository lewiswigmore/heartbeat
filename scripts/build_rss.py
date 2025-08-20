#!/usr/bin/env python3
"""
Build a simple RSS feed from ideas/*.md and docs/latest.json
Outputs to docs/feed.xml
"""
import datetime as dt
import html
import json
import os
import subprocess
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDEAS_DIR = ROOT / "ideas"
DOCS_DIR = ROOT / "docs"


def _get_repo_slug() -> str:
    """Return 'owner/repo' for links.
    Order of preference:
    - REPO_SLUG env var
    - GITHUB_REPOSITORY env var
    - Parse `git remote get-url origin`
    - Fallback to 'lewiswigmore/heartbeat'
    """
    slug = os.getenv("REPO_SLUG") or os.getenv("GITHUB_REPOSITORY")
    if slug:
        return slug
    try:
        res = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        url = (res.stdout or "").strip()
        if url:
            if url.startswith("http") and "github.com" in url:
                parts = url.split("github.com/")[-1].replace(".git", "").strip("/")
                if parts.count("/") == 1:
                    return parts
            if url.startswith("git@github.com:"):
                parts = url.split(":", 1)[1].replace(".git", "").strip("/")
                if parts.count("/") == 1:
                    return parts
    except Exception:
        pass
    return "lewiswigmore/heartbeat"


def parse_entries():
    """Parse both markdown and JSONL files to get complete entry data with unique identifiers"""
    # First load JSONL data for metadata
    jsonl_data = {}
    for jsonl_path in sorted(IDEAS_DIR.glob("*.jsonl")):
        try:
            for line in jsonl_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if data.get("date"):
                        jsonl_data[data["date"]] = data
                except Exception:
                    continue
        except Exception:
            continue
    
    # Parse markdown monthly files for entries
    for path in sorted(IDEAS_DIR.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        # Split by headings that start with '### YYYY-MM-DD — '
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            if line.startswith("### ") and " — " in line:
                title_line = line[4:].strip()
                try:
                    date_str, title = title_line.split(" — ", 1)
                except ValueError:
                    continue
                # Capture lines until the next '### '
                desc_lines = []
                for l in lines[idx + 1 :]:
                    if l.startswith("### "):
                        break
                    desc_lines.append(l)
                description = html.escape("\n".join(desc_lines).strip()[:800])
                
                # Get additional metadata from JSONL if available
                jsonl_entry = jsonl_data.get(date_str, {})
                guid = jsonl_entry.get("repo_name") or jsonl_entry.get("slug") or f"{date_str}-{title.lower().replace(' ', '-')}"
                
                yield {
                    "date": date_str,
                    "title": title.strip(),
                    "relpath": path.relative_to(ROOT).as_posix(),
                    "description": description,
                    "guid": guid,
                    "slug": jsonl_entry.get("slug", ""),
                }


def build_feed():
    items = list(parse_entries())
    if not items:
        return
    items = items[-20:]

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = format_datetime(dt.datetime.now(dt.timezone.utc))
    repo_slug = _get_repo_slug()
    owner, repo = repo_slug.split("/", 1) if "/" in repo_slug else ("", repo_slug)
    feed_url = f"https://{owner}.github.io/{repo}/feed.xml" if owner else f"https://raw.githubusercontent.com/{repo_slug}/main/docs/feed.xml"

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '<channel>',
        '<title>Daily Ideas</title>',
        f'<link>https://github.com/{repo_slug}</link>',
        '<description>Latest daily repo ideas</description>',
        f'<lastBuildDate>{now}</lastBuildDate>',
        f'<atom:link href="{feed_url}" rel="self" type="application/rss+xml" />',
    ]

    for it in items:
        try:
            pub_dt = dt.datetime.fromisoformat(it["date"]).replace(tzinfo=dt.timezone.utc)
        except Exception:
            pub_dt = dt.datetime.now(dt.timezone.utc)
        pub = format_datetime(pub_dt)
        link = f"https://github.com/{repo_slug}/blob/main/{it['relpath']}"
        # Use repo_name as GUID if available, otherwise create one from date and slug
        guid = html.escape(it["guid"])
        
        xml += [
            '<item>',
            f'<title>{html.escape(it["title"])}</title>',
            f'<link>{link}</link>',
            f'<guid isPermaLink="false">{guid}</guid>',
            f'<pubDate>{pub}</pubDate>',
            f'<description>{it["description"]}</description>',
            '</item>',
        ]

    xml += ['</channel>', '</rss>']
    (DOCS_DIR / 'feed.xml').write_text("\n".join(xml), encoding='utf-8')
    print("Wrote docs/feed.xml")


if __name__ == "__main__":
    build_feed()
