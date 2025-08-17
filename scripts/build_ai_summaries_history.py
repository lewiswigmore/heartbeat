#!/usr/bin/env python3
"""
Generate AI summaries for historical ideas by updating each ideas/*.jsonl entry
to include an `ai_summary` object, similar to scripts/build_ai_summary.py.

Safe behavior:
- If an entry already has `ai_summary`, it is left unchanged (unless --overwrite is used).
- Prefers Azure OpenAI if configured; falls back to OpenAI; then offline.

Usage:
  python scripts/build_ai_summaries_history.py [--overwrite]
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
try:
    from .util_env import load_local_env  # type: ignore
except Exception:
    try:
        from util_env import load_local_env  # type: ignore
    except Exception:
        load_local_env = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
IDEAS = ROOT / "ideas"
DOCS = ROOT / "docs"


def _strip_code_fences(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```(?:json)?", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"```$", "", s).strip()
    return s


def _azure_chat_complete(prompt: str) -> str | None:
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    api_version_env = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    api_version = "2024-12-01-preview"
    if not (api_key and endpoint and deployment):
        return None
    url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    body = {
        "messages": [
            {"role": "system", "content": (
                "You are an expert product explainer. Be concrete and specific. "
                "Return strict JSON only—no prose or code fences."
            )},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", "api-key": api_key}, method="POST")
        with urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        if os.getenv("AI_DEBUG") == "1":
            log = ROOT / ".green" / "ai_errors.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            try:
                detail = ""
                if isinstance(e, HTTPError):
                    try:
                        detail = e.read().decode("utf-8", errors="ignore")
                    except Exception:
                        detail = ""
                with log.open("a", encoding="utf-8") as f:
                    f.write(f"AZURE_CHAT_ERROR: {e}\n{detail}\n")
            except Exception:
                pass
        return None


def _azure_responses_complete(prompt: str) -> str | None:
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    if not (api_key and endpoint and deployment):
        return None
    if not re.search(r"^2025-", api_version):
        return None
    def _build_body() -> dict:
        system = (
            "You are an expert product explainer. Be concrete and specific. "
            "Return strict JSON only—no prose or code fences."
        )
        return {
            "input": f"{system}\n\n{prompt}",
            "max_output_tokens": 300,
            "text": {"format": "json"},
        }

    def _extract_text(data: dict) -> str | None:
        if not isinstance(data, dict):
            return None
        if isinstance(data.get("output_text"), str):
            return data["output_text"].strip()
        out = data.get("output")
        if isinstance(out, dict):
            content = out.get("content")
            if isinstance(content, list):
                for part in content:
                    txt = part.get("text") or part.get("content")
                    if isinstance(txt, str) and txt.strip():
                        return txt.strip()
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message", {})
            txt = msg.get("content")
            if isinstance(txt, str):
                return txt.strip()
        return None

    url2 = f"{endpoint.rstrip('/')}/openai/responses?api-version={api_version}"
    body2 = _build_body()
    body2["model"] = deployment
    try:
        req2 = Request(url2, data=json.dumps(body2).encode("utf-8"), headers={"Content-Type": "application/json", "api-key": api_key}, method="POST")
        with urlopen(req2, timeout=30) as resp:
            data = json.load(resp)
        text = _extract_text(data)
        if text:
            return text
    except Exception as e:
        if os.getenv("AI_DEBUG") == "1":
            log = ROOT / ".green" / "ai_errors.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            try:
                with log.open("a", encoding="utf-8") as f:
                    f.write(f"AZURE_RESPONSES_SERVICE_ERROR: {e}\n")
            except Exception:
                pass
        pass
    return None


def _openai_chat_complete(prompt: str) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": (
                "You are an expert product explainer. Be concrete and specific. "
                "Return strict JSON only—no prose or code fences."
            )},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 300,
    }
    try:
        req = Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def _article(word: str) -> str:
    return "an" if word[:1].lower() in {"a", "e", "i", "o", "u"} else "a"


def _fallback_summary(concept: str, summary: str, theme: str, tags: list[str]):
    cz = (concept or "idea").strip()
    base = (summary or "").strip()
    if not base or base.lower() == cz.lower():
        art = _article(cz)
        base = f"Build {art} {cz} to demonstrate the core value quickly."
    extras = []
    if theme:
        extras.append(f"It aligns to the {theme} theme")
    if tags:
        extras.append("touching " + ", ".join(tags[:4]))
    extra_txt = (" " + ("; ".join(extras) + ".") ) if extras else ""
    text = (base + extra_txt).strip()

    short_cz = cz.lower()
    examples = [
        f"Ship a tiny {short_cz} prototype end-to-end (README + demo)",
        f"Integrate {short_cz} into an existing repo and add basic metrics",
        f"Instrument {short_cz} and capture before/after results for one workflow",
    ]
    return {"text": text, "examples": examples, "source": "offline"}


def summarize(concept: str, summary: str, theme: str, tags: list[str]) -> dict:
    prompt = f"""Based on this concept: "{concept}" with summary: "{summary}" and theme: "{theme}" and tags: {', '.join(tags[:5])}

Generate a JSON response with exactly this structure:
{{
  "text": "A 1-2 sentence explanation of what this concept does and its value",
  "examples": [
    "Action 1: specific implementable task using '{concept}' terminology", 
    "Action 2: specific implementable task using '{concept}' terminology",
    "Action 3: specific implementable task using '{concept}' terminology"
  ]
}}

Return only valid JSON, no other text."""
    content = _azure_chat_complete(prompt)
    src = "azure" if content else None
    if not content:
        content = _openai_chat_complete(prompt)
        src = "openai" if content else None
    out = None
    if content:
        try:
            raw = _strip_code_fences(content)
            if os.getenv("AI_DEBUG") == "1":
                from pathlib import Path as _P
                _p = ROOT / ".green" / "ai_raw_history.txt"
                _p.parent.mkdir(parents=True, exist_ok=True)
                _p.write_text(f"{raw}", encoding="utf-8")
            out = json.loads(raw)
            if not isinstance(out, dict) or "text" not in out or "examples" not in out:
                out = None
        except Exception:
            out = None
    if not out:
        out = _fallback_summary(concept, summary, theme, tags)
    else:
        out["source"] = src or "openai"
    out["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    return out


def main(argv: list[str]) -> int:
    # Load local env if available
    if callable(load_local_env):  # type: ignore
        load_local_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true", help="Regenerate ai_summary even if present")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between API calls (rate limiting)")
    args = parser.parse_args(argv)

    files = sorted(glob.glob(str(IDEAS / "*.jsonl")))
    total = 0
    updated = 0
    for fp in files:
        p = Path(fp)
        try:
            lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except Exception:
            continue
        changed = False
        out_lines: list[str] = []
        for ln in lines:
            total += 1
            try:
                obj = json.loads(ln)
            except Exception:
                out_lines.append(ln)
                continue
            if not isinstance(obj, dict):
                out_lines.append(ln)
                continue
            if ("ai_summary" in obj) and not args.overwrite:
                out_lines.append(json.dumps(obj, ensure_ascii=False))
                continue
            concept = obj.get("concept") or obj.get("title") or "Idea"
            summary = obj.get("summary") or ""
            theme = obj.get("theme") or ""
            tags = obj.get("tags") or []
            ai = summarize(concept, summary, theme, tags)
            obj["ai_summary"] = ai
            out_lines.append(json.dumps(obj, ensure_ascii=False))
            changed = True
            updated += 1
            if args.sleep:
                time.sleep(args.sleep)
        if changed:
            p.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
            print(f"Updated {p.name}")

    # Update recent.json from jsonl
    try:
        from subprocess import run
        run(["python", str(ROOT / "scripts" / "build_recent.py")], check=False)
    except Exception:
        pass

    print(f"Processed {total} entries, updated {updated}")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
