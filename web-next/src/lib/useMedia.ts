import {useEffect, useState} from 'react';

/** Whether a media query matches, kept current on change ("(max-width: 639px)" is the phone
 *  layout of the redesigned screens: pair mode in the comparison, one column in the picker). */
export function useMedia(query: string): boolean {
  const [matches, setMatches] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatches(mq.matches);
    on();
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, [query]);
  return matches;
}
