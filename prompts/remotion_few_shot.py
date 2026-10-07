"""Verified Remotion pattern injected into the system prompt (few-shot)."""

VERIFIED_REMOTION_EXAMPLE = """
═══════════════════════════════════════
VERIFIED WORKING EXAMPLE — COPY THIS STRUCTURE
═══════════════════════════════════════
Beat-per-slide with Series, clamped interpolate, data defined outside the component,
a bar chart and a counter. Every durationInFrames is Math.max(1, ...).

import React from 'react';
import {AbsoluteFill, Easing, Series, interpolate, useCurrentFrame} from 'remotion';

const FPS = 30;
const sec = (s: number) => Math.max(1, Math.round(s * FPS));

const BARS: {label: string; value: number; color: string}[] = [
  {label: '2021', value: 40, color: '#7C3AED'},
  {label: '2022', value: 65, color: '#06B6D4'},
  {label: '2023', value: 90, color: '#10B981'},
];

const FadeUp: React.FC<{delay?: number; children: React.ReactNode}> = ({delay = 0, children}) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [delay, delay + 20], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });
  return <div style={{opacity: t, transform: `translateY(${(1 - t) * 40}px)`}}>{children}</div>;
};

const TitleSlide: React.FC = () => (
  <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: 80}}>
    <FadeUp>
      <h1 style={{fontSize: 72, margin: 0}}>Growth at a glance</h1>
    </FadeUp>
    <FadeUp delay={15}>
      <p style={{fontSize: 32, color: '#94A3B8'}}>Three years of adoption</p>
    </FadeUp>
  </AbsoluteFill>
);

const ChartSlide: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: 80}}>
      <div style={{display: 'flex', alignItems: 'flex-end', gap: 60, height: 500}}>
        {BARS.map((bar, i) => {
          const grow = interpolate(frame, [i * 10, i * 10 + 30], [0, bar.value], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
            easing: Easing.out(Easing.cubic),
          });
          return (
            <div key={bar.label} style={{display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
              <span style={{fontSize: 32, fontVariantNumeric: 'tabular-nums'}}>{Math.round(grow)}%</span>
              <div style={{width: 140, height: grow * 4, backgroundColor: bar.color, borderRadius: 12}} />
              <span style={{fontSize: 28, color: '#94A3B8', marginTop: 12}}>{bar.label}</span>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

export const MainComposition: React.FC<{topic?: string}> = () => {
  return (
    <AbsoluteFill style={{backgroundColor: '#0B1020', color: 'white', fontFamily: 'Inter, system-ui, sans-serif'}}>
      <Series>
        {/* BEAT 1 @ 0.0s (4.0s) */}
        <Series.Sequence durationInFrames={sec(4.0)}>
          <TitleSlide />
        </Series.Sequence>
        {/* BEAT 2 @ 4.0s (6.0s) */}
        <Series.Sequence durationInFrames={sec(6.0)}>
          <ChartSlide />
        </Series.Sequence>
      </Series>
    </AbsoluteFill>
  );
};

KEY RULES THIS EXAMPLE FOLLOWS:
- Hooks (useCurrentFrame) only at the top of a component — never inside .map(), if, or callbacks.
  Inside a Sequence, useCurrentFrame() is LOCAL to that Sequence (starts at 0).
- Every interpolate input range is strictly increasing with distinct numbers, and clamped.
- Data arrays are typed and defined outside the component.
"""
