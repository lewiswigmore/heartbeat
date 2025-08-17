#!/usr/bin/env python3
"""
Build an AI-generated summary for    body = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that creates concise product summaries."},
            {"role": "user", "content": prompt},
        ],
        "max_completion_tokens": 200,
    } idea and embed it into docs/latest.json.

Prefers Azure OpenAI if configured via env:
  AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_VERSION

Falls back to OpenAI if OPENAI_API_KEY is set, else to a simple offline composition.

Outputs:
  - Updates docs/latest.json by adding an object field `ai_summary` with:
      {
        "text": str,           # short summary (<= ~40 words)
        "examples": [str, str, str],
        "source": "azure"|"openai"|"offline",
        "generated_at": ISO8601 UTC timestamp
      }
  - Also writes docs/ai_summary.json with the same object (optional convenience file)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# Auto-load local.env for local runs (no-op in CI if not present)
try:
    from .util_env import load_local_env  # type: ignore
except Exception:
    try:
        from util_env import load_local_env  # type: ignore
    except Exception:
        load_local_env = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
LATEST = DOCS / "latest.json"
IDEAS = ROOT / "ideas"


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
    # For gpt-5, prefer the 2024-12-01-preview chat API version
    api_version = "2024-12-01-preview"
    if not (api_key and endpoint and deployment):
        return None
    url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    body = {
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", "api-key": api_key}, method="POST")
        with urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        
        # Debug logging
        if os.getenv("AI_DEBUG") == "1":
            print(f"Azure response data: {json.dumps(data, indent=2)}")
        
        content = data["choices"][0]["message"]["content"]
        if content is None:
            if os.getenv("AI_DEBUG") == "1":
                print("Warning: Azure returned None content")
            return ""
        return content.strip()
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
    """Call Azure OpenAI Responses API if configured (2025-04-01-preview or similar).

    Uses the deployment-based endpoint for better compatibility:
      POST {endpoint}/openai/deployments/{deployment}/responses?api-version=...
    """
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    if not (api_key and endpoint and deployment):
        return None
    # Heuristic: only try responses API for 2025+ versions which support it
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

    # Service-level endpoint (requires model = deployment name)
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
                detail = ""
                if isinstance(e, HTTPError):
                    try:
                        detail = e.read().decode("utf-8", errors="ignore")
                    except Exception:
                        detail = ""
                with log.open("a", encoding="utf-8") as f:
                    f.write(f"AZURE_RESPONSES_SERVICE_ERROR: {e}\n{detail}\n")
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
    # Compose a slightly more explanatory offline summary when no AI is available.
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

    # Produce varied, concrete starter actions without being overly generic.
    short_cz = cz.lower()
    examples = [
        f"Ship a tiny {short_cz} prototype end-to-end (README + demo)",
        f"Integrate {short_cz} into an existing repo and add basic metrics",
        f"Instrument {short_cz} and capture before/after results for one workflow",
    ]
    return {"text": text, "examples": examples, "source": "offline"}


def main() -> int:
    # Load local env if available
    if callable(load_local_env):  # type: ignore
        load_local_env()
    if not LATEST.exists():
        print("docs/latest.json not found; skipping AI summary.")
        return 0
    j = json.loads(LATEST.read_text(encoding="utf-8"))
    concept = j.get("concept") or j.get("title") or "Idea"
    summary = j.get("summary") or ""
    theme = j.get("theme") or ""
    tags_list = j.get("tags") or []
    tags = ", ".join(tags_list[:5])

    prompt = f"""Based on this concept: "{concept}" with summary: "{summary}" and theme: "{theme}" and tags: {tags}

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

    # Use Azure Chat Completions for gpt-5 (skip Responses API due to compatibility issues)
    content = _azure_chat_complete(prompt)
    src = "azure" if content else None
    if not content:
        content = _openai_chat_complete(prompt)
        src = "openai" if content else None

    out = None
    if content:
        try:
            raw = _strip_code_fences(content)
            # Optional debug dump
            if os.getenv("AI_DEBUG") == "1":
                dbg = ROOT / ".green" / "ai_raw.txt"
                dbg.parent.mkdir(parents=True, exist_ok=True)
                dbg.write_text(f"source={src}\n\n{raw}", encoding="utf-8")
            out = json.loads(raw)
            if not isinstance(out, dict) or "text" not in out or "examples" not in out:
                out = None
        except Exception:
            out = None

    if not out:
        out = _fallback_summary(concept, summary, theme, tags_list)
    else:
        out["source"] = src or "openai"

    out["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    # Merge into latest.json
    j["ai_summary"] = out
    DOCS.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")

    # Also emit a standalone file
    (DOCS / "ai_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # Persist ai_summary back into ideas/YYYY-MM.jsonl for the matching date, and update .green/todays_idea.json
    try:
        date = j.get("date")
        if date and isinstance(date, str) and len(date) >= 7:
            month_jsonl = IDEAS / f"{date[:7]}.jsonl"
            if month_jsonl.exists():
                lines = [ln for ln in month_jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
                changed = False
                out_lines = []
                for ln in lines:
                    try:
                        obj = json.loads(ln)
                    except Exception:
                        out_lines.append(ln)
                        continue
                    if isinstance(obj, dict) and obj.get("date") == date:
                        if obj.get("ai_summary") != out:
                            obj["ai_summary"] = out
                            changed = True
                        out_lines.append(json.dumps(obj, ensure_ascii=False))
                    else:
                        out_lines.append(json.dumps(obj, ensure_ascii=False) if isinstance(obj, dict) else ln)
                if changed:
                    month_jsonl.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

            # Update .green/todays_idea.json if present
            green_json = ROOT / ".green" / "todays_idea.json"
            if green_json.exists():
                try:
                    g = json.loads(green_json.read_text(encoding="utf-8"))
                    g["ai_summary"] = out
                    green_json.write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
    except Exception:
        pass

    print("Updated docs/latest.json with ai_summary and wrote docs/ai_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
