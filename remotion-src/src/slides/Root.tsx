import React from 'react';
import {CalculateMetadataFunction, Composition} from 'remotion';

import {SlideLecture} from './SlideLecture';
import {FPS, H, W} from './theme';
import type {LectureProps} from './types';

const SAMPLE: LectureProps = {
  title: 'History of the Internet',
  slides: [
    {
      title: 'From ARPANET to the Web',
      layout: 'timeline',
      frames: 300,
      beatStarts: [15, 90, 165, 230],
      reveal: [0, 1, 2, 3],
      focus: [0, 1, 2, 3],
      items: [
        {label: '1969', text: 'ARPANET links four university computers'},
        {label: '1974', text: 'TCP/IP gives networks a common language'},
        {label: '1983', text: 'ARPANET switches to TCP/IP'},
        {label: '1991', text: 'The World Wide Web goes public'},
      ],
      index: 1,
      total: 1,
      accent: 0,
    },
  ],
};

const calculateMetadata: CalculateMetadataFunction<LectureProps> = ({props}) => ({
  durationInFrames: Math.max(1, props.slides.reduce((sum, s) => sum + Math.max(1, s.frames), 0)),
});

export const SlidesRoot: React.FC = () => (
  <Composition
    id="SlideLecture"
    component={SlideLecture}
    durationInFrames={300}
    fps={FPS}
    width={W}
    height={H}
    defaultProps={SAMPLE}
    calculateMetadata={calculateMetadata}
  />
);
