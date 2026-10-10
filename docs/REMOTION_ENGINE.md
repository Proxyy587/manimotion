# Remotion engine guide (Clarity / manimotion)

> **Legacy pipeline** (`PIPELINE_V2=0` only). Graphics lectures now use a fixed, designed template
> that the LLM fills with content. See [REMOTION_PRODUCTION.md](./REMOTION_PRODUCTION.md).

How we generate **reliable** Remotion compositions for STEM motion graphics.
Prompts live in `prompts/remotion_prompt.py`; sanitization in `services/llm.py`.

## Goal

One compile + render that:
1. Matches measured narration beats (`timing_source=tts`) at 30fps
2. Uses only `react` + `remotion` imports
3. Never emits `durationInFrames={0}` or unclamped interpolations

## Pipeline contract

```
beat sheet (measured start_s / duration_sec)
  → LLM TSX (MainComposition)
  → sanitize (React import, strip fences, durationInFrames={0}→1)
  → Remotion CLI render
  → ffmpeg merge (no atempo)
```

## Non-negotiable API rules

| Rule | Why |
|------|-----|
| `export const MainComposition` | Renderer looks up this name |
| Imports only from `react` and `remotion` | Bundle has nothing else |
| `durationInFrames >= 1` | Zero-length sequences break / blank |
| `Sequence from >= 0` | Negative starts are invalid |
| `interpolate` always clamped | Prevents NaN / runaway values |
| Hooks only inside the component | Rules of Hooks |
| No default export | Named export only |
| No emoji / external assets | Font/glyph and network failures |

### Frame math (fps = 30)

```tsx
const framesFor = (sec: number) => Math.max(1, Math.round(sec * 30));
const startFrame = (sec: number) => Math.max(0, Math.round(sec * 30));

<Sequence from={startFrame(3.2)} durationInFrames={framesFor(4.0)}>
  {/* BEAT 2 */}
</Sequence>
```

Or with `Series` (preferred for sequential beats):

```tsx
<Series>
  <Series.Sequence durationInFrames={framesFor(3.2)}>{/* BEAT 1 */}</Series.Sequence>
  <Series.Sequence durationInFrames={framesFor(4.0)}>{/* BEAT 2 */}</Series.Sequence>
</Series>
```

## Design tokens

| Token | Value |
|-------|--------|
| Background | `#0B1020` |
| Text | `#FFFFFF` / `#94A3B8` |
| Accents | `#7C3AED`, `#06B6D4`, `#F59E0B`, `#10B981` |
| Title | 56–72px |
| Body | 28–36px |
| Font | `Inter, system-ui, sans-serif` |
| Padding | 60–80px |

## Motion patterns

Always clamp:

```tsx
const t = interpolate(frame, [delay, delay + 25], [0, 1], {
  extrapolateLeft: 'clamp',
  extrapolateRight: 'clamp',
  easing: Easing.out(Easing.cubic),
});
```

Spring (only when bounce is needed):

```tsx
spring({
  frame: Math.max(0, frame - delay),
  fps,
  config: { damping: 14, stiffness: 100 },
});
```

Drive motion from `frame` — do **not** use CSS transitions for timeline animation.

## Beat sync checklist

- One `Series.Sequence` / `Sequence` per beat
- Comment `{/* BEAT N @ Ts (Ds) */}`
- Visual appears near the **start** of the sequence
- `durationInFrames ≈ duration_sec * 30` (≥ 1)
- Max ~8 sequences (matches planner cap)
- Total ≈ `target_duration_sec * 30`

## Banned / high-risk patterns

- `durationInFrames={0}` or `durationInFrames={Math.round(0)}`
- Imports from anywhere except `react` / `remotion`
- `useCurrentFrame()` outside `MainComposition`
- Unclamped `interpolate`
- `export default`
- Markdown fences around the component
- External images, fonts, or `fetch`

## Retry policy

Worker: max 3 attempts. Attempt ≥2 forces a simple AbsoluteFill + text/SVG plan.
Optional: `QUALITY_JUDGE=1` rejects weak first drafts before render.

Error hints: `REMOTION_ERROR_HINTS` in `prompts/remotion_prompt.py`.

## See also

- `docs/PROMPT_ENGINEERING.md` — full pipeline
- `docs/MANIM_ENGINE.md` — Manim counterpart
- `.cursor/skills/clarity-video-quality/SKILL.md`
