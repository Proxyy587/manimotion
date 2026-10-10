"""
Step 6–8: per-slide audio (lead-in + sentences + pauses + end hold + lead-out), frame-exact
video segments (+ burned captions), concat, final mux and the A/V assertion.

Every slide is quantized to whole frames and its audio is padded to exactly that length,
so the full narration track and the concatenated video have identical durations by
construction. Audio is never time-stretched; video is only padded by cloning its last frame.
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from typing import Any, Callable

FPS = 30
SAMPLE_RATE = 48000
LEAD_IN, END_HOLD, LEAD_OUT = 0.5, 1.2, 0.4  # must match slide_kit.SlideScene
MAX_AV_DIFF = 0.12
BURN_CAPTIONS = os.getenv("CAPTIONS_BURN", "1").strip().lower() not in {"0", "false", "no"}
CAPTION_FONT = os.getenv("SLIDE_FONT", "DejaVu Sans")
CAPTION_LINE = 46


class AVMismatchError(RuntimeError):
    pass


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-6:])
        raise RuntimeError(f"ffmpeg failed: {tail}")


def slide_length(slide: dict[str, Any]) -> tuple[float, int]:
    """(exact seconds, frame count) for a slide built from its beats."""
    t = LEAD_IN + sum(b["dur"] for b in slide["beats"]) + END_HOLD + LEAD_OUT
    return t, max(1, round(t * FPS))


def build_slide_audio(slide: dict[str, Any], out_path: str) -> float:
    """Concatenate lead-in, each sentence padded to its beat, and the tail; returns seconds."""
    t, frames = slide_length(slide)
    total = frames / FPS
    tail = END_HOLD + LEAD_OUT + (total - t)
    fmt = f"aresample={SAMPLE_RATE},aformat=sample_fmts=s16:channel_layouts=stereo"
    cmd = ["ffmpeg", "-y", "-v", "error"]
    parts = []
    for i, beat in enumerate(slide["beats"]):
        cmd += ["-i", beat["audio"]]
        parts.append(f"[{i}:a]{fmt},apad=whole_dur={beat['dur']:.4f},atrim=duration={beat['dur']:.4f}[b{i}]")
    n = len(slide["beats"])
    silence = f"anullsrc=r={SAMPLE_RATE}:cl=stereo,{fmt}"
    parts.append(f"{silence},atrim=duration={LEAD_IN:.4f}[lead]")
    parts.append(f"{silence},atrim=duration={max(tail, 0.001):.4f}[tail]")
    chain = "[lead]" + "".join(f"[b{i}]" for i in range(n)) + "[tail]"
    parts.append(f"{chain}concat=n={n + 2}:v=0:a=1[out]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-c:a", "pcm_s16le", out_path]
    _run(cmd)
    return total


def _caption_chunks(text: str) -> list[str]:
    """Split a sentence into ≤ 2-line caption chunks."""
    lines = textwrap.wrap(text, CAPTION_LINE)
    return ["\n".join(lines[i:i + 2]) for i in range(0, len(lines), 2)] or [text]


def _ts(sec: float, sep: str) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def caption_cues(slide: dict[str, Any], offset: float = 0.0) -> list[tuple[float, float, str]]:
    """One cue per beat (split into readable chunks), timed to the spoken sentence."""
    cues = []
    t = offset + LEAD_IN
    for beat in slide["beats"]:
        chunks = _caption_chunks(beat["text"])
        total_chars = sum(len(c) for c in chunks) or 1
        start = t
        for chunk in chunks:
            span = beat["audio_dur"] * len(chunk) / total_chars
            cues.append((start, start + span, chunk))
            start += span
        t += beat["dur"]
    return cues


def write_srt(cues: list[tuple[float, float, str]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for i, (a, b, text) in enumerate(cues, start=1):
            f.write(f"{i}\n{_ts(a, ',')} --> {_ts(b, ',')}\n{text}\n\n")


def write_vtt(cues: list[tuple[float, float, str]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for a, b, text in cues:
            f.write(f"{_ts(a, '.')} --> {_ts(b, '.')}\n{text}\n\n")


_subtitles_ok: bool | None = None


def _can_burn_captions() -> bool:
    """ffmpeg builds without libass have no `subtitles` filter."""
    global _subtitles_ok
    if _subtitles_ok is None:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        _subtitles_ok = any(line.split()[1:2] == ["subtitles"] for line in out.splitlines())
    return _subtitles_ok


def _subtitle_filter(srt_path: str) -> str:
    escaped = srt_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    style = (
        f"FontName={CAPTION_FONT},FontSize=13,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=1,Shadow=0,Alignment=2,MarginV=6"
    )
    return f"subtitles='{escaped}':force_style='{style}'"


def _frame_exact(
    video_path: str, frames: int, out: str, cues: list[tuple[float, float, str]], srt: str
) -> str:
    """Silent copy of exactly `frames` frames (last frame cloned if short), captions burned."""
    vf = f"fps={FPS},tpad=stop_mode=clone:stop_duration={frames / FPS + 1:.2f}"
    if BURN_CAPTIONS and _can_burn_captions():
        write_srt(cues, srt)
        vf += "," + _subtitle_filter(os.path.abspath(srt))
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", video_path, "-vf", vf, "-frames:v", str(frames),
        "-an", "-c:v", "libx264", "-preset", os.getenv("SLIDE_X264_PRESET", "veryfast"),
        "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS), out,
    ])
    return out


def build_slide_segment(slide: dict[str, Any], video_path: str, work_dir: str) -> str:
    _, frames = slide_length(slide)
    base = os.path.join(work_dir, f"seg_{slide['id']:02d}")
    return _frame_exact(video_path, frames, base + ".mp4", caption_cues(slide), base + ".srt")


def stream_durations(path: str) -> dict[str, float]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json", path],
        capture_output=True, text=True, check=True,
    ).stdout
    return {s["codec_type"]: float(s.get("duration") or 0) for s in json.loads(out)["streams"]}


def assemble(
    slides: list[dict[str, Any]],
    videos: list[str],
    work_dir: str,
    log: Callable[[str], None] = print,
) -> tuple[str, str]:
    """One video per slide → (final_mp4, captions_vtt). Raises AVMismatchError on drift."""
    asm = os.path.join(work_dir, "assemble")
    os.makedirs(asm, exist_ok=True)
    segs = [build_slide_segment(slide, video, asm) for slide, video in zip(slides, videos)]
    vlist = os.path.join(asm, "video.txt")
    with open(vlist, "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in segs)
    video = os.path.join(asm, "video.mp4")
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", vlist, "-c", "copy", video])
    wavs, cues = _narration(slides, asm)
    return _mux(video, wavs, cues, work_dir, log)


def assemble_continuous(
    slides: list[dict[str, Any]],
    video: str,
    work_dir: str,
    log: Callable[[str], None] = print,
) -> tuple[str, str]:
    """One video for the whole lecture (slide i spans slide_length(i) frames)."""
    asm = os.path.join(work_dir, "assemble")
    os.makedirs(asm, exist_ok=True)
    wavs, cues = _narration(slides, asm)
    frames = sum(slide_length(s)[1] for s in slides)
    exact = _frame_exact(video, frames, os.path.join(asm, "video.mp4"), cues, os.path.join(asm, "lecture.srt"))
    return _mux(exact, wavs, cues, work_dir, log)


def _narration(slides: list[dict[str, Any]], asm: str) -> tuple[list[str], list[tuple[float, float, str]]]:
    wavs, cues = [], []
    offset = 0.0
    for slide in slides:
        wav = os.path.join(asm, f"seg_{slide['id']:02d}.wav")
        length = build_slide_audio(slide, wav)
        wavs.append(wav)
        cues += caption_cues(slide, offset)
        offset += length
    return wavs, cues


def _mux(
    video: str,
    wavs: list[str],
    cues: list[tuple[float, float, str]],
    work_dir: str,
    log: Callable[[str], None],
) -> tuple[str, str]:
    asm = os.path.join(work_dir, "assemble")
    audio = os.path.join(asm, "narration.wav")
    alist = os.path.join(asm, "audio.txt")
    with open(alist, "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in wavs)
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", alist, "-c", "copy", audio])

    final = os.path.join(work_dir, "lecture_final.mp4")
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", str(SAMPLE_RATE), "-ac", "2",
        "-movflags", "+faststart", final,
    ])
    vtt = os.path.join(work_dir, "captions.vtt")
    write_vtt(cues, vtt)

    d = stream_durations(final)
    diff = abs(d.get("video", 0) - d.get("audio", 0))
    log(f"  📏 Final: video {d.get('video', 0):.2f}s · audio {d.get('audio', 0):.2f}s · Δ {diff:.3f}s")
    if diff > MAX_AV_DIFF:
        raise AVMismatchError(f"Audio/video differ by {diff:.2f}s")
    return final, vtt
