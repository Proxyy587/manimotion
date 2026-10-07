"""Optional per-attempt model rotation for Manim codegen retries."""

from __future__ import annotations

import os

from services.llm import DEFAULT_MODEL


def get_model_for_manim_attempt(attempt: int, base_model: str | None = None) -> str:
    """
    MANIM_ATTEMPT_MODELS=attempt:model,attempt:model (1-based attempts).
    Example: 1:google/gemini-2.5-flash,2:google/gemini-2.5-flash,3:openai/gpt-4o
    Falls back to base_model or DEFAULT_MODEL.
    """
    fallback = (base_model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    raw = (os.getenv("MANIM_ATTEMPT_MODELS") or "").strip()
    if not raw:
        return fallback
    mapping: dict[int, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        idx_s, model = part.split(":", 1)
        try:
            mapping[int(idx_s.strip())] = model.strip()
        except ValueError:
            continue
    return mapping.get(attempt) or mapping.get(max(mapping)) or fallback
