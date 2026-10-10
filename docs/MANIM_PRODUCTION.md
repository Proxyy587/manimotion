# Manim Production Guide — math lectures

> How manimotion turns a math or physics topic into a narrated slide lecture that looks like a
> great teacher presenting: one idea per slide, every sentence shown as it is spoken, nothing
> overlapping, nothing frozen.
>
> Companion guides: [REMOTION_PRODUCTION.md](./REMOTION_PRODUCTION.md) (non-math lectures) ·
> [MANIM_ENGINE.md](./MANIM_ENGINE.md) (Manim API pitfalls) ·
> [PROMPT_ENGINEERING.md](./PROMPT_ENGINEERING.md) (legacy pipeline).

---

## Contents

1. [The idea in one minute](#1-the-idea-in-one-minute)
2. [Pipeline](#2-pipeline)
3. [The lesson plan](#3-the-lesson-plan)
4. [Narration and timing](#4-narration-and-timing)
5. [Writing a slide](#5-writing-a-slide)
6. [The guard: what makes a slide fail](#6-the-guard-what-makes-a-slide-fail)
7. [Retries and the fallback slide](#7-retries-and-the-fallback-slide)
8. [Assembly and the A/V guarantee](#8-assembly-and-the-av-guarantee)
9. [Visual language](#9-visual-language)
10. [Configuration](#10-configuration)
11. [Debugging a bad video](#11-debugging-a-bad-video)
12. [Quality checklist](#12-quality-checklist)

---

## 1. The idea in one minute

The old pipeline asked one LLM call for one long Manim scene and then tried to stretch it over
the narration. That produced the classic failures: text piling up, visuals finishing early and a
frozen frame talking for 20 seconds.

The slide pipeline inverts control:

- **The narration is fixed first.** Every sentence is recorded and measured before any code is
  written.
- **Time can only pass through `self.beat(i, …)`.** Sentence *i* is spoken during beat *i*, so a
  slide's length is the sum of its sentences by construction. The LLM cannot desync it.
- **The LLM writes only the body of `build(self)`** for one slide at a time, using a small,
  safe helper API (`place`, `bullets`, `morph`, …).
- **A guard runs after every beat** and rejects overlaps, off-screen objects, tiny text, empty
  slides and sentences with no motion. Errors go back to the same model as a targeted retry.
- **A deterministic fallback slide** guarantees the job finishes even if a slide can't be fixed.

Which lectures use this path: `style: "math"`, or `style: "auto"` when the lesson plan decides
the topic needs equations, graphs, geometry or derivations.

---

## 2. Pipeline

```
topic + model
  │
  ├─ 1. Lesson plan (storyboard)        services/slides/storyboard.py   1 LLM call (+ fixes)
  ├─ 2. Narration, one clip per sentence services/slides/narration.py   edge-tts, parallel
  ├─ 3. Slide code, one per slide        services/slides/build.py       LLM, 4 in parallel
  ├─ 4. Render + guard                   services/slides/kit/slide_kit.py  Manim, 2 in parallel
  ├─ 5. Assemble                         services/slides/assemble.py    ffmpeg, frame-exact
  └─ 6. Plan quality + upload            worker.py
```

| Stage | Typical time (720p, 6–8 slides) |
|---|---|
| Lesson plan | 15–40 s |
| Narration | 5–15 s |
| Slide code + render | 1.5–4 min |
| Assembly | 10–25 s |

Every LLM call uses **the model the user picked**. There is no hidden "strong model" or
per-attempt rotation. Retired OpenRouter IDs are mapped to their successors in
`services/llm.normalize_model`.

---

## 3. The lesson plan

`generate_storyboard(topic, model, style=…, duration_hint=…)` returns:

```json
{
  "title": "Derivatives",
  "style": "math",
  "slides": [
    {
      "id": 1, "title": "Slope at a Point", "kind": "graph",
      "goal": "A derivative is the slope of the tangent line",
      "beats": [
        {"text": "Here is the graph of f of x equals x squared.",
         "on_screen": "f(x)=x^2", "action": "Draw axes and the parabola"}
      ],
      "graph": {"fn": "x**2", "x_range": [-2.5, 2.5], "y_range": [0, 7], "highlight": "tangent"}
    }
  ]
}
```

Rules the plan follows (`prompts/slides_prompt.py`):

- **One idea per slide, 3–6 sentences per slide, 8–28 words per sentence.**
- **Math order:** hook → intuition with a visual → formal statement → worked example → common
  pitfall → recap.
- **Length is automatic.** A focused concept takes 4–6 slides, a typical topic 6–8, and a
  broad survey up to 12. The duration picker is only a soft hint; "Auto" is the default.
- **Spoken text is for the ear:** "x squared plus two x", never `x^2 + 2x`. The validator
  rejects LaTeX, `^`, `_`, `$` and `\` in speech.
- **`on_screen` is a key phrase or one LaTeX equation**, never a transcript of the sentence.
- **Kinds:** `graph | equation_steps | bullets | compare | custom`.

The validator re-asks the model with the exact problems; after that, `_salvage` splits overlong
slides and strips symbols so a plan always comes out.

---

## 4. Narration and timing

- Voice `en-US-AriaNeural` at `-8%` (`TTS_VOICE`, `TTS_RATE`), one clip per sentence, cached by
  a hash of voice, rate and text.
- Each beat gets `audio_dur` (measured) and `dur = audio_dur + 0.35 s` (a natural pause).
- A slide is `LEAD_IN 0.5 s + Σ dur + END_HOLD 1.2 s + LEAD_OUT 0.4 s`, rounded to whole frames
  at 30 fps (`slide_length`).
- **Audio is never time-stretched.** Video is only padded by cloning its final frame.

---

## 5. Writing a slide

The pipeline writes the class header (title + measured `BEATS`). The LLM writes the body:

```python
axes = Axes(x_range=[-2.5, 2.5, 1], y_range=[0, 7, 1], x_length=5.6, y_length=4.4,
            axis_config={"include_numbers": True, "font_size": 22}, tips=False)
self.place(axes, "left")
curve = axes.plot(lambda x: x**2, x_range=[-2.4, 2.4], color=BLUE)
fx = MathTex(r"f(x)=x^2", font_size=FONT_MATH, color=BLUE)
self.place(fx, "right", slot=(0, 3))

self.beat(0, FadeIn(axes), Create(curve), Write(fx), anim_time=1.8)
self.beat(1, Indicate(curve, color=YELLOW))
```

### The helper API

| Helper | Use |
|---|---|
| `self.beat(i, *anims, anim_time=1.2, fill=False)` | The **only** way time passes. Exactly once per sentence, in order. `fill=True` stretches a sweep over the whole sentence. |
| `self.place(mob, zone, slot=(row, rows))` | Position anything. Zones: `full`, `left`, `right`. Auto-scales to fit. |
| `self.slot_center(zone, row, rows)` | Anchor for `always_redraw` objects. |
| `self.bullets(items, zone)` | Bullet rows; reveal one per beat and dim earlier ones to 0.45. |
| `self.morph(a, b)` | Safe transform between any two objects. |
| `self.freeze(*mobs)` | Stop updaters after a `ValueTracker` sweep (cheap static frames). |
| `body_text(text, width)` | Wrapped, readable text in the slide font. |

### Rules that keep slides clean

1. Every visible object is positioned with `place()` or `slot_center()`. Labels may attach with
   `next_to(…, buff=0.2)`.
2. Axes always get `x_length` and `y_length`; curves stay inside the axes' range.
3. At most **two new text objects per beat**, and never two in the same slot. Replace text by
   morphing it.
4. Words are `Text`, math is `MathTex`. Words inside `MathTex` go in `\text{…}`, and `%` is `\%`.
5. Body text ≥ 28, equations ≥ 36. If it doesn't fit, **say less**; never shrink the font.
6. **Something moves in every beat.** A sentence that reflects on what is visible points at it
   (`Indicate`, `Circumscribe`, a color change). A bare `self.beat(i)` is only allowed for
   sentences under 4 seconds.
7. Never `self.play`, `self.wait` or `self.add`, and never imports, classes, images or SVGs.
   A static check rejects them before rendering.

---

## 6. The guard: what makes a slide fail

After each beat `SlideScene._guard` checks the frame and raises a `LayoutError` whose message
is sent back to the model verbatim:

| Message | Meaning | Typical fix |
|---|---|---|
| `leaves the safe frame` | Object outside x ±6.8 or under the caption band | `place()` it; keep curves in range |
| `covers the title area` | Content above the title's baseline | Use a zone, not the top strip |
| `text overlaps text` | Two text boxes intersect | Different slots, or morph the old one |
| `N new text objects at once` | More than two new texts in one beat | Spread over beats |
| `too small to read` | Text < 24 or math < 32 | Say less on screen |
| `the slide is empty below the title` | Nothing but the title is visible | Reveal the sentence's `on_screen` |
| `animates nothing for X s` | A sentence over 4 s with no motion | Indicate / Circumscribe / color change |

`SyncError` covers beat misuse: skipped or repeated beats, or `play/wait/add` inside
`build()`.

---

## 7. Retries and the fallback slide

```
attempt 1  → static check → render + guard
attempt 2  → same model + the exact error + targeted guidance (RETRY_GUIDANCE)
attempt 3  → same again
fallback   → FallbackSlide: one bullet per sentence from the plan's on_screen phrases,
             earlier rows dimmed, LaTeX rendered only when it looks like math
```

A failing slide never fails the job. Slides that used the fallback are listed in
`slides_report.json → degraded_slides` and in the job result.

---

## 8. Assembly and the A/V guarantee

For each slide: lead-in silence + each sentence padded to its `dur` + tail, giving audio of
exactly `frames / 30` seconds. The video is normalized to the same frame count (the last frame
is cloned if the render is short) and captions are burned into the band under the slide.
Segments are concatenated, muxed and probed:

```
📏 Final: video 212.40s · audio 212.41s · Δ 0.010s
```

If `|video − audio| > 0.12 s` the job raises `AVMismatchError` instead of shipping a drifting
video. A `captions.vtt` is always written next to the MP4.

---

## 9. Visual language

| Element | Value |
|---|---|
| Background | `#0E1117` |
| Font | `DejaVu Sans` (`SLIDE_FONT`) |
| Title / body / math sizes | 42 / 34 / 50 |
| Colors carry meaning | BLUE main object · YELLOW highlight/answer · TEAL derivative/tangent · GREEN result · RED warning · ORANGE secondary · GRAY axes |
| Reveal | `FadeIn`, `Write`, `Create`, `GrowArrow` — about 1.2 s, then hold ≥ 0.8 s |
| Emphasis | `Indicate`, `Circumscribe`, `SurroundingRectangle`, dim others to 0.45 |

---

## 10. Configuration

| Variable | Default | Meaning |
|---|---|---|
| `PIPELINE_V2` | `1` | Slide pipeline on. `0` falls back to the legacy single-scene pipeline. |
| `SLIDE_RESOLUTION` | `720` | `720` (`-qm`) or `1080` (`-qh --frame_rate 30`) |
| `SLIDE_RENDER_WORKERS` | `2` | Slides rendered in parallel (≈1 core each) |
| `SLIDE_LLM_WORKERS` | `4` | Concurrent LLM calls |
| `SLIDE_CODE_ATTEMPTS` | `3` | Code attempts per slide before the fallback |
| `SLIDE_STILL_MAX` | `4.0` | Longest sentence allowed with no motion (s) |
| `SLIDE_RENDER_TIMEOUT` | `480` | Per-slide Manim timeout (s) |
| `SLIDE_CODEGEN` | `1` | `0` renders fallback slides only (debugging) |
| `TTS_VOICE`, `TTS_RATE` | Aria, `-8%` | Narration voice |
| `CAPTIONS_BURN` | `1` | Burn captions (needs ffmpeg with libass) |

---

## 11. Debugging a bad video

Each job's work dir (`outputs/<job_id>/`, kept when `CLARITY_ENV=local`) contains:

- `storyboard.json`: the lesson plan with measured `dur` per sentence
- `slides/sNN/`: one file per attempt (`a1.py`, `a2.py`, …, `fallback.py`), `aN_error.log`
  for failed renders, and the rendered clips under `media/`
- `slides_report.json`: attempts, error types and fallbacks per slide, plus timings
- `assemble/`: per-slide audio and video, `narration.wav`, `lecture.srt`

| Symptom | Look at |
|---|---|
| A slide is plain bullets | `slides_report.json` → `error_types`; read that slide's `aN_error.log` |
| Text crowding or a frozen sentence | The guard should prevent it; make sure the image has the current `slide_kit.py` |
| Lecture too long or short | `storyboard.json`: count slides and sentences; adjust the length guidance in `prompts/slides_prompt.py` |
| Wrong model in logs | Search the log for `🧠 Model:`; it must equal the user's pick |

---

## 12. Quality checklist

Before shipping a prompt or kit change, render three topics (a graph, a derivation and a
concept) and check:

- [ ] No frame has overlapping text or anything under the caption band
- [ ] Every sentence visibly changes or highlights something
- [ ] No slide is ever empty below its title
- [ ] Equations are correct and readable at 720p
- [ ] `Δ ≤ 0.12 s` in the final log line; captions match the voice
- [ ] `degraded_slides` is empty or one slide at most
- [ ] `uv run --with pytest python -m pytest -q tests` passes
