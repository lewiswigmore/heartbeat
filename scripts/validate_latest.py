#!/usr/bin/env python3
"""Validate docs/latest.json against docs/latest.schema.json"""
from pathlib import Path
import json
import sys

try:
    from jsonschema import Draft7Validator
except Exception:
    print("jsonschema not installed. Run: pip install jsonschema", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs" / "latest.schema.json"
DATA = ROOT / "docs" / "latest.json"

schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
if not DATA.exists():
    print("docs/latest.json not found; skipping validation (no data).", file=sys.stderr)
    sys.exit(0)

obj = json.loads(DATA.read_text(encoding="utf-8"))
errors = sorted(Draft7Validator(schema).iter_errors(obj), key=lambda e: e.path)
if errors:
    for e in errors:
        path = "/".join([str(p) for p in e.path])
        print(f"Schema error at {path or 'root'}: {e.message}", file=sys.stderr)
    sys.exit(1)
print("latest.json passes schema")
