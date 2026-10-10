export type Layout = 'bullets' | 'timeline' | 'bars' | 'stats' | 'compare' | 'steps' | 'definition';

export type Item = {
  text: string;
  detail?: string;
  label?: string;
  value?: number;
  display?: string;
  side?: 'left' | 'right';
};

export type SlideSpec = {
  title: string;
  layout: Layout;
  /** Total frames, computed by the pipeline from the narration. */
  frames: number;
  /** Frame (within the slide) at which each spoken sentence starts. */
  beatStarts: number[];
  /** reveal[i] = the beat during which item i appears. */
  reveal: number[];
  /** focus[b] = the item the sentence in beat b talks about (-1 for none). */
  focus: number[];
  items: Item[];
  term?: string;
  leftTitle?: string;
  rightTitle?: string;
  unit?: string;
  index: number;
  total: number;
  accent: number;
};

export type LectureProps = {
  title: string;
  slides: SlideSpec[];
};
