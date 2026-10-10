"""Step 2: one TTS clip per beat sentence → exact per-beat durations."""

from __future__ import annotations

import asyncio
import hashlib
import os
from typing import Any, Callable

import edge_tts

from services.renderer import get_media_duration

VOICE = os.getenv("TTS_VOICE", "en-US-AriaNeural")
RATE = os.getenv("TTS_RATE", "-8%")
PAUSE = 0.35  # silence after every sentence; part of beat.dur
CONCURRENCY = 4
RETRIES = 3


async def _synthesize(text: str, path: str) -> None:
    for attempt in range(1, RETRIES + 1):
        try:
            await edge_tts.Communicate(text, voice=VOICE, rate=RATE).save(path)
            if os.path.getsize(path) > 0:
                return
            raise RuntimeError("empty audio")
        except Exception:
            if attempt == RETRIES:
                raise
            await asyncio.sleep(1.5 * attempt)


async def record_beats(
    storyboard: dict[str, Any],
    work_dir: str,
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    """
    Record every beat sentence and annotate the storyboard in place:
    beat["audio"], beat["audio_dur"], beat["dur"] (= audio_dur + PAUSE).
    """
    audio_dir = os.path.join(work_dir, "narration")
    os.makedirs(audio_dir, exist_ok=True)
    beats = [b for s in storyboard["slides"] for b in s["beats"]]
    sem = asyncio.Semaphore(CONCURRENCY)
    done = 0

    async def one(beat: dict[str, Any]) -> None:
        nonlocal done
        key = hashlib.sha1(f"{VOICE}|{RATE}|{beat['text']}".encode()).hexdigest()[:16]
        path = os.path.join(audio_dir, f"{key}.mp3")
        async with sem:
            if not (os.path.exists(path) and os.path.getsize(path) > 0):
                await _synthesize(beat["text"], path)
        audio_dur = await asyncio.to_thread(get_media_duration, path)
        beat["audio"] = path
        beat["audio_dur"] = round(audio_dur, 3)
        beat["dur"] = round(audio_dur + PAUSE, 3)
        done += 1
        if on_progress:
            on_progress(done, len(beats))

    await asyncio.gather(*(one(b) for b in beats))
