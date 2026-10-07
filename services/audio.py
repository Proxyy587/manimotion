"""TTS narration with word timestamps for beat-level A/V sync."""

from __future__ import annotations

import os
import re
from typing import Any

import edge_tts

from services.beat_timing import (
    build_beat_map,
    ensure_beat_markers,
    save_beat_debug,
    strip_and_locate_beats,
)
from services.renderer import get_media_duration


async def _stream_tts_with_words(
    clean_script: str,
    output_dir: str,
    voice: str,
) -> tuple[str, str, list[dict[str, Any]], float]:
    """
    Generate MP3 + SRT + word timestamp list from clean (marker-free) script.
    edge-tts WordBoundary offset/duration are in 100-nanosecond units.
    """
    audio_path = os.path.join(output_dir, "narration.mp3")
    srt_path = os.path.join(output_dir, "captions.srt")

    communicate = edge_tts.Communicate(clean_script, voice=voice)
    submaker = edge_tts.SubMaker()
    audio_bytes = bytearray()
    word_timestamps: list[dict[str, Any]] = []
    cursor = 0

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            word = str(chunk.get("text") or "")
            # 100-ns → seconds
            start_s = float(chunk["offset"]) / 10_000_000
            dur_s = float(chunk["duration"]) / 10_000_000
            # Locate the word in the real script: TTS words omit punctuation, so a
            # running "len(word)+1" count drifts later with every comma/period.
            found = clean_script.find(word, cursor) if word else -1
            char_offset = found if found >= 0 else cursor
            end_char = char_offset + len(word)
            word_timestamps.append(
                {
                    "word": word,
                    "start_s": start_s,
                    "end_s": start_s + dur_s,
                    "char_offset": char_offset,
                    "pause_after": bool(
                        re.match(r"\s*[,.;:!?\u2014]", clean_script[end_char : end_char + 3])
                    ),
                }
            )
            cursor = end_char
            if hasattr(submaker, "feed"):
                submaker.feed(chunk)
            elif hasattr(submaker, "create_sub"):
                submaker.create_sub(word, (chunk["offset"], chunk["duration"]))

    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    srt_text = ""
    if hasattr(submaker, "get_srt"):
        srt_text = submaker.get_srt() or ""
    elif hasattr(submaker, "generate_subs"):
        srt_text = submaker.generate_subs(words_in_cue=6) or ""
    else:
        raise RuntimeError("Unsupported edge-tts SubMaker API.")

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_text)

    duration = get_media_duration(audio_path)
    if (not duration or duration <= 0) and word_timestamps:
        duration = float(word_timestamps[-1]["end_s"])
    return audio_path, srt_path, word_timestamps, float(duration or 0.0)


async def generate_audio_with_captions(
    script: str,
    output_dir: str,
    voice: str = "en-US-AriaNeural",
    log=print,
    *,
    visual_plan: dict[str, Any] | None = None,
) -> tuple[str, str, float, dict[str, dict[str, float]]]:
    """
    TTS + captions + beat_map from [BEAT:id] markers.

    Returns:
      audio_path, srt_path, audio_duration, beat_map
      beat_map[id] = {start_s, end_s, duration_sec}
    """
    log("Step 4/6: Generating TTS audio, captions, and beat timestamps...")
    os.makedirs(output_dir, exist_ok=True)

    marked = ensure_beat_markers(script, visual_plan or {})
    clean_script, beat_char_positions = strip_and_locate_beats(marked)

    # Persist scripts for debugging
    with open(os.path.join(output_dir, "narration_marked.txt"), "w", encoding="utf-8") as f:
        f.write(marked + "\n")
    with open(os.path.join(output_dir, "narration_clean.txt"), "w", encoding="utf-8") as f:
        f.write(clean_script + "\n")

    if not clean_script.strip():
        raise RuntimeError("Narration script empty after stripping beat markers")

    audio_path, srt_path, word_timestamps, audio_duration = await _stream_tts_with_words(
        clean_script=clean_script,
        output_dir=output_dir,
        voice=voice,
    )

    beat_ids = [b.get("id") for b in (visual_plan or {}).get("beats", [])]
    beat_map = build_beat_map(
        word_timestamps=word_timestamps,
        beat_char_positions=beat_char_positions,
        audio_duration=audio_duration,
        beat_ids=beat_ids or None,
    )
    save_beat_debug(output_dir, word_timestamps, beat_map)

    log(f"  ✔️ Audio saved at {audio_path} ({audio_duration:.1f}s)")
    log(f"  ✔️ Captions saved at {srt_path}")
    log(f"  ✔️ Beat map: {len(beat_map)} timed beats from word timestamps")
    return audio_path, srt_path, audio_duration, beat_map
