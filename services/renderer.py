import json
import os
import shutil
import subprocess
import time
import uuid
from typing import Optional


def find_output_video(output_dir: str, job_id: str) -> Optional[str]:
    search_root = os.path.join(output_dir, "videos", job_id)
    if not os.path.exists(search_root):
        return None
    for root, _, files in os.walk(search_root):
        for file_name in files:
            if file_name.endswith(".mp4") and not file_name.endswith("_final.mp4"):
                return os.path.join(root, file_name)
    return None


def _manim_cmd() -> list[str]:
    """
    Prefer the manim binary on PATH (Docker/.venv).
    Fall back to `uv run manim` for local dev without activated venv.
    """
    manim_bin = shutil.which("manim")
    if manim_bin:
        return [manim_bin]
    uv_bin = shutil.which("uv")
    if uv_bin:
        return [uv_bin, "run", "manim"]
    return ["manim"]


def _manim_quality_flag(override: Optional[str] = None) -> str:
    q = (override or os.getenv("MANIM_QUALITY") or "medium").strip().lower()
    return {"low": "-ql", "medium": "-qm", "high": "-qh", "4k": "-qk"}.get(q, "-qm")


def _render_timeout_sec() -> float:
    try:
        return max(60.0, float(os.getenv("MANIM_RENDER_TIMEOUT", "600")))
    except ValueError:
        return 600.0


def render_video(
    code: str,
    output_dir: str,
    log=print,
    *,
    quality: Optional[str] = None,
    marks_path: Optional[str] = None,
    scales: Optional[dict] = None,
    measure_only: bool = False,
) -> tuple[Optional[str], Optional[str]]:
    """
    Render `Scene` from `code`. Instrumented code (services.beat_sync) writes beat
    stats to `marks_path` and applies per-beat time `scales`.

    measure_only: run construct() with animations skipped (`-s`), which is fast
    but advances the scene clock exactly like a real render. Returns
    (marks_path, None) on success so callers can read the measured timings.
    """
    log("Step 2/6: Measuring scene timing..." if measure_only else "Step 2/6: Starting Manim rendering...")
    job_id = str(uuid.uuid4())
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{job_id}.py")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code)

    env = os.environ.copy()
    if marks_path:
        env["CLARITY_BEAT_MARKS"] = marks_path
    if scales:
        env["CLARITY_BEAT_SCALES"] = json.dumps(scales)
    timeout = _render_timeout_sec()

    quality_flag = "-ql" if measure_only else _manim_quality_flag(quality)
    cmd = [
        *_manim_cmd(),
        file_path,
        "Scene",
        quality_flag,
        *(["-s"] if measure_only else []),
        "--media_dir",
        output_dir,
        "-o",
        job_id,
    ]
    try:
        log(f"  ▶️ Executing: {' '.join(cmd)}")
        t0 = time.time()
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
        log(
            f"  ✔️ {'Measure pass' if measure_only else 'Rendering'} finished "
            f"in {time.time()-t0:.1f}s."
        )
        if measure_only:
            return marks_path, None
    except subprocess.TimeoutExpired:
        err = (
            f"Render timed out after {timeout:.0f}s (MANIM_RENDER_TIMEOUT). "
            "The scene is too heavy: reduce always_redraw / updaters, sample counts, "
            "and very long animations."
        )
        log(f"  ❌ {err}")
        return None, err
    except FileNotFoundError as e:
        err = f"Manim executable not found: {e}"
        log(f"  ❌ {err}")
        return None, err
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        stdout = (e.stdout or "").strip()
        err = stderr if stderr else stdout if stdout else str(e)
        err_path = os.path.join(output_dir, f"{job_id}_render_error.log")
        with open(err_path, "w", encoding="utf-8") as f:
            f.write(err)
        log(f"  ❌ Rendering failed. Error log saved: {err_path}")
        # Return a truncated error for API clients
        return None, err[-4000:]

    video_path = find_output_video(output_dir, job_id)
    if not video_path:
        return None, "Could not find rendered video file under outputs/videos/"
    log(f"  ✔️ Video will be at {video_path}")
    return video_path, None


def get_media_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
