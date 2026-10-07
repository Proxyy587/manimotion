"""Persist first-try Manim successes for few-shot injection (no fine-tuning)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_PATH = _REPO_ROOT / "data" / "manim_success_examples.jsonl"


def _store_path() -> Path:
    raw = (os.getenv("MANIM_EXAMPLES_PATH") or "").strip()
    return Path(raw) if raw else _DEFAULT_PATH


def _topic_category(topic: str) -> str:
    t = topic.lower()
    if re.search(r"\b(calculus|derivative|integral|limit|taylor)\b", t):
        return "calculus"
    if re.search(r"\b(physics|force|velocity|energy|wave)\b", t):
        return "physics"
    if re.search(r"\b(linear|matrix|vector|algebra|equation)\b", t):
        return "algebra"
    return "general"


def save_successful_example(
    topic: str,
    code: str,
    *,
    attempt: int = 1,
    engine: str = "manim",
) -> None:
    if attempt != 1 or engine != "manim":
        return
    if (os.getenv("MANIM_SAVE_EXAMPLES") or "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "topic": topic[:500],
        "topic_category": _topic_category(topic),
        "code": code[:12000],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def get_relevant_examples(topic: str, *, limit: int = 2) -> str:
    path = _store_path()
    if not path.is_file():
        return ""
    category = _topic_category(topic)
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return ""

    same = [r for r in rows if r.get("topic_category") == category]
    pool = same if same else rows
    pool = list(reversed(pool))[:limit]
    if not pool:
        return ""
    parts = ["PREVIOUSLY SUCCESSFUL CODE FOR SIMILAR TOPICS (patterns only):"]
    for r in pool:
        parts.append(f"# Topic: {r.get('topic', '')}\n{r.get('code', '')[:4000]}")
    return "\n---\n".join(parts)
