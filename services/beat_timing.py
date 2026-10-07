"""Map TTS word timestamps onto beat-sheet markers for audio-driven sync."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

# [BEAT:1] or [BEAT:hook] — id is digits or lowercase_underscore
BEAT_MARKER_RE = re.compile(r"\[BEAT:([a-zA-Z0-9_]+)\]\s*", re.IGNORECASE)


def strip_and_locate_beats(script: str) -> tuple[str, dict[str, int]]:
    """
    Remove [BEAT:id] markers and record each beat's start char index in clean text.
    Later markers win if duplicated.
    """
    beat_char_positions: dict[str, int] = {}
    clean_parts: list[str] = []
    last = 0
    for match in BEAT_MARKER_RE.finditer(script):
        clean_parts.append(script[last : match.start()])
        beat_id = match.group(1).lower()
        # Position where spoken text for this beat begins
        beat_char_positions[beat_id] = sum(len(p) for p in clean_parts)
        last = match.end()
    clean_parts.append(script[last:])
    clean = "".join(clean_parts)
    leading = len(clean) - len(clean.lstrip())
    clean = clean.strip()
    if leading:
        beat_char_positions = {
            k: max(0, v - leading) for k, v in beat_char_positions.items()
        }
    return clean, beat_char_positions


def marked_script_from_plan(plan: dict[str, Any]) -> str:
    """Fallback marked script when the LLM omits [BEAT:] markers."""
    parts: list[str] = []
    for beat in plan.get("beats") or []:
        bid = beat.get("id", len(parts) + 1)
        text = (beat.get("narration") or "").strip()
        if not text:
            continue
        parts.append(f"[BEAT:{bid}] {text}")
    return " ".join(parts).strip()


def ensure_beat_markers(script: str, plan: dict[str, Any]) -> str:
    """Keep LLM script if it has markers; otherwise rebuild from the beat sheet."""
    if BEAT_MARKER_RE.search(script or ""):
        return script.strip()
    return marked_script_from_plan(plan)


def find_timestamp_at_char(word_timestamps: list[dict[str, Any]], char_pos: int) -> float:
    """Timestamp (seconds) of the word covering char_pos in the clean script."""
    if not word_timestamps:
        return 0.0
    if char_pos <= 0:
        return float(word_timestamps[0].get("start_s", 0.0))

    # First word that starts at/after the marker position (markers sit right before
    # the beat's first word, so this is that word).
    for word in word_timestamps:
        if int(word.get("char_offset", 0)) >= char_pos:
            return float(word.get("start_s", 0.0))
    return float(word_timestamps[-1].get("start_s", 0.0))


def build_spoken_cues(
    word_timestamps: list[dict[str, Any]],
    start_s: float,
    end_s: float,
    max_words: int = 7,
) -> list[dict[str, Any]]:
    """
    Split a beat's words into short phrases with offsets relative to the beat start,
    breaking at punctuation pauses or every `max_words` words.
    """
    words = [
        w
        for w in word_timestamps
        if start_s - 0.05 <= float(w.get("start_s", 0.0)) < end_s - 0.05
    ]
    groups: list[list[dict[str, Any]]] = []
    chunk: list[dict[str, Any]] = []
    for w in words:
        chunk.append(w)
        if w.get("pause_after") or len(chunk) >= max_words:
            groups.append(chunk)
            chunk = []
    if chunk:
        groups.append(chunk)
    return [
        {
            "t": round(max(0.0, float(g[0]["start_s"]) - start_s), 1),
            "text": " ".join(str(w.get("word", "")) for w in g),
        }
        for g in groups
    ]


def build_beat_map(
    word_timestamps: list[dict[str, Any]],
    beat_char_positions: dict[str, int],
    audio_duration: float,
    beat_ids: list[Any] | None = None,
) -> dict[str, dict[str, float]]:
    """
    beat_map[id] = {start_s, end_s, duration_sec}
    Ends at the next beat's start (or audio_duration for the last).
    """
    if not beat_char_positions and beat_ids:
        # Proportional fallback — equal share of audio
        n = max(1, len(beat_ids))
        slice_len = audio_duration / n
        out: dict[str, dict[str, float]] = {}
        for i, bid in enumerate(beat_ids):
            start = i * slice_len
            end = audio_duration if i == n - 1 else (i + 1) * slice_len
            out[str(bid)] = {
                "start_s": round(start, 3),
                "end_s": round(end, 3),
                "duration_sec": round(max(0.5, end - start), 3),
            }
        return out

    # Sort beats by spoken position
    ordered = sorted(beat_char_positions.items(), key=lambda x: x[1])
    starts: list[tuple[str, float]] = []
    for beat_id, char_pos in ordered:
        starts.append((str(beat_id), find_timestamp_at_char(word_timestamps, char_pos)))

    # Force first beat to 0 if very close
    if starts and starts[0][1] < 0.35:
        starts[0] = (starts[0][0], 0.0)

    beat_map: dict[str, dict[str, float]] = {}
    for i, (beat_id, start_s) in enumerate(starts):
        end_s = starts[i + 1][1] if i + 1 < len(starts) else float(audio_duration)
        if end_s <= start_s:
            end_s = start_s + 0.5
        beat_map[beat_id] = {
            "start_s": round(start_s, 3),
            "end_s": round(end_s, 3),
            "duration_sec": round(max(0.5, end_s - start_s), 3),
            "cues": build_spoken_cues(word_timestamps, start_s, end_s),
        }
    return beat_map


def apply_measured_timings_to_plan(
    plan: dict[str, Any],
    beat_map: dict[str, dict[str, float]],
    audio_duration: float,
) -> dict[str, Any]:
    """
    Return a copy of the beat sheet with duration_sec / start_s / end_s from TTS.
    Voice length is sacred — planner estimates are replaced by measured times.
    """
    timed = deepcopy(plan)
    beats = timed.get("beats") or []
    for beat in beats:
        key = str(beat.get("id", "")).lower()
        # Also try numeric string
        info = beat_map.get(key) or beat_map.get(str(beat.get("id")))
        if not info:
            # try int id as string of int
            try:
                info = beat_map.get(str(int(beat.get("id"))))
            except (TypeError, ValueError):
                info = None
        if not info:
            continue
        beat["start_s"] = info["start_s"]
        beat["end_s"] = info["end_s"]
        beat["duration_sec"] = info["duration_sec"]
        beat["timing_source"] = "tts"
        if info.get("cues"):
            beat["cues"] = info["cues"]

    measured_sum = sum(float(b.get("duration_sec", 0)) for b in beats)
    timed["target_duration_sec"] = int(
        round(audio_duration if audio_duration > 0 else measured_sum)
    )
    timed["audio_duration_sec"] = round(float(audio_duration), 3)
    timed["timing_source"] = "tts"
    return timed


def save_beat_debug(
    output_dir: str,
    word_timestamps: list[dict[str, Any]],
    beat_map: dict[str, dict[str, float]],
) -> None:
    import os

    words_path = os.path.join(output_dir, "words.json")
    map_path = os.path.join(output_dir, "beat_map.json")
    with open(words_path, "w", encoding="utf-8") as f:
        json.dump(word_timestamps, f, indent=2)
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(beat_map, f, indent=2)
