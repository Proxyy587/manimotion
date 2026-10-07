"""
Beat-locked A/V sync for Manim renders.

1. `instrument_beat_marks` turns every `# BEAT N` comment into a call that records
   the scene clock (`renderer.time`) when that beat starts. Line numbers are kept
   identical so tracebacks still point at the LLM's code.
2. After rendering, `retime_to_beats` maps each video beat segment onto the
   narration's measured beat window (gentle speed change + hold), so every slide
   change lands exactly when the narrator starts talking about it.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from typing import Any, Callable, Optional

MARKS_ENV = "CLARITY_BEAT_MARKS"
_BEAT_COMMENT = re.compile(r"^(?P<indent>[ \t]*)#\s*BEAT\s+(?P<id>[A-Za-z0-9_]+)\b.*$", re.I)
_BLOCK_CONTINUATION = re.compile(r"^\s*(else|elif|except|finally)\b")

_MARK_HELPER = '''

_CLARITY_MARKS = {}


def _clarity_mark(beat_id):
    try:
        import inspect as _inspect
        import json as _json
        import os as _os

        path = _os.environ.get("CLARITY_BEAT_MARKS")
        key = str(beat_id)
        if not path or key in _CLARITY_MARKS:
            return
        frame = _inspect.currentframe().f_back
        for _ in range(8):
            if frame is None:
                return
            for value in list(frame.f_locals.values()):
                renderer = getattr(value, "renderer", None)
                t = getattr(renderer, "time", None)
                if isinstance(t, (int, float)):
                    _CLARITY_MARKS[key] = float(t)
                    with open(path, "w") as fh:
                        _json.dump(_CLARITY_MARKS, fh)
                    return
            frame = frame.f_back
    except Exception:
        pass
'''


def _next_code_line(lines: list[str], start: int) -> Optional[str]:
    for line in lines[start:]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return line
    return None


def instrument_beat_marks(code: str) -> tuple[str, int]:
    """
    Replace each `# BEAT N ...` comment line with `_clarity_mark("N")  # BEAT N ...`
    (same line, so line numbers are unchanged) and append the helper at the end.
    Returns (code, number_of_marks). Returns the original code if anything looks unsafe.
    """
    lines = code.splitlines()
    count = 0
    seen: set[str] = set()
    for i, line in enumerate(lines):
        m = _BEAT_COMMENT.match(line)
        if not m:
            continue
        beat_id = m.group("id")
        if beat_id in seen:
            continue
        nxt = _next_code_line(lines, i + 1)
        if nxt is None or _BLOCK_CONTINUATION.match(nxt):
            continue
        indent = nxt[: len(nxt) - len(nxt.lstrip())]
        if not indent:
            continue
        lines[i] = f"{indent}_clarity_mark({json.dumps(beat_id)})  {line.strip()}"
        seen.add(beat_id)
        count += 1

    if count == 0:
        return code, 0
    instrumented = "\n".join(lines) + "\n" + _MARK_HELPER
    try:
        ast.parse(instrumented)
    except SyntaxError:
        return code, 0
    return instrumented, count


def read_beat_marks(path: str) -> dict[str, float]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): float(v) for k, v in data.items()}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def plan_segments(
    video_marks: dict[str, float],
    video_duration: float,
    beat_map: dict[str, dict[str, Any]],
    audio_duration: float,
    *,
    min_gap: float = 0.12,
) -> list[tuple[float, float, float, float]]:
    """
    Pair video beat starts with audio beat starts.
    Returns segments as (video_start, video_end, audio_start, audio_end).
    Beats missing on either side are skipped; out-of-order pairs are dropped.
    """
    pairs: list[tuple[float, float]] = []
    for bid, v in video_marks.items():
        info = beat_map.get(str(bid))
        if info is None or info.get("start_s") is None:
            continue
        pairs.append((float(v), float(info["start_s"])))
    pairs.sort()

    points: list[tuple[float, float]] = [(0.0, 0.0)]
    for v, a in pairs:
        last_v, last_a = points[-1]
        if v >= video_duration - min_gap or a >= audio_duration - min_gap:
            continue
        if v > last_v + min_gap and a > last_a + min_gap:
            points.append((v, a))
    end = (float(video_duration), float(audio_duration))
    if len(points) > 1 and (
        end[0] <= points[-1][0] + min_gap or end[1] <= points[-1][1] + min_gap
    ):
        points.pop()
    points.append(end)

    return [
        (points[i][0], points[i + 1][0], points[i][1], points[i + 1][1])
        for i in range(len(points) - 1)
    ]


def compute_retime(
    segments: list[tuple[float, float, float, float]],
    *,
    max_slowdown: float,
    max_speedup: float,
) -> list[dict[str, float]]:
    """
    For each segment decide a speed factor (>1 = slower) and a hold (frozen last
    frame) so the cumulative output tracks the audio beat boundaries. Overflow
    from a segment that can't be compressed enough is carried into the next one.
    """
    plan: list[dict[str, float]] = []
    debt = 0.0
    for v0, v1, a0, a1 in segments:
        dv = max(1e-3, v1 - v0)
        target = max(0.0, (a1 - a0) - debt)
        factor = min(max_slowdown, max(1.0 / max_speedup, target / dv)) if target > 0 else 1.0 / max_speedup
        out_len = dv * factor
        hold = max(0.0, target - out_len)
        debt = max(0.0, out_len - target)
        plan.append(
            {"start": v0, "end": v1, "factor": factor, "hold": hold, "out": out_len + hold}
        )
    return plan


def _needs_retime(plan: list[dict[str, float]]) -> bool:
    return any(abs(p["factor"] - 1.0) > 0.02 or p["hold"] > 0.08 for p in plan)


def _video_fps(path: str) -> float:
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", path,
            ],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout.strip()
        num, _, den = out.partition("/")
        fps = float(num) / float(den or 1)
        return fps if 1 <= fps <= 120 else 30.0
    except (subprocess.SubprocessError, ValueError, ZeroDivisionError):
        return 30.0


def build_filter_graph(plan: list[dict[str, float]], fps: float) -> str:
    parts: list[str] = []
    labels: list[str] = []
    for i, seg in enumerate(plan):
        chain = (
            f"[0:v]trim=start={seg['start']:.4f}:end={seg['end']:.4f},"
            f"setpts=PTS-STARTPTS,setpts={seg['factor']:.5f}*PTS,fps={fps:g}"
        )
        if seg["hold"] > 0.02:
            chain += f",tpad=stop_mode=clone:stop_duration={seg['hold']:.4f}"
        chain += f",trim=duration={seg['out']:.4f},setpts=PTS-STARTPTS[v{i}]"
        parts.append(chain)
        labels.append(f"[v{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(plan)}:v=1:a=0[out]")
    return ";".join(parts)


def retime_to_beats(
    video_path: str,
    *,
    video_marks: dict[str, float],
    video_duration: float,
    beat_map: dict[str, dict[str, Any]],
    audio_duration: float,
    log: Callable[[str], None] = print,
) -> str:
    """
    Return a path to a beat-locked copy of `video_path` (or the original path if no
    change is needed / ffmpeg fails).
    """
    if video_duration <= 0 or audio_duration <= 0:
        return video_path

    segments = plan_segments(video_marks, video_duration, beat_map, audio_duration)
    plan = compute_retime(
        segments,
        max_slowdown=_env_float("BEAT_SYNC_MAX_SLOWDOWN", 1.3),
        max_speedup=_env_float("BEAT_SYNC_MAX_SPEEDUP", 1.6),
    )
    if not _needs_retime(plan):
        log("  ✔️ Beat sync: video already matches narration timing")
        return video_path

    fps = _video_fps(video_path)
    out_path = os.path.splitext(video_path)[0] + "_synced.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-filter_complex", build_filter_graph(plan, fps),
        "-map", "[out]", "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        out_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
    except (subprocess.SubprocessError, OSError) as e:
        stderr = getattr(e, "stderr", "") or str(e)
        log(f"  ⚠️ Beat sync failed, using unsynced video: {stderr[-400:]}")
        return video_path

    held = sum(p["hold"] for p in plan)
    log(
        f"  ✔️ Beat sync: {len(plan)} segments locked to narration "
        f"({len(video_marks)} beat marks, {held:.1f}s of holds spread across beats)"
    )
    return out_path
