# Clarity Video — Prompt Engineering Guide

> **Legacy pipeline** (`PIPELINE_V2=0` only). Lectures are now built slide by slide. See
> [MANIM_PRODUCTION.md](./MANIM_PRODUCTION.md) for math and
> [REMOTION_PRODUCTION.md](./REMOTION_PRODUCTION.md) for graphics.

This document describes how the legacy pipeline turns a user prompt into a single-scene STEM video.

## Pipeline overview

```
User prompt
    ↓
Router (engine + optional duration)
    ↓
Beat-sheet planner (visual + narration + estimated timing)
    ↓
Narration polish with [BEAT:N] markers
    ↓
TTS (edge-tts) → word timestamps → measured beat_map
    ↓
Manim / Remotion code (timed to measured start_s / duration_sec)
    ↓
Render → ffmpeg merge (NO atempo) → R2 upload
```

**Key insight:** Voice tempo is sacred. Audio is generated first; measured beat
timestamps drive animation timing. Never stretch narration to fit the picture.

## The beat sheet

Every video is planned as sequential **beats**. Each beat has:

| Field | Purpose |
|-------|---------|
| `duration_sec` | How long this moment lasts (planner estimate → then TTS-measured) |
| `start_s` / `end_s` | Filled after TTS from word timestamps |
| `visual` | Exactly what appears and how it animates |
| `narration` | Words spoken during this beat |

Rules:
- Beats are sequential; durations sum to `target_duration_sec`
- ~2.3 words/second for narration (5s beat ≈ 11 words)
- Narration scripts include `[BEAT:N]` markers for timestamp alignment
- Manim: no sub-part equation highlights (whole `MathTex` only)
- Remotion: one `Sequence` per beat

Prompt file: `prompts/planner_prompt.py`
Timing: `services/beat_timing.py` + `services/audio.py`

## Duration policy

| Request | Behavior |
|---------|----------|
| `duration` omitted | Router + planner choose 20–120s freely |
| `duration` set | Beat sheet must sum to that length (±2s) |

Do **not** default to 60 seconds. Length should match teaching depth.
After TTS, code target duration = **measured audio length**.

## Audio ↔ video sync

1. **Plan** narrations per beat
2. **Polish** script with `[BEAT:N]` markers
3. **TTS** → word timestamps → `beat_map` (`start_s`, `duration_sec`)
4. **Rewrite** beat sheet with measured timings (`timing_source=tts`)
5. **Code** animations to start at each `start_s` and hold `duration_sec`
6. **Merge** (`services/merger.py`) — **never** `atempo`:
   - Audio longer: pad video (`tpad` freeze last frame)
   - Video longer: keep natural voice; picture may continue after audio ends

Debug artifacts in the job work dir: `words.json`, `beat_map.json`,
`narration_marked.txt`.

## Visual quality levers

### Manim
- `MANIM_QUALITY=medium` (720p30) default — was `low` before
- `MANIM_QUALITY=high` for 1080p60 on beefier VPS
- Dark bg `#0B1020`, colored accents, `TransformMatchingTex`, paced `self.wait()`

### Remotion
- Sequence-per-beat timing
- Spring entrances, clamped interpolates
- Typography scale: title 56–72px, body 28–36px

### Narration
- Beat-aligned script polish (`prompts/narration_prompt.py`)
- Edge TTS voice: `en-US-AriaNeural` (change in `services/audio.py`)
- AAC 192k in merge

## Prompt files map

| File | Role |
|------|------|
| `prompts/router_prompt.py` | manim vs remotion + duration hint |
| `prompts/planner_prompt.py` | JSON beat sheet (HOOK→SUMMARY) |
| `prompts/narration_prompt.py` | Flowing voiceover from beats (`[BEAT:N]`) |
| `prompts/manim_prompt.py` | Sync-aware Manim code |
| `prompts/remotion_prompt.py` | Sync-aware Remotion TSX |
| `prompts/quality_prompt.py` | Optional pre-render judge |

## Engine deep-dives

| Doc | Use when |
|-----|----------|
| [`docs/MANIM_PRODUCTION.md`](./MANIM_PRODUCTION.md) | Speed, tiers, templates, ETA |
| [`docs/REMOTION_PRODUCTION.md`](./REMOTION_PRODUCTION.md) | Remotion speed / design / ETA |
| [`docs/MANIM_ENGINE.md`](./MANIM_ENGINE.md) | Manim crashes, `wait(0)`, MathTex / layout rules |
| [`docs/REMOTION_ENGINE.md`](./REMOTION_ENGINE.md) | Remotion compile errors, frame math, clamps |

**Research samples** (not loaded): `prompt-docs/*.prompt.py` — port selectively into `prompts/`.

## Remotion notes

- Prefer `interpolate` + `Easing` (Remotion LLM guide); `spring` only when bounce is needed
- Strip markdown fences in `clean_code` / renderer sanitize
- Retries escalate to a simplified plan (like Manim)
- Optional: `QUALITY_JUDGE=1` runs a cheap judge before first Remotion render
- Duration cap for Remotion render: 180s (matches API)
- **Never** `durationInFrames={0}` — use `Math.max(1, Math.round(sec * 30))`

## Manim notes

- **Never** `self.wait(0)` / `run_time=0` — Manim raises `ValueError`
- Sanitizer drops zero waits and clamps non-positive `run_time`
- See [`docs/MANIM_ENGINE.md`](./MANIM_ENGINE.md)

## Tuning checklist

When a video feels poor:

- [ ] Beat sheet has enough beats (4–12)? Hook in beat 1?
- [ ] Narration lines short enough for their `duration_sec`?
- [ ] Manim using `-qm` or `-qh` (`MANIM_QUALITY`)?
- [ ] Code comments show `# BEAT N` / `{/* BEAT N */}` with matching waits?
- [ ] Crashes? Check `get_part_by_tex` sanitizer in `services/llm.py`
- [ ] Remotion fences / imports? Check `clean_code` + `_sanitize_tsx`
- [ ] Audio ahead/behind visuals? Compare `audio_duration` vs `video_duration` in logs

## Environment variables

```env
MANIM_QUALITY=medium          # low | medium | high | 4k
DEFAULT_MODEL=deepseek/deepseek-v3.2
PLANNER_MODEL=openai/gpt-4o-mini
ROUTER_MODEL=openai/gpt-4o-mini
JUDGE_MODEL=openai/gpt-4o-mini
QUALITY_JUDGE=0               # set 1 to enable pre-render quality gate
CLARITY_ENV=vps               # deletes local files after R2 upload
```

## Roadmap (public API)

Planned before launch:
- Per-user R2 bucket credentials
- Usage metering + pricing tiers
- Webhook on job complete
- Optional `voice` / `style` request fields

See `docs/ROADMAP.md` for details.

## For agents

When editing prompts in this repo, read `.cursor/skills/clarity-video-quality/SKILL.md` first.
