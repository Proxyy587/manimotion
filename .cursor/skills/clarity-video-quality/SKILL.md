---
name: clarity-video-quality
description: >-
  Tune manimotion lecture generation: lesson plans, per-sentence narration,
  Manim math slides, the Remotion graphics template, audio-video sync and model
  selection. Use when improving video output, editing prompts in prompts/,
  debugging overlaps, still frames or sync, or changing services/slides/.
---

# manimotion video quality

## Read first

1. [docs/MANIM_PRODUCTION.md](../../../docs/MANIM_PRODUCTION.md): math lectures (Manim slides, guard, fallback)
2. [docs/REMOTION_PRODUCTION.md](../../../docs/REMOTION_PRODUCTION.md): graphics lectures (layout specs, fixed template)
3. [docs/MANIM_ENGINE.md](../../../docs/MANIM_ENGINE.md): Manim API pitfalls (still apply inside slides)

The legacy single-scene pipeline (`PIPELINE_V2=0`) is documented in `PROMPT_ENGINEERING.md`
and `REMOTION_ENGINE.md`. Don't tune it; all traffic uses the slide pipeline.

## Pipeline (do not break order)

```
lesson plan (style: math | graphics, chosen by the plan on "auto")
  → one TTS clip per sentence (measured durations)
  → math:     one build() body per slide → Manim render + guard → retry/fallback
    graphics: one layout spec per slide → validate/repair/fallback → one Remotion render
  → frame-exact assembly → |video − audio| ≤ 0.12 s → upload
```

Key files: `services/slides/{storyboard,narration,build,graphics,assemble,pipeline}.py`,
`services/slides/kit/slide_kit.py`, `remotion-src/src/slides/`, `prompts/slides_prompt.py`,
`prompts/graphics_prompt.py`.

## Invariants

- **Narration first, visuals fit it.** Never time-stretch audio (no `atempo`); video is only
  padded by cloning its last frame.
- **One sentence = one beat.** Every sentence reveals or highlights something; no slide is ever
  empty below its title.
- **The user's model is the only model.** No per-attempt rotation, no "strong model" escalation.
  Retired IDs are aliased in `services/llm.normalize_model` and `client/lib/chalkboard-api.ts`.
- **Length is automatic.** The duration picker defaults to Auto and is only a soft hint.
- **Graphics text is content, not code.** Layout lives in the template; the LLM never writes TSX
  on this path.
- **A bad slide degrades, never fails the job** (fallback slide, reported in `degraded_slides`).

## Do not

- Add `self.play` / `self.wait` / `self.add` to slide prompts or examples
- Loosen the slide guard to make a slide pass; fix the prompt or the slide instead
- Use absolute positioning for text in `remotion-src/src/slides/layouts.tsx`
- Call Remotion `delayRender` at module level (long renders time out)
- Change `LEAD_IN / END_HOLD / LEAD_OUT` in only one of `slide_kit.py` and `assemble.py`
- Mention Manim or Remotion in user-facing UI copy (users see "Math", "Graphics", "Auto")

## Quick test

```bash
uv run --with pytest python -m pytest -q tests
cd remotion-src && npx tsc --noEmit -p .

# real job (needs OPENROUTER_API_KEY; output in temp/phase0/<name>_final.mp4)
MODEL=anthropic/claude-sonnet-4.5 ENGINE=auto \
  uv run python temp/phase0/run_job.py internet "How the internet grew from ARPANET to today"
```

Check the log for `🧠 Model:` (it must be the selected model), `🎨 Lecture style:`, and the
final `📏 … Δ` line. Then build a contact sheet and look for overlaps and still stretches:

```bash
ffmpeg -i final.mp4 -vf "fps=1/10,scale=480:-1,tile=4x6" -frames:v 1 sheet.png
```
