import {createContext, useContext} from 'react';

/**
 * Presentation switches of the design review that reach components outside the comparison
 * grid (the status badges also sit in the picker and the profile). Read from the route query
 * in App.tsx; the defaults are the current recommendation.
 */
export type StatusTone = 'colored' | 'neutral';

export interface Presentation {
  statusTone: StatusTone;
  /** Legacy `photos=demo` review switch; comparison no longer consumes it. */
  photoDemo: boolean;
}

export const PresentationContext = createContext<Presentation>({statusTone: 'colored', photoDemo: false});

export function usePresentation(): Presentation { return useContext(PresentationContext); }
