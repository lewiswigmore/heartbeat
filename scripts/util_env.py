#!/usr/bin/env python3
"""Simple local env loader.

Reads key=value pairs from a local.env file in the repo root and injects them into
os.environ if not already present. Lines starting with '#' and blank lines are ignored.
Values can be optionally quoted with single or double quotes.

This is intended for local dev only; local.env is gitignored.
"""
from __future__ import annotations

import os
from pathlib import Path


def _parse_line(line: str) -> tuple[str, str] | None:
    if not line or line.strip().startswith("#"):
        return None
    if "=" not in line:
        return None
    key, val = line.split("=", 1)
    key = key.strip()
    val = val.strip()
    # Strip surrounding quotes if present
    if (val.startswith("\"") and val.endswith("\"")) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    if not key:
        return None
    return key, val


def load_local_env(filename: str = "local.env", override: bool = False) -> int:
    root = Path(__file__).resolve().parents[1]
    env_path = root / filename
    if not env_path.exists():
        return 0
    count = 0
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_line(raw)
            if not parsed:
                continue
            k, v = parsed
            if not override and k in os.environ:
                continue
            os.environ[k] = v
            count += 1
        return count
    except Exception:
        return 0


__all__ = ["load_local_env"]
