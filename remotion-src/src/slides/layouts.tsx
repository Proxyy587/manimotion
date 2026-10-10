import React from 'react';

import {
  ACCENTS,
  C,
  CONTENT_BOTTOM,
  CONTENT_TOP,
  FONT,
  MONO,
  PAD_X,
  W,
  appear,
  clampLines,
  countUp,
  withAlpha,
} from './theme';
import type {Item, SlideSpec} from './types';

export type Ctx = {
  frame: number;
  spec: SlideSpec;
  accent: string;
  /** Arrival progress (0..1) of item i. */
  shown: (i: number) => number;
  /** How strongly item i is the current focus (0..1). */
  emph: (i: number) => number;
  /** Opacity multiplier: unfocused items recede while another item is in focus. */
  dim: (i: number) => number;
};

const CONTENT_W = W - PAD_X * 2;
const CONTENT_H = CONTENT_BOTTOM - CONTENT_TOP;

const pad2 = (n: number) => String(n).padStart(2, '0');
const lift = (p: number, px = 22) => `0px ${(1 - p) * px}px`;
const slideIn = (p: number, px = 28) => `${(1 - p) * -px}px 0px`;

/* ---------------------------------------------------------------- bullets */

export const Bullets: React.FC<{ctx: Ctx}> = ({ctx}) => {
  const {spec, accent} = ctx;
  const n = spec.items.length;
  const hasDetail = spec.items.some((it) => it.detail);
  const fs = n <= 3 ? 56 : n <= 4 ? 50 : 44;
  const gap = n <= 3 ? (hasDetail ? 44 : 52) : hasDetail ? 26 : 34;
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap, width: '100%', maxWidth: 1480}}>
      {spec.items.map((it, i) => {
        const p = ctx.shown(i);
        const e = ctx.emph(i);
        return (
          <div
            key={i}
            style={{
              position: 'relative',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 32,
              opacity: p * ctx.dim(i),
              translate: slideIn(p),
            }}
          >
            <div
              style={{
                position: 'absolute',
                left: -36,
                top: 4,
                bottom: 4,
                width: 6,
                borderRadius: 3,
                background: accent,
                opacity: e,
              }}
            />
            <div
              style={{
                flex: 'none',
                width: fs * 1.3,
                height: fs * 1.3,
                borderRadius: fs * 0.36,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: MONO,
                fontSize: fs * 0.5,
                color: C.ink,
                background: withAlpha(accent, 0.14 + 0.5 * e),
                border: `2px solid ${withAlpha(accent, 0.45 + 0.55 * e)}`,
              }}
            >
              {pad2(i + 1)}
            </div>
            <div style={{display: 'flex', flexDirection: 'column', gap: 8, paddingTop: fs * 0.08}}>
              <div
                style={{
                  fontSize: fs,
                  fontWeight: 600,
                  lineHeight: 1.22,
                  letterSpacing: '-0.01em',
                  color: C.ink,
                  ...clampLines(2),
                }}
              >
                {it.text}
              </div>
              {it.detail && (
                <div style={{fontSize: fs * 0.62, lineHeight: 1.35, color: C.soft, ...clampLines(2)}}>
                  {it.detail}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

/* --------------------------------------------------------------- timeline */

export const Timeline: React.FC<{ctx: Ctx}> = ({ctx}) => {
  const {spec, accent} = ctx;
  const n = spec.items.length;
  const col = CONTENT_W / n;
  const fs = n >= 6 ? 32 : n >= 5 ? 35 : 40;
  const reach = spec.items.reduce((m, _, i) => Math.max(m, ctx.shown(i) * (n > 1 ? i / (n - 1) : 1)), 0);
  const lineW = CONTENT_W - col;
  const lineTop = 170;
  return (
    <div style={{position: 'relative', width: CONTENT_W, height: Math.min(CONTENT_H, 480)}}>
      <div
        style={{
          position: 'absolute',
          left: col / 2,
          width: lineW,
          top: lineTop,
          height: 5,
          borderRadius: 3,
          background: C.line,
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: col / 2,
          width: Math.max(0, lineW * reach),
          top: lineTop,
          height: 5,
          borderRadius: 2,
          background: `linear-gradient(90deg, ${withAlpha(accent, 0.4)}, ${accent})`,
          boxShadow: `0 0 18px ${withAlpha(accent, 0.6)}`,
        }}
      />
      <div style={{display: 'flex', position: 'absolute', inset: 0}}>
        {spec.items.map((it, i) => {
          const p = ctx.shown(i);
          const e = ctx.emph(i);
          return (
            <div
              key={i}
              style={{
                width: col,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                opacity: ctx.dim(i),
              }}
            >
              <div
                style={{
                  height: 130,
                  display: 'flex',
                  alignItems: 'flex-end',
                  paddingBottom: 8,
                  fontFamily: MONO,
                  fontSize: n >= 6 ? 36 : n >= 5 ? 42 : 48,
                  color: accent,
                  opacity: p,
                  translate: lift(p, 14),
                  whiteSpace: 'nowrap',
                }}
              >
                {it.label}
              </div>
              <div style={{height: 84, display: 'flex', alignItems: 'center'}}>
                <div
                  style={{
                    width: 38,
                    height: 38,
                    borderRadius: 19,
                    border: `5px solid ${accent}`,
                    background: p > 0.5 ? accent : C.bg,
                    scale: String(0.4 + 0.6 * p + 0.25 * e),
                    opacity: Math.max(0.35, p),
                    boxShadow: `0 0 0 ${14 * e}px ${withAlpha(accent, 0.22)}`,
                  }}
                />
              </div>
              <div
                style={{
                  marginTop: 18,
                  width: col - 28,
                  textAlign: 'center',
                  fontSize: fs,
                  fontWeight: 500,
                  lineHeight: 1.3,
                  color: e > 0.5 ? C.ink : C.soft,
                  opacity: p,
                  translate: lift(p),
                  ...clampLines(4),
                }}
              >
                {it.text}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------- bars */

const fmtValue = (it: Item) => {
  if (it.display) return it.display;
  const v = it.value ?? 0;
  return Number.isInteger(v) ? v.toLocaleString('en-US') : v.toFixed(1);
};

export const Bars: React.FC<{ctx: Ctx}> = ({ctx}) => {
  const {spec, accent, frame} = ctx;
  const n = spec.items.length;
  const max = Math.max(...spec.items.map((it) => Math.abs(it.value ?? 0)), 1e-9);
  const bh = n <= 4 ? 60 : n <= 5 ? 50 : 42;
  const gap = n <= 4 ? 34 : n <= 5 ? 26 : 20;
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap, width: '100%'}}>
      {spec.unit && (
        <div style={{alignSelf: 'flex-end', fontFamily: MONO, fontSize: 24, color: C.muted, marginBottom: -6}}>
          {spec.unit}
        </div>
      )}
      {spec.items.map((it, i) => {
        const p = ctx.shown(i);
        const grow = appear(frame, Math.round(spec.beatStarts[spec.reveal[i]] ?? 0), 36);
        const e = ctx.emph(i);
        const frac = Math.abs(it.value ?? 0) / max;
        return (
          <div key={i} style={{display: 'flex', alignItems: 'center', gap: 28, opacity: p * ctx.dim(i)}}>
            <div
              style={{
                width: 360,
                textAlign: 'right',
                fontSize: 32,
                fontWeight: 600,
                color: C.ink,
                lineHeight: 1.15,
                ...clampLines(2),
              }}
            >
              {it.label}
            </div>
            <div style={{flex: 1, height: bh, borderRadius: 14, background: C.card, position: 'relative'}}>
              <div
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: `${Math.max(0.6, frac * grow * 100)}%`,
                  borderRadius: 14,
                  background: `linear-gradient(90deg, ${withAlpha(accent, 0.55)}, ${accent})`,
                  boxShadow: e > 0 ? `0 0 ${28 * e}px ${withAlpha(accent, 0.55)}` : 'none',
                }}
              />
            </div>
            <div style={{width: 230, fontFamily: MONO, fontSize: 34, color: C.ink, whiteSpace: 'nowrap'}}>
              {countUp(fmtValue(it), grow)}
            </div>
          </div>
        );
      })}
    </div>
  );
};

/* ------------------------------------------------------------------ stats */

export const Stats: React.FC<{ctx: Ctx}> = ({ctx}) => {
  const {spec, frame} = ctx;
  const n = spec.items.length;
  const big = n <= 2 ? 150 : n === 3 ? 118 : 96;
  return (
    <div style={{display: 'flex', gap: 40, width: '100%', alignItems: 'stretch'}}>
      {spec.items.map((it, i) => {
        const p = ctx.shown(i);
        const e = ctx.emph(i);
        const color = ACCENTS[(spec.accent + i) % ACCENTS.length];
        const count = appear(frame, Math.round(spec.beatStarts[spec.reveal[i]] ?? 0), 42);
        return (
          <div
            key={i}
            style={{
              flex: 1,
              minWidth: 0,
              padding: '56px 44px',
              borderRadius: 32,
              background: C.card,
              border: `2px solid ${e > 0 ? withAlpha(color, 0.3 + 0.7 * e) : C.cardLine}`,
              display: 'flex',
              flexDirection: 'column',
              gap: 18,
              opacity: p * ctx.dim(i),
              translate: lift(p, 30),
            }}
          >
            <div
              style={{
                fontSize: big,
                fontWeight: 800,
                letterSpacing: '-0.04em',
                lineHeight: 1,
                color,
                whiteSpace: 'nowrap',
              }}
            >
              {countUp(it.display ?? '', count)}
            </div>
            <div style={{fontSize: 38, lineHeight: 1.3, color: C.soft, ...clampLines(3)}}>{it.text}</div>
          </div>
        );
      })}
    </div>
  );
};

/* ---------------------------------------------------------------- compare */

export const Compare: React.FC<{ctx: Ctx}> = ({ctx}) => {
  const {spec, frame} = ctx;
  const head = appear(frame, 6, 18);
  const sides: Array<'left' | 'right'> = ['left', 'right'];
  return (
    <div style={{display: 'flex', gap: 48, width: '100%', height: CONTENT_H * 0.9}}>
      {sides.map((side, s) => {
        const color = ACCENTS[(spec.accent + 1 + s) % ACCENTS.length];
        const title = side === 'left' ? spec.leftTitle : spec.rightTitle;
        const rows = spec.items.map((it, i) => ({it, i})).filter(({it}) => it.side === side);
        return (
          <div
            key={side}
            style={{
              flex: 1,
              minWidth: 0,
              borderRadius: 32,
              padding: '44px 48px',
              background: C.card,
              border: `2px solid ${C.cardLine}`,
              display: 'flex',
              flexDirection: 'column',
              gap: 30,
            }}
          >
            <div
              style={{
                fontSize: 46,
                fontWeight: 700,
                color,
                letterSpacing: '-0.01em',
                opacity: head,
                translate: lift(head, 14),
                ...clampLines(1),
              }}
            >
              {title}
            </div>
            <div style={{height: 3, width: 84 * head, background: color, borderRadius: 2}} />
            {rows.map(({it, i}) => {
              const p = ctx.shown(i);
              const e = ctx.emph(i);
              return (
                <div
                  key={i}
                  style={{display: 'flex', gap: 22, alignItems: 'flex-start', opacity: p * ctx.dim(i), translate: slideIn(p, 20)}}
                >
                  <div
                    style={{
                      flex: 'none',
                      marginTop: 20,
                      width: 22,
                      height: 6,
                      borderRadius: 3,
                      background: color,
                      scale: `${1 + e * 0.6} 1`,
                    }}
                  />
                  <div style={{fontSize: 40, fontWeight: 500, lineHeight: 1.3, color: C.ink, ...clampLines(2)}}>
                    {it.text}
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
};

/* ------------------------------------------------------------------ steps */

export const Steps: React.FC<{ctx: Ctx}> = ({ctx}) => {
  const {spec, accent} = ctx;
  const n = spec.items.length;
  const fs = n >= 5 ? 31 : n === 4 ? 35 : 40;
  return (
    <div style={{display: 'flex', alignItems: 'stretch', width: '100%'}}>
      {spec.items.map((it, i) => {
        const p = ctx.shown(i);
        const e = ctx.emph(i);
        return (
          <React.Fragment key={i}>
            {i > 0 && (
              <div style={{width: 64, flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: p}}>
                <svg width="40" height="24" viewBox="0 0 40 24">
                  <path d="M2 12h30M24 4l8 8-8 8" stroke={C.muted} strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            )}
            <div
              style={{
                flex: 1,
                minWidth: 0,
                padding: '40px 30px',
                borderRadius: 28,
                background: e > 0 ? withAlpha(accent, 0.08 * e) : C.card,
                border: `2px solid ${e > 0 ? withAlpha(accent, 0.35 + 0.65 * e) : C.cardLine}`,
                display: 'flex',
                flexDirection: 'column',
                gap: 20,
                opacity: p * ctx.dim(i),
                translate: lift(p, 26),
              }}
            >
              <div
                style={{
                  width: 60,
                  height: 60,
                  borderRadius: 30,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontFamily: MONO,
                  fontSize: 26,
                  color: C.ink,
                  background: withAlpha(accent, 0.18 + 0.6 * e),
                }}
              >
                {i + 1}
              </div>
              <div style={{fontSize: fs, fontWeight: 600, lineHeight: 1.25, color: C.ink, ...clampLines(4)}}>{it.text}</div>
              {it.detail && (
                <div style={{fontSize: fs * 0.72, lineHeight: 1.35, color: C.soft, ...clampLines(3)}}>{it.detail}</div>
              )}
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
};

/* ------------------------------------------------------------- definition */

export const Definition: React.FC<{ctx: Ctx}> = ({ctx}) => {
  const {spec, accent, frame} = ctx;
  const t = appear(frame, Math.round(spec.beatStarts[0] ?? 0), 22);
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 40, width: '100%', maxWidth: 1500}}>
      <div style={{opacity: t, translate: lift(t, 18)}}>
        <div style={{fontSize: 92, fontWeight: 800, letterSpacing: '-0.035em', color: C.ink, lineHeight: 1.05, ...clampLines(2)}}>
          {spec.term}
        </div>
        <div style={{marginTop: 22, height: 8, width: 160 * t, borderRadius: 4, background: accent}} />
      </div>
      {spec.items.map((it, i) => {
        const p = ctx.shown(i);
        const first = i === 0;
        return (
          <div
            key={i}
            style={{
              display: 'flex',
              gap: 22,
              alignItems: 'flex-start',
              opacity: p * ctx.dim(i),
              translate: lift(p, 18),
            }}
          >
            {!first && (
              <div style={{flex: 'none', marginTop: 20, width: 22, height: 6, borderRadius: 3, background: accent}} />
            )}
            <div
              style={{
                fontSize: first ? 46 : 36,
                fontWeight: first ? 500 : 400,
                lineHeight: 1.35,
                color: first ? C.ink : C.soft,
                ...clampLines(first ? 3 : 2),
              }}
            >
              {it.text}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export const LAYOUTS = {
  bullets: Bullets,
  timeline: Timeline,
  bars: Bars,
  stats: Stats,
  compare: Compare,
  steps: Steps,
  definition: Definition,
} as const;

export const BASE_FONT: React.CSSProperties = {fontFamily: FONT};
