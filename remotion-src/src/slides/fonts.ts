import {useEffect, useState} from 'react';
import {continueRender, delayRender, staticFile} from 'remotion';

let loading: Promise<unknown> | null = null;

const loadFonts = (): Promise<unknown> => {
  if (!loading) {
    const faces = [
      new FontFace('Inter', `url(${staticFile('fonts/Inter-Variable.woff2')}) format('woff2')`, {
        weight: '100 900',
      }),
      new FontFace(
        'JetBrains Mono',
        `url(${staticFile('fonts/JetBrainsMono-500.woff2')}) format('woff2')`,
        {weight: '500'},
      ),
    ];
    loading = Promise.all(
      faces.map((f) => f.load().then((loaded) => document.fonts.add(loaded))),
    ).catch(() => undefined);
  }
  return loading;
};

/** Hold the frame until the bundled fonts are ready so text never renders in a fallback face. */
export const useFonts = () => {
  const [handle] = useState(() => delayRender('Loading fonts'));
  useEffect(() => {
    let done = false;
    loadFonts().finally(() => {
      if (!done) {
        done = true;
        continueRender(handle);
      }
    });
    return () => {
      if (!done) {
        done = true;
        continueRender(handle);
      }
    };
  }, [handle]);
};
