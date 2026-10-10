import type {CSSProperties} from 'react';
import {Easing, interpolate} from 'remotion';

export const W = 1920;
export const H = 1080;
export const FPS = 30;

export const C = {
  bg: '#090E1C',
  ink: '#F4F6FB',
  soft: '#B4BCD3',
  muted: '#6E7794',
  line: 'rgba(255,255,255,0.10)',
  card: 'rgba(255,255,255,0.045)',
  cardLine: 'rgba(255,255,255,0.09)',
};

export const ACCENTS = ['#8B5CF6', '#22D3EE', '#F59E0B', '#34D399', '#F472B6', '#60A5FA'];

export const FONT = 'Inter, system-ui, sans-serif';
export const MONO = '"JetBrains Mono", ui-monospace, monospace';

/** Safe area: content never enters the caption band at the bottom. */
export const PAD_X = 128;
export const CONTENT_TOP = 268;
export const CONTENT_BOTTOM = 880;

export const ENTER = 20; // frames an item takes to arrive (~0.67s)
export const FOCUS_FADE = 10;

const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
const easeIn = Easing.bezier(0.7, 0, 0.84, 0);

export const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/** 0 → 1 starting at `at`, ease-out over `dur` frames. */
export const appear = (frame: number, at: number, dur = ENTER) =>
  interpolate(frame, [at, at + dur], [0, 1], {
    easing: easeOut,
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

/** 1 → 0 over the last `dur` frames before `end`. */
export const disappear = (frame: number, end: number, dur: number) =>
  interpolate(frame, [end - dur, end], [1, 0], {
    easing: easeIn,
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

export const withAlpha = (hex: string, alpha: number) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
};

export const clampLines = (lines: number): CSSProperties => ({
  display: '-webkit-box',
  WebkitLineClamp: lines,
  WebkitBoxOrient: 'vertical',
  overflow: 'hidden',
});

/** "1,250" / "4.2B" / "70%" counted up from zero by progress p. */
export const countUp = (display: string, p: number): string => {
  const m = display.match(/^([^0-9]*)([0-9][0-9,]*(?:\.[0-9]+)?)(.*)$/);
  if (!m) return display;
  const raw = parseFloat(m[2].replace(/,/g, ''));
  if (!Number.isFinite(raw)) return display;
  const decimals = (m[2].split('.')[1] || '').length;
  const v = raw * p;
  const body = m[2].includes(',')
    ? v.toLocaleString('en-US', {minimumFractionDigits: decimals, maximumFractionDigits: decimals})
    : v.toFixed(decimals);
  return m[1] + body + m[3];
};
