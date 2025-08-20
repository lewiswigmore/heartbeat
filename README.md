# Heartbeat

[![Daily Green Commit](https://github.com/lewiswigmore/heartbeat/actions/workflows/daily-heartbeat.yml/badge.svg)](https://github.com/lewiswigmore/heartbeat/actions/workflows/daily-heartbeat.yml)

Daily “heartbeat” commits plus a short, structured idea every day. Outputs are consumable as JSON and RSS.

## How it works

- The workflow at `.github/workflows/daily-heartbeat.yml` runs daily and on demand.
- It generates a short idea (prefers Azure OpenAI; then OpenAI; otherwise offline), writes:
   - `ideas/YYYY-MM.md` (human‑readable)
   - `ideas/YYYY-MM.jsonl` (append‑only machine feed)
   - `docs/latest.json` (tiny API for the latest idea)
   - `docs/feed.xml` (RSS of the last 20 ideas)
- It updates `.green/heartbeat.txt` and pushes back to `main`.

## Public endpoints

- Home (GitHub Pages): [https://lewiswigmore.github.io/heartbeat/](https://lewiswigmore.github.io/heartbeat/)
- Latest JSON: [docs/latest.json](https://raw.githubusercontent.com/lewiswigmore/heartbeat/main/docs/latest.json)
- RSS feed: [docs/feed.xml](https://raw.githubusercontent.com/lewiswigmore/heartbeat/main/docs/feed.xml)
- Recent JSON (last 10): [docs/recent.json](https://raw.githubusercontent.com/lewiswigmore/heartbeat/main/docs/recent.json)
- Archive page: [docs/archive.html](https://raw.githubusercontent.com/lewiswigmore/heartbeat/main/docs/archive.html)
- Recent HTML: [docs/recent.html](https://raw.githubusercontent.com/lewiswigmore/heartbeat/main/docs/recent.html)
- Monthly JSONL: `ideas/YYYY-MM.jsonl` (e.g., `ideas/2025-08.jsonl`)

Tip: Enable GitHub Pages (Settings → Pages → Deploy from branch → `main`/`/docs`) for nicer URLs like:

- [https://lewiswigmore.github.io/heartbeat/latest.json](https://lewiswigmore.github.io/heartbeat/latest.json)
- [https://lewiswigmore.github.io/heartbeat/feed.xml](https://lewiswigmore.github.io/heartbeat/feed.xml)
- [https://lewiswigmore.github.io/heartbeat/recent.json](https://lewiswigmore.github.io/heartbeat/recent.json)
- [https://lewiswigmore.github.io/heartbeat/archive.html](https://lewiswigmore.github.io/heartbeat/archive.html)
- [https://lewiswigmore.github.io/heartbeat/recent.html](https://lewiswigmore.github.io/heartbeat/recent.html)

Robots and sitemap:

- [docs/robots.txt](https://raw.githubusercontent.com/lewiswigmore/heartbeat/main/docs/robots.txt)
- [docs/sitemap.xml](https://raw.githubusercontent.com/lewiswigmore/heartbeat/main/docs/sitemap.xml)
- [https://lewiswigmore.github.io/heartbeat/robots.txt](https://lewiswigmore.github.io/heartbeat/robots.txt)
- [https://lewiswigmore.github.io/heartbeat/sitemap.xml](https://lewiswigmore.github.io/heartbeat/sitemap.xml)

## Idea format (constrained)

- concept: ≤ 8 words
- summary: ≤ 35 words
- tags: up to 5, kebab‑case
- theme: rotates daily (security → data → devtools → automation → observability → productivity → ml)
- date, slug, repo_name, source (azure/openai/offline)

Example (`docs/latest.json`):

```json
{
   "date": "2025-08-17",
   "concept": "minimal notes cli",
   "summary": "A cli that can generate and manage github issues with a focus on minimal notes.",
   "tags": ["minimal", "notes", "cli"],
   "theme": "security",
   "slug": "minimal-notes-cli",
   "repo_name": "minimal-notes-cli-2025-08-17",
   "source": "azure"
}
```

## Setup

1. In this repo: Settings → Secrets and variables → Actions → New repository secret
   - `GREEN_PAT`: Fine‑grained PAT with Contents: Read and write (or classic PAT `repo`/`public_repo`).
   - Optional: `COMMIT_USER_NAME`, `COMMIT_USER_EMAIL` to author commits as you.
   - Optional (AI): `AZURE_OPENAI_API_KEY` (+ repo variables `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`) or `OPENAI_API_KEY`.
2. Commit to `main`. Then run the workflow once via Actions to verify.

## Daily idea validation

- De‑duplicates against prior ideas in this repo (slugified title).
- Optionally searches GitHub repos (uses Actions token) to avoid name collisions.
- Makes up to 6 attempts for a unique concept; as a last resort, appends a tiny suffix.
- Disable external search via `IDEA_VALIDATE_GITHUB=false` in the workflow env.

## Backfill missing dates

If the workflow was down and you need to generate ideas for missed dates:

```bash
cd scripts
FORCE_DATE=2025-08-18 python daily_idea.py
FORCE_DATE=2025-08-19 python daily_idea.py
# Rebuild feeds
python build_recent.py
python build_rss.py
python build_jsonfeed.py
python build_archive.py
python build_archive_json.py
```

## Notes

- Commits include `[skip ci]` to avoid triggering other workflows.
- If this is a private repo, enable “Include private contributions” in your GitHub profile to see green squares.
