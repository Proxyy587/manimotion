# Remotion Production Guide — graphics lectures

> How manimotion turns history, processes, data and concepts into a narrated motion-graphics
> lecture that looks like a designer built the deck: consistent typography, a clear focus on
> what is being said, and no overlapping text, ever.
>
> Companion guides: [MANIM_PRODUCTION.md](./MANIM_PRODUCTION.md) (math lectures) ·
> [REMOTION_ENGINE.md](./REMOTION_ENGINE.md) (legacy free-form TSX pipeline).

---

## Contents

1. [The idea in one minute](#1-the-idea-in-one-minute)
2. [Pipeline](#2-pipeline)
3. [The slide spec](#3-the-slide-spec)
4. [Layouts](#4-layouts)
5. [Beats: reveal and focus](#5-beats-reveal-and-focus)
6. [Validation, repair and fallback](#6-validation-repair-and-fallback)
7. [The template](#7-the-template)
8. [Rendering](#8-rendering)
9. [Design system](#9-design-system)
10. [Adding or changing a layout](#10-adding-or-changing-a-layout)
11. [Configuration](#11-configuration)
12. [Debugging a bad video](#12-debugging-a-bad-video)
13. [Quality checklist](#13-quality-checklist)

---

## 1. The idea in one minute

The old Remotion path asked the LLM to write a whole TSX composition with absolute
positioning. Every video was a new, untested layout, so text collided, animations were
random and visuals ended long before the narration did.

The graphics path splits the work:

- **The LLM writes content, not code.** For each slide it picks a layout (`timeline`, `bars`,
  `stats`, …), writes short on-screen phrases, and says which item appears or is highlighted on
  each sentence.
- **One hand-designed Remotion template renders every lecture** (`remotion-src/src/slides`).
  Layout is flexbox with fixed type scales and line clamps, so text cannot overlap or spill.
- **Every sentence reveals or focuses something.** Items arrive exactly when their sentence
  starts, and the item being discussed is highlighted while the others recede. A slide is
  never a still frame waiting for the voice to finish.
- **The whole lecture renders in one pass** against the same frame-exact timing as the Manim
  path, and goes through the same assembly and A/V assertion.

Which lectures use this path: `style: "graphics"`, or `style: "auto"` when the lesson plan
decides the topic needs no equations.

---

## 2. Pipeline

```
topic + model
  │
  ├─ 1. Lesson plan (style = graphics)    services/slides/storyboard.py
  ├─ 2. Narration, one clip per sentence  services/slides/narration.py
  ├─ 3. Design: one spec per slide        services/slides/graphics.py  design_slide()   LLM, parallel
  ├─ 4. Props: frames + beat starts       services/slides/graphics.py  lecture_props()
  ├─ 5. Render the lecture                services/slides/graphics.py  render_lecture() Remotion
  └─ 6. Assemble                          services/slides/assemble.py  assemble_continuous()
```

| Stage | Typical time (6–8 slides, 720p) |
|---|---|
| Lesson plan | 15–40 s |
| Narration | 5–15 s |
| Design (all slides in parallel) | 10–25 s |
| Render | about 0.4× the lecture length on 8 cores; slower on small VPSes |
| Assembly | 10–20 s |

The model used for the plan and every design call is **the model the user picked**.

---

## 3. The slide spec

What the LLM returns for one slide (`prompts/graphics_prompt.py`):

```json
{
  "layout": "timeline",
  "items": [
    {"label": "1969", "text": "First ARPANET message, UCLA → Stanford"},
    {"label": "1983", "text": "Network adopts TCP/IP"},
    {"label": "1991", "text": "World Wide Web launches"}
  ],
  "beats": [
    {"show": [0], "focus": 0},
    {"show": [],  "focus": 0},
    {"show": [1], "focus": 1},
    {"show": [2], "focus": 2}
  ]
}
```

`lecture_props()` adds the timing and returns the `SlideLecture` props:

```json
{
  "title": "How the Internet Grew",
  "slides": [{
    "title": "ARPANET: The First Connection", "layout": "timeline",
    "frames": 642, "beatStarts": [15, 152, 301, 455],
    "reveal": [0, 2, 3], "focus": [0, 0, 1, 2],
    "items": [...], "index": 2, "total": 7, "accent": 1
  }]
}
```

- `frames`: the slide's exact length (`slide_length`, the same formula as the Manim path).
- `beatStarts[b]`: the frame where sentence *b* starts (`LEAD_IN + Σ previous dur`).
- `reveal[i]`: the beat on which item *i* appears.
- `focus[b]`: the item sentence *b* is about, or `-1`.

---

## 4. Layouts

| Layout | Items | Item fields (max chars) | Best for |
|---|---|---|---|
| `bullets` | 2–6 | `text` 64, `detail` 76 | Key points, takeaways, recap |
| `timeline` | 2–6 | `label` 12 (a year), `text` 48 | History, milestones, eras |
| `bars` | 2–7 | `label` 24, `value` number, `display` 10; slide `unit` | Comparing quantities |
| `stats` | 1–4 | `display` 9 (e.g. `5.4B`), `text` 48 | Headline numbers |
| `compare` | 2–8 | `side` left/right, `text` 52; slide `left_title`, `right_title` | Before/after, A vs B |
| `steps` | 2–5 | `text` 38, `detail` 60 | Processes, pipelines, cycles |
| `definition` | 1–3 | slide `term` 30; `text` 110 | Introducing a key term |

How each one moves:

- **bullets:** numbered chips slide in; the focused row gets an accent bar and a filled chip.
- **timeline:** the rail draws itself up to the newest milestone; nodes pop in; the focused
  node glows and its caption brightens.
- **bars:** each bar grows over 1.2 s while its value counts up; the focused bar glows.
- **stats:** big numbers count up inside cards; the focused card gets an accent border.
- **compare:** two cards with colored headers; rows arrive on their side; the focused marker
  stretches.
- **steps:** boxes connected by arrows; the focused step is tinted.
- **definition:** a large term with an underline that draws in, then the definition and
  examples.

---

## 5. Beats: reveal and focus

The narration is fixed. `beats` has exactly one entry per sentence:

- **`show`**: items that appear as this sentence starts. Every item appears exactly once, in
  order.
- **`focus`**: the item this sentence is about. While a focus is active, every other item dims
  to about 50% so the eye goes where the voice is.
- A sentence that reflects on something already visible shows nothing and focuses that item.
- **No sentence may show nothing and focus nothing.** That's exactly the still-frame failure
  this design removes.

Focus transitions fade over 10 frames; consecutive beats with the same focus merge into one
continuous highlight, so it never flickers.

---

## 6. Validation, repair and fallback

```
LLM spec ─► normalize (clean text, drop emoji, settle beats) ─► validate
   ▲                                                              │ problems
   └──────────── one retry with the exact problem list ◄──────────┘
                                                                  │ still invalid
                    repair (shorten text, rebuild reveal plan) ◄──┘
                                                                  │ unusable
                    fallback: bullets from the plan's on_screen phrases
```

- **Settle beats** fixes mechanical mistakes without spending an LLM call: duplicate or
  out-of-range indices, focusing an item before it is shown, or an empty first sentence.
- **Validate** enforces the item counts, character limits, required fields per layout, no
  LaTeX or markup (currency like `$4.2B` is allowed) and the beat rules.
- **Repair** shortens over-long text at word boundaries and spreads reveals evenly across the
  sentences.
- **Fallback** always validates. Fallback slides are reported in `degraded_slides`.

`design_slide()` never raises; one bad slide can't fail a lecture.

---

## 7. The template

```
remotion-src/src/slides/
  index.ts          registerRoot(SlidesRoot) (separate entry; the legacy pipeline rewrites src/Root.tsx)
  Root.tsx          <Composition id="SlideLecture"> + calculateMetadata (Σ frames) + sample props
  SlideLecture.tsx  background, header, progress bar, focus math, <Series> of slides
  layouts.tsx       the seven layouts
  theme.ts          canvas, colors, accents, spacing, easing helpers
  fonts.ts          useFonts(): loads bundled Inter + JetBrains Mono before the first frame
  types.ts          SlideSpec / LectureProps
remotion-src/public/fonts/  Inter-Variable.woff2, JetBrainsMono-500.woff2
```

Anatomy of a slide (1920 × 1080 canvas):

```
┌─ progress bar (accent, grows across the lecture) ───────────────────────────┐
│  ── 02 / 07                                                   (mono kicker)  │
│  ARPANET: The First Connection                                (title 50–64)  │
│                                                                              │
│  ┌──────────── content area: y 268 → 880, x 128 → 1792 ──────────────────┐   │
│  │                  layout, centred, flexbox only                        │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                    caption band (burned captions)                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

Motion: items enter over 20 frames with an ease-out curve (`cubic-bezier(0.16, 1, 0.3, 1)`)
and a short lift or slide. The slide fades out over its last 12 frames. Nothing else moves, so
the animation follows the narration.

Preview with the built-in sample lecture:

```bash
cd remotion-src && npx remotion studio src/slides/index.ts
```

Or render a real job's props:

```bash
npx remotion render src/slides/index.ts SlideLecture out.mp4 \
  --props=../outputs/<job_id>/graphics/props.json --frames=0-300
```

---

## 8. Rendering

`render_lecture()` runs:

```
remotion render src/slides/index.ts SlideLecture graphics/lecture.mp4
  --props=graphics/props.json --scale=0.667 (720p) | 1 (1080p)
  --concurrency=$REMOTION_CONCURRENCY --jpeg-quality=92
  --browser-executable <Chrome Headless Shell>
```

- **Fonts** load once per tab through a component-level `delayRender`, so every frame uses
  Inter. Never call `delayRender` at module level: it isn't cleared reliably on long renders
  and fails them about 30 seconds in.
- **Timeout** is `max(900 s, frames / 4)`; a failed render is retried once.
- **Assembly** (`assemble_continuous`) builds the narration track, forces the video to the exact
  total frame count, burns captions, muxes and asserts `|video − audio| ≤ 0.12 s`.

---

## 9. Design system

| Token | Value |
|---|---|
| Background | `#090E1C` with violet and cyan radial glows and a faint 96 px grid |
| Ink / soft / muted | `#F4F6FB` / `#B4BCD3` / `#6E7794` |
| Accents (one per slide, cycling) | `#8B5CF6` `#22D3EE` `#F59E0B` `#34D399` `#F472B6` `#60A5FA` |
| Fonts | Inter (100–900), JetBrains Mono 500 for numbers, labels and kickers |
| Title | 64 / 56 / 50 px by length, 700, −0.025em, one line |
| Body | 40–56 px bullets, 32–40 px captions, 96–150 px stat numbers |
| Cards | `rgba(255,255,255,0.045)` fill, 2 px border, 28–32 px radius |
| Margins | 128 px left/right; content never enters the title or caption bands |

Writing for the screen:

- Short key phrases: "Network adopts TCP/IP", not "In 1983 the network adopted TCP/IP".
- Parallel phrasing across items.
- Real numbers and dates only. If the model isn't sure of a figure, it should choose a layout
  that doesn't need one.

---

## 10. Adding or changing a layout

1. Add the component to `layouts.tsx` and register it in `LAYOUTS`. Use flexbox only, no
   absolute coordinates for text, and `clampLines(n)` on every text block.
2. Add the name to `Layout` in `types.ts`.
3. Add item counts and text limits in `services/slides/graphics.py` (`ITEM_COUNTS`,
   `TEXT_LIMITS`) and any required-field checks in `validate_spec`.
4. Describe it in `GRAPHICS_SLIDE_SYSTEM_PROMPT` with the same limits.
5. Add a sample slide in `Root.tsx`, check it in Studio at maximum item count and maximum text
   length, then run `npx tsc --noEmit -p .` and the Python tests.

---

## 11. Configuration

| Variable | Default | Meaning |
|---|---|---|
| `PIPELINE_V2` | `1` | Slide pipeline (both styles) |
| `SLIDE_RESOLUTION` | `720` | `720` renders at scale 2/3, `1080` at full size |
| `REMOTION_CONCURRENCY` | half the cores, max 4 | Chrome tabs rendering frames |
| `SLIDE_LLM_WORKERS` | `4` | Concurrent design calls |
| `CAPTIONS_BURN` | `1` | Burn captions under the slide |

---

## 12. Debugging a bad video

Work dir `outputs/<job_id>/`:

- `storyboard.json`: the plan, with `style` and measured sentence durations
- `graphics_props.json`: exactly what the template received
- `graphics/lecture.mp4`: the silent render; `graphics/render_error.log` if it failed
- `slides_report.json`: per-slide attempts and fallbacks, plus timings

| Symptom | Look at |
|---|---|
| A slide is plain bullets | `slides_report.json` → `used_fallback`; the log line `🔁 Slide N design attempt …` |
| Wrong item highlighted | `graphics_props.json` → that slide's `focus` vs the sentences in `storyboard.json` |
| Text truncated with "…" | The model ignored the limit and repair shortened it; tighten the prompt wording |
| Render timed out | Lower `REMOTION_CONCURRENCY` on small machines; check `render_error.log` |
| A math topic came out as graphics | Auto style chose graphics; pick Math explicitly or sharpen `STYLE_HINTS["auto"]` |

---

## 13. Quality checklist

Render three topics (a timeline, a data topic and a process) and check:

- [ ] No text ever overlaps, truncates mid-word or leaves the content area
- [ ] Every sentence reveals or highlights something; no still stretches
- [ ] The highlighted item always matches what the voice is saying
- [ ] Numbers and dates are correct
- [ ] Fonts are Inter and JetBrains Mono, never a serif fallback
- [ ] `Δ ≤ 0.12 s` in the final log line; captions match the voice
- [ ] `npx tsc --noEmit -p .` in `remotion-src` and the Python tests pass
