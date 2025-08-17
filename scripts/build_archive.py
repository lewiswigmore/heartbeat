#!/usr/bin/env python3
"""Generate docs/archive.html listing monthly idea files with quick links.
Links point to GitHub for markdown and to raw.githubusercontent for JSONL.
"""
from __future__ import annotations

import glob
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDEAS = ROOT / "ideas"
DOCS = ROOT / "docs"


def get_repo_slug() -> str:
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


def count_entries_md(path: Path) -> int:
    try:
        txt = path.read_text(encoding="utf-8")
        return sum(1 for line in txt.splitlines() if line.startswith("### ") and " — " in line)
    except Exception:
        return 0


def count_entries_jsonl(path: Path) -> int:
    try:
        return sum(1 for _ in path.read_text(encoding="utf-8").splitlines() if _.strip())
    except Exception:
        return 0


def build() -> None:
    repo = get_repo_slug()
    months = {}
    for md in glob.glob(str(IDEAS / "*.md")):
        m = Path(md).stem  # YYYY-MM
        months.setdefault(m, {})["md"] = Path(md)
    for jl in glob.glob(str(IDEAS / "*.jsonl")):
        m = Path(jl).stem  # YYYY-MM
        months.setdefault(m, {})["jsonl"] = Path(jl)
    # Sort months descending
    ordered = sorted(months.items(), key=lambda kv: kv[0], reverse=True)

    DOCS.mkdir(parents=True, exist_ok=True)

    rows = []
    for m, files in ordered:
        md = files.get("md")
        jl = files.get("jsonl")
        md_count = count_entries_md(md) if md else 0
        jl_count = count_entries_jsonl(jl) if jl else 0
        md_link = f"https://github.com/{repo}/blob/main/ideas/{m}.md" if md else ""
        jl_link = f"https://raw.githubusercontent.com/{repo}/main/ideas/{m}.jsonl" if jl else ""
        row = "<tr>" \
              f"<td><strong>{m}</strong></td>" \
              f"<td>{md_count}</td>" \
              f"<td>{jl_count}</td>" \
              "<td>" \
              + (f"<a href=\"{md_link}\">Markdown</a>" if md_link else "") \
              + (" &middot; " if md_link and jl_link else "") \
              + (f"<a href=\"{jl_link}\">JSONL</a>" if jl_link else "") \
              + "</td></tr>"
        rows.append(row)

    table_rows = "".join(rows) if rows else '<tr><td colspan="4" class="muted">No data yet.</td></tr>'
    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>Heartbeat • Archive</title>
  <style>
    :root {{ color-scheme: light dark; --accent:#0078D4; --bg:#f6f8fa; --card:#fff; --text:#111827; --muted:#6b7280; --border:#e5e7eb; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --bg:#0b0c0e; --card:#111316; --text:#e5e7eb; --muted:#9ca3af; --border:#1f2937; }} }}
    body {{ margin:0; font-family:Segoe UI,system-ui,-apple-system,Roboto,Arial; background:var(--bg); color:var(--text); padding:24px; display:grid; place-items:center; }}
    .shell {{ width:100%; max-width:980px; }}
    header {{ text-align:center; margin-bottom:16px; }}
    h1 {{ margin:.25rem 0; font-size:1.6rem; }}
    .muted {{ color:var(--muted); }}
    .card {{ background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 20px; }}
    table {{ width:100%; border-collapse: collapse; }}
    th,td {{ border-bottom:1px solid var(--border); text-align:left; padding:10px; }}
    th {{ font-weight:600; font-size:.95rem; }}
    a {{ color:#0969da; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .actions {{ margin-top:12px; text-align:center; }}
  </style>
</head>
<body>
  <div class=\"shell\">
    <header>
      <h1>Archive</h1>
      <div class=\"muted\">Monthly idea logs with quick links</div>
    </header>
    <section class=\"card\">
      <table>
        <thead><tr><th>Month</th><th>Entries (MD)</th><th>Entries (JSONL)</th><th>Links</th></tr></thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
      <div class=\"actions\">
        <a href=\"./index.html\">Home</a> · 
        <a href=\"./latest.json\">Latest JSON</a> · 
        <a href=\"./recent.json\">Recent JSON</a> · 
        <a href=\"./feed.xml\">RSS</a>
      </div>
    </section>
  </div>
</body>
</html>
"""

    (DOCS / "archive.html").write_text(html, encoding="utf-8")
    print("Wrote docs/archive.html")


if __name__ == "__main__":
    build()
