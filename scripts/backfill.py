#!/usr/bin/env python3
"""
Backfill ideas for a date range using scripts/daily_idea.py.
Respects local.env if present to set environment variables (e.g., API keys).
Usage:
  python scripts/backfill.py 2025-08-10 2025-08-17
"""
from __future__ import annotations

import os
import sys
import subprocess
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
LOCAL_ENV = ROOT / "local.env"


def load_local_env(path: Path) -> dict[str, str]:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def run_for_date(d: dt.date, base_env: dict[str, str]) -> int:
    env = os.environ.copy()
    env.update(base_env)
    env["FORCE_DATE"] = d.isoformat()
    print(f"Generating idea for {d}...")
    proc = subprocess.run([sys.executable, str(SCRIPTS / "daily_idea.py")], env=env)
    # Also generate AI summary for this date's latest.json (best-effort)
    try:
        subprocess.run([sys.executable, str(SCRIPTS / "build_ai_summary.py")], env=env, check=False)
    except Exception:
        pass
    return proc.returncode


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: python scripts/backfill.py <start:YYYY-MM-DD> <end:YYYY-MM-DD>", file=sys.stderr)
        return 2
    start = dt.date.fromisoformat(argv[1])
    end = dt.date.fromisoformat(argv[2])
    if end < start:
        print("End date must be >= start date", file=sys.stderr)
        return 2

    base_env = load_local_env(LOCAL_ENV)

    d = start
    failures = 0
    while d <= end:
        code = run_for_date(d, base_env)
        if code != 0:
            print(f"Failed for {d} with exit code {code}", file=sys.stderr)
            failures += 1
        d += dt.timedelta(days=1)

    # Rebuild RSS after backfill completes
    try:
        subprocess.run([sys.executable, str(SCRIPTS / "build_rss.py")], check=False)
    except Exception:
        pass

    # Build recent.json for convenience
    try:
        subprocess.run([sys.executable, str(SCRIPTS / "build_recent.py")], check=False)
    except Exception:
        pass

    # Build archive page
    try:
        subprocess.run([sys.executable, str(SCRIPTS / "build_archive.py")], check=False)
    except Exception:
        pass

    # Build archive.json for cards page
    try:
        subprocess.run([sys.executable, str(SCRIPTS / "build_archive_json.py")], check=False)
    except Exception:
        pass

    # Optionally populate AI summaries for history (best-effort)
    try:
        subprocess.run([sys.executable, str(SCRIPTS / "build_ai_summaries_history.py")], check=False)
    except Exception:
        pass

    print("Backfill complete with", failures, "failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
