// Brand glyphs lucide-react no longer ships (removed upstream). Paths are the Lucide brand
// icons the old static page embedded (ISC, https://lucide.dev); X and TikTok are
// simple outlines drawn here. All decorative: the visible handle is the accessible text.
import type {SVGProps} from 'react';
type P = SVGProps<SVGSVGElement> & {size?: number};
const base = (size = 16): SVGProps<SVGSVGElement> => ({width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true});
export const Instagram = ({size, ...p}: P) => <svg {...base(size)} {...p}><rect width="20" height="20" x="2" y="2" rx="5" ry="5" /><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" /><line x1="17.5" x2="17.51" y1="6.5" y2="6.5" /></svg>;
export const Facebook = ({size, ...p}: P) => <svg {...base(size)} {...p}><path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" /></svg>;
export const XBrand = ({size, ...p}: P) => <svg {...base(size)} {...p}><path d="M4 4l16 16" /><path d="M20 4L4 20" /></svg>;
export const Youtube = ({size, ...p}: P) => <svg {...base(size)} {...p}><path d="M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17" /><path d="m10 15 5-3-5-3z" /></svg>;
export const Tiktok = ({size, ...p}: P) => <svg {...base(size)} {...p}><path d="M9 18V5l12-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="18" cy="16" r="3" /></svg>;
