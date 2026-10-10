import React from 'react';
import {AbsoluteFill, Series, useCurrentFrame} from 'remotion';

import {useFonts} from './fonts';
import {BASE_FONT, Ctx, LAYOUTS} from './layouts';
import {
  ACCENTS,
  C,
  CONTENT_BOTTOM,
  CONTENT_TOP,
  FOCUS_FADE,
  MONO,
  PAD_X,
  appear,
  clamp01,
  clampLines,
  disappear,
} from './theme';
import type {LectureProps, SlideSpec} from './types';

const LEAD_OUT_FRAMES = 12;

/** 0..1: how much item i is the subject of the sentence being spoken right now. */
const focusLevel = (frame: number, spec: SlideSpec, i: number) => {
  const n = spec.focus.length;
  let level = 0;
  let b = 0;
  while (b < n) {
    if (spec.focus[b] !== i) {
      b++;
      continue;
    }
    let e = b;
    while (e + 1 < n && spec.focus[e + 1] === i) e++;
    const start = spec.beatStarts[b];
    const end = e + 1 < n ? spec.beatStarts[e + 1] : spec.frames;
    const up = clamp01((frame - start) / FOCUS_FADE);
    const down = e + 1 < n ? clamp01((end - frame) / FOCUS_FADE) : 1;
    level = Math.max(level, Math.min(up, down));
    b = e + 1;
  }
  return level;
};

const Background: React.FC = () => (
  <AbsoluteFill
    style={{
      background: [
        'radial-gradient(1100px 680px at 88% -12%, rgba(139,92,246,0.20), transparent 62%)',
        'radial-gradient(900px 620px at -8% 112%, rgba(34,211,238,0.12), transparent 60%)',
        C.bg,
      ].join(', '),
    }}
  >
    <AbsoluteFill
      style={{
        backgroundImage:
          'linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)',
        backgroundSize: '96px 96px',
        maskImage: 'radial-gradient(ellipse at 50% 40%, black 30%, transparent 80%)',
      }}
    />
  </AbsoluteFill>
);

const Header: React.FC<{spec: SlideSpec; accent: string; frame: number}> = ({spec, accent, frame}) => {
  const p = appear(frame, 0, 16);
  const size = spec.title.length > 42 ? 50 : spec.title.length > 32 ? 56 : 64;
  return (
    <div style={{position: 'absolute', left: PAD_X, right: PAD_X, top: 92, opacity: p, translate: `0px ${(1 - p) * 16}px`}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 18, marginBottom: 18}}>
        <div style={{width: 44 * p, height: 5, borderRadius: 3, background: accent}} />
        <div style={{fontFamily: MONO, fontSize: 22, letterSpacing: '0.12em', color: C.muted}}>
          {String(spec.index).padStart(2, '0')} / {String(spec.total).padStart(2, '0')}
        </div>
      </div>
      <div
        style={{
          fontSize: size,
          fontWeight: 700,
          letterSpacing: '-0.025em',
          lineHeight: 1.08,
          color: C.ink,
          ...clampLines(1),
        }}
      >
        {spec.title}
      </div>
    </div>
  );
};

const Slide: React.FC<{spec: SlideSpec}> = ({spec}) => {
  const frame = useCurrentFrame();
  const accent = ACCENTS[spec.accent % ACCENTS.length];
  const levels = spec.items.map((_, i) => focusLevel(frame, spec, i));
  const anyFocus = Math.max(0, ...levels);
  const ctx: Ctx = {
    frame,
    spec,
    accent,
    shown: (i) => appear(frame, Math.round(spec.beatStarts[spec.reveal[i]] ?? 0)),
    emph: (i) => levels[i] ?? 0,
    dim: (i) => 1 - 0.52 * anyFocus * (1 - (levels[i] ?? 0)),
  };
  const Layout = LAYOUTS[spec.layout] ?? LAYOUTS.bullets;
  const out = disappear(frame, spec.frames, LEAD_OUT_FRAMES);
  const progress = (spec.index - 1 + frame / Math.max(1, spec.frames)) / Math.max(1, spec.total);

  return (
    <AbsoluteFill style={{...BASE_FONT, color: C.ink}}>
      <div style={{position: 'absolute', left: 0, top: 0, height: 4, width: `${progress * 100}%`, background: accent, opacity: 0.85}} />
      <AbsoluteFill style={{opacity: out}}>
        <Header spec={spec} accent={accent} frame={frame} />
        <div
          style={{
            position: 'absolute',
            left: PAD_X,
            right: PAD_X,
            top: CONTENT_TOP,
            height: CONTENT_BOTTOM - CONTENT_TOP,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Layout ctx={ctx} />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const SlideLecture: React.FC<LectureProps> = ({slides}) => {
  useFonts();
  return (
    <AbsoluteFill>
      <Background />
      <Series>
        {slides.map((spec, i) => (
          <Series.Sequence key={i} durationInFrames={Math.max(1, spec.frames)}>
            <Slide spec={spec} />
          </Series.Sequence>
        ))}
      </Series>
    </AbsoluteFill>
  );
};
