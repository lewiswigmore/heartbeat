#!/usr/bin/env python3
"""
Build a JSON Feed (https://jsonfeed.org/version/1) from ideas/*.md
Outputs to docs/feed.json
"""
import datetime as dt
import html
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDEAS_DIR = ROOT / "ideas"
DOCS_DIR = ROOT / "docs"


def _get_repo_slug() -> str:
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
    for path in sorted(IDEAS_DIR.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            if line.startswith("### ") and " — " in line:
                title_line = line[4:].strip()
                try:
                    date_str, title = title_line.split(" — ", 1)
                except ValueError:
                    continue
                desc_lines = []
                for l in lines[idx + 1 :]:
                    if l.startswith("### "):
                        break
                    desc_lines.append(l)
                description = "\n".join(desc_lines).strip()[:800]
                yield {
                    "date": date_str,
                    "title": title.strip(),
                    "relpath": path.relative_to(ROOT).as_posix(),
                    "description": description,
                }


def build_json_feed():
    items = list(parse_entries())
    if not items:
        return
    items = items[-20:]

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    repo_slug = _get_repo_slug()
    owner, repo = repo_slug.split("/", 1)
    home_url = f"https://{owner}.github.io/{repo}/"
    feed_url = home_url + "feed.json"

    feed = {
        "version": "https://jsonfeed.org/version/1",
        "title": "Daily Ideas",
        "home_page_url": home_url,
        "feed_url": feed_url,
        "description": "Latest daily repo ideas",
        "items": [],
    }

    for it in items:
        try:
            pub_dt = dt.datetime.fromisoformat(it["date"]).replace(tzinfo=dt.timezone.utc)
        except Exception:
            pub_dt = dt.datetime.now(dt.timezone.utc)
        link = f"https://github.com/{repo_slug}/blob/main/{it['relpath']}"
        feed["items"].append({
            "id": link,
            "url": link,
            "title": html.escape(it["title"]),
            "content_text": it["description"],
            "date_published": pub_dt.isoformat().replace("+00:00", "Z"),
        })

    (DOCS_DIR / "feed.json").write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrote docs/feed.json")


if __name__ == "__main__":
    build_json_feed()
