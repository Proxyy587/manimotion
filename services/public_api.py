"""
What API users see.

Internally jobs run on different rendering engines; publicly a video has a
`style` ("math" for equations and graphs, "graphics" for charts, timelines and
explainers), and failures come back as short, actionable messages instead of
renderer stack traces.
"""

from __future__ import annotations

from typing import Optional

STYLES = ("auto", "math", "graphics")

_STYLE_TO_ENGINE = {"auto": "auto", "math": "manim", "graphics": "remotion"}
_ENGINE_TO_STYLE = {"manim": "math", "remotion": "graphics"}

GENERIC_FAILURE = (
    "We couldn't create this video. Try rephrasing the topic or making it more specific."
)
STORAGE_FAILURE = (
    "The video was created but uploading to your storage failed. "
    "Check your bucket settings in Settings → Storage."
)
_STORAGE_HINTS = ("bucket", "storage", "upload", "s3", "r2", "credential", "access key")


def engine_for_style(style: Optional[str], legacy_engine: Optional[str] = None) -> str:
    """Map a public style (or a legacy engine value) to the internal engine id."""
    for raw in (style, legacy_engine):
        value = (raw or "").strip().lower()
        if value in _STYLE_TO_ENGINE:
            return _STYLE_TO_ENGINE[value]
        if value in _ENGINE_TO_STYLE:
            return value
    return "auto"


def public_style(engine: Optional[str]) -> Optional[str]:
    return _ENGINE_TO_STYLE.get((engine or "").strip().lower())


def public_error(raw: Optional[str]) -> str:
    text = (raw or "").lower()
    if any(hint in text for hint in _STORAGE_HINTS):
        return STORAGE_FAILURE
    return GENERIC_FAILURE
