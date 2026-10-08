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

SCALES_ENV = "CLARITY_BEAT_SCALES"

# Appended to the scene file. Patches manim's Scene.play/wait to:
#  - record the scene clock when each beat's first animation starts
#  - record per-beat wait time (static holds)
#  - apply per-beat time scales (CLARITY_BEAT_SCALES) so motion fills narration
# Stats are dumped as JSON to CLARITY_BEAT_MARKS at process exit.
_MARK_HELPER = '''

import atexit as _clarity_atexit
import json as _clarity_json
import os as _clarity_os

import manim as _clarity_manim

_CLARITY = {
    "beat": "_pre",
    "pending": None,
    "in_wait": False,
    "marks": {},
    "waits": {},
    "wait_list": {},
    "end": 0.0,
    "scales": {},
}
try:
    _CLARITY["scales"] = _clarity_json.loads(_clarity_os.environ.get("CLARITY_BEAT_SCALES") or "{}")
except Exception:
    pass


def _clarity_mark(beat_id):
    key = str(beat_id)
    if key not in _CLARITY["marks"]:
        _CLARITY["beat"] = key
        _CLARITY["pending"] = key


def _clarity_scale(kind):
    try:
        return float(_CLARITY["scales"].get(_CLARITY["beat"], {}).get(kind, 1.0))
    except Exception:
        return 1.0


def _clarity_base_run_time(args, kwargs):
    rt = kwargs.get("run_time")
    if isinstance(rt, (int, float)):
        return float(rt)
    base = 0.0
    for a in args:
        attrs = getattr(a, "__dict__", {})
        if "anim_args" in attrs:  # mob.animate builder
            val = attrs["anim_args"].get("run_time")
        else:
            val = getattr(a, "run_time", None)
        base = max(base, float(val) if isinstance(val, (int, float)) else 1.0)
    return base or 1.0


_clarity_orig_play = _clarity_manim.Scene.play
_clarity_orig_wait = _clarity_manim.Scene.wait


def _clarity_play(self, *args, **kwargs):
    try:
        if _CLARITY["pending"] is not None:
            _CLARITY["marks"][_CLARITY["pending"]] = float(self.renderer.time)
            _CLARITY["pending"] = None
        if not _CLARITY["in_wait"] and args:
            s = _clarity_scale("play")
            if abs(s - 1.0) > 1e-3:
                kwargs["run_time"] = max(1 / 30, _clarity_base_run_time(args, kwargs) * s)
    except Exception:
        pass
    result = _clarity_orig_play(self, *args, **kwargs)
    try:
        _CLARITY["end"] = float(self.renderer.time)
    except Exception:
        pass
    return result


def _clarity_wait(self, duration=1.0, *args, **kwargs):
    try:
        d = float(duration) * _clarity_scale("wait")
        d = max(1 / 30, d)
        beat = _CLARITY["beat"]
        _CLARITY["waits"][beat] = _CLARITY["waits"].get(beat, 0.0) + d
        _CLARITY["wait_list"].setdefault(beat, []).append(round(d, 3))
    except Exception:
        d = duration
    _CLARITY["in_wait"] = True
    try:
        return _clarity_orig_wait(self, d, *args, **kwargs)
    finally:
        _CLARITY["in_wait"] = False


def _clarity_dump():
    path = _clarity_os.environ.get("CLARITY_BEAT_MARKS")
    if not path:
        return
    try:
        with open(path, "w") as fh:
            _clarity_json.dump(
                {
                    "marks": _CLARITY["marks"],
                    "waits": _CLARITY["waits"],
                    "wait_list": _CLARITY["wait_list"],
                    "end": _CLARITY["end"],
                },
                fh,
            )
    except Exception:
        pass


_clarity_manim.Scene.play = _clarity_play
_clarity_manim.Scene.wait = _clarity_wait
_clarity_atexit.register(_clarity_dump)
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
    (same line, so line numbers are unchanged) and append the timing harness.
    Returns (code, number_of_marks). With no beat comments the harness is still
    appended (the whole scene is one "_pre" beat). Returns the original code with
    0 marks if the result would not parse.
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

    if "from manim import" not in code:
        return code, 0
    instrumented = "\n".join(lines) + "\n" + _MARK_HELPER
    try:
        ast.parse(instrumented)
    except SyntaxError:
        return code, 0
    return instrumented, count


def read_beat_stats(path: str) -> dict[str, Any]:
    """{"marks": {beat: t}, "waits": {beat: seconds}, "end": t} written by the harness."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {
            "marks": {str(k): float(v) for k, v in (data.get("marks") or {}).items()},
            "waits": {str(k): float(v) for k, v in (data.get("waits") or {}).items()},
            "wait_list": {
                str(k): [float(x) for x in v] for k, v in (data.get("wait_list") or {}).items()
            },
            "end": float(data.get("end") or 0.0),
        }
    except (OSError, ValueError, TypeError, AttributeError):
        return {"marks": {}, "waits": {}, "wait_list": {}, "end": 0.0}


def read_beat_marks(path: str) -> dict[str, float]:
    return read_beat_stats(path)["marks"]


def beat_windows(
    stats: dict[str, Any],
    beat_map: dict[str, dict[str, Any]],
    audio_duration: float,
    *,
    min_gap: float = 0.12,
) -> list[dict[str, Any]]:
    """
    Pair each measured video beat with its narration window, in video order.
    Returns [{id, v0, v1, a0, a1, wait}] covering the whole video and audio.
    Content before the first mark is "_pre".
    """
    end = float(stats.get("end") or 0.0)
    waits = stats.get("waits") or {}
    pairs: list[tuple[float, float, str]] = []
    for bid, v in (stats.get("marks") or {}).items():
        info = beat_map.get(str(bid))
        if info is None or info.get("start_s") is None:
            continue
        pairs.append((float(v), float(info["start_s"]), str(bid)))
    pairs.sort()

    # Each point: [video_start, audio_start, member beat ids]. Beats that can't
    # form their own window (too close / out of order) join the previous one.
    points: list[list[Any]] = [[0.0, 0.0, ["_pre"]]]
    for v, a, bid in pairs:
        last_v, last_a, members = points[-1]
        ok_bounds = v < end - min_gap and a < audio_duration - min_gap
        if ok_bounds and v > last_v + min_gap and a > last_a + min_gap:
            points.append([v, a, [bid]])
        else:
            members.append(bid)

    windows = []
    for i, (v0, a0, members) in enumerate(points):
        v1, a1 = (points[i + 1][0], points[i + 1][1]) if i + 1 < len(points) else (end, audio_duration)
        windows.append(
            {
                "id": members[-1] if members[0] == "_pre" and len(members) > 1 else members[0],
                "members": members,
                "v0": v0,
                "v1": v1,
                "a0": a0,
                "a1": a1,
                "wait": float(sum(waits.get(m, 0.0) for m in members)),
                "wait_list": [
                    float(x)
                    for m in members
                    for x in (stats.get("wait_list") or {}).get(m, [])
                ],
            }
        )
    return windows


def compute_beat_scales(
    windows: list[dict[str, Any]],
    *,
    max_play_stretch: float = 1.8,
    max_wait_stretch: float = 3.0,
    min_play: float = 0.7,
    min_wait: float = 0.3,
    dead_air_after: float = 2.5,
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    """
    Per beat, decide how much to stretch animations ("play") and holds ("wait")
    so the beat fills its narration window. Motion is stretched first so the
    picture keeps moving; holds only absorb what motion can't.

    "Dead air" = the part of any single hold beyond `dead_air_after` seconds,
    plus narration time the beat doesn't cover at all. Short pauses between
    reveals are normal teaching rhythm and are not counted.
    Returns (scales, report) where report["static_ratio"] is dead air / narration.
    """
    scales: dict[str, dict[str, float]] = {}
    beats_report = []
    total_target = 0.0
    total_static = 0.0
    for w in windows:
        video_len = max(0.0, w["v1"] - w["v0"])
        target = max(0.0, w["a1"] - w["a0"])
        wait = min(w["wait"], video_len)
        motion = max(0.0, video_len - wait)
        sp, sw = 1.0, 1.0
        if target > video_len + 0.05:
            if motion > 0.05:
                sp = max(1.0, min(max_play_stretch, (target - wait) / motion))
            rest = target - motion * sp
            if wait > 0.05 and rest > wait:
                sw = min(max_wait_stretch, rest / wait)
        elif target < video_len - 0.05:
            excess = video_len - target
            if wait > 0.05:
                sw = max(min_wait, (wait - excess) / wait)
                excess -= wait * (1 - sw)
            if excess > 0.05 and motion > 0.05:
                sp = max(min_play, (motion - excess) / motion)
        if abs(sp - 1) > 1e-3 or abs(sw - 1) > 1e-3:
            for member in w.get("members") or [w["id"]]:
                scales[member] = {"play": round(sp, 4), "wait": round(sw, 4)}
        holds = w.get("wait_list") or ([wait] if wait > 0 else [])
        long_holds = sum(max(0.0, h * sw - dead_air_after) for h in holds)
        uncovered = max(0.0, target - (motion * sp + wait * sw))
        static = long_holds + uncovered
        total_target += target
        total_static += static
        beats_report.append(
            {
                "id": w["id"],
                "motion": round(motion, 2),
                "wait": round(wait, 2),
                "narration": round(target, 2),
                "static": round(static, 2),
            }
        )
    ratio = (total_static / total_target) if total_target > 0 else 0.0
    return scales, {"static_ratio": round(ratio, 3), "beats": beats_report}


def format_pacing_feedback(report: dict[str, Any], visual_plan: dict[str, Any] | None = None) -> str:
    """Retry instructions when the scene renders but the picture goes static."""
    cues_by_id = {
        str(b.get("id")): b.get("cues") or [] for b in (visual_plan or {}).get("beats", [])
    }
    lines = [
        "PACING PROBLEM (the code renders, but the picture freezes while the narrator keeps talking).",
        f"{round(report['static_ratio'] * 100)}% of the narration is frozen screen "
        "(holds longer than 2.5s, or nothing left to show).",
        "Measured per beat (seconds of motion / seconds of narration):",
    ]
    for b in report["beats"]:
        if b["id"] == "_pre" and b["narration"] < 0.5:
            continue
        flag = "  ← too static" if b["static"] > max(2.0, 0.3 * b["narration"]) else ""
        lines.append(
            f"  BEAT {b['id']}: {b['motion']}s motion + {b['wait']}s waits for {b['narration']}s narration{flag}"
        )
        if flag and cues_by_id.get(b["id"]):
            for cue in cues_by_id[b["id"]][:6]:
                lines.append(f"      +{float(cue.get('t', 0)):.1f}s \"{cue.get('text', '')}\"")
    lines += [
        "",
        "FIX: keep the working structure, but add more on-screen action to the flagged beats:",
        "- one reveal per spoken cue (Write / FadeIn / Create / GrowArrow) at the cue time",
        "- emphasis while explaining: Indicate, Circumscribe, SurroundingRectangle, color change",
        "- continuous motion for long explanations: move a Dot along a curve, ValueTracker sweep,",
        "  transform one equation into the next, build a diagram piece by piece",
        "- no self.wait() longer than 2.5s; every beat starts with its `# BEAT N` comment",
    ]
    return "\n".join(lines)


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
