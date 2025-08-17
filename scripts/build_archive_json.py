#!/usr/bin/env python3
"""Build docs/archive.json containing all ideas from ideas/*.jsonl (newest first)."""
from pathlib import Path
import glob
import json

ROOT = Path(__file__).resolve().parents[1]
IDEAS = ROOT / "ideas"
DOCS = ROOT / "docs"


def load_items():
    items = []
    for p in sorted(glob.glob(str(IDEAS / "*.jsonl"))):
        try:
            for line in Path(p).read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    j = json.loads(line)
                except Exception:
                    continue
                if isinstance(j, dict) and j.get("date"):
                    items.append(j)
        except Exception:
            continue
    items.sort(key=lambda x: x.get("date", ""), reverse=True)
    return items


def main() -> int:
    items = load_items()
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "archive.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote docs/archive.json with {len(items)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
