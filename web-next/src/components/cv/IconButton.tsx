/**
 * A round 44 px button with only an icon (Tela 2 spec, sections 0.1 and 5.1): share on the
 * action bar, swap or remove on a column header. `label` is the accessible name. With `href`
 * it is a link (the WhatsApp fallback of the share button). `variant="white"` is the white
 * button with the small shadow of spec 4.3 for a coloured background; `spin` turns the icon
 * 180 degrees while pressed (the swap button), not under reduced motion.
 */
import type {MouseEvent, ReactNode} from 'react';

export interface IconButtonProps {
  /** Accessible name ("Compartilhar comparação", "Trocar X pela próxima marcada"). */
  label: string;
  icon: ReactNode;
  onClick?: (event: MouseEvent<HTMLElement>) => void;
  href?: string;
  /** Grey `--cv-surface` (the default, on white) or white with a shadow (on a slot tint). */
  variant?: 'surface' | 'white';
  spin?: boolean;
}

export function IconButton({label, icon, onClick, href, variant = 'surface', spin = false}: IconButtonProps) {
  const className = ['cv-iconbtn', variant === 'white' ? 'cv-iconbtn-white' : '', spin ? 'cv-iconbtn-spin' : ''].filter(Boolean).join(' ');
  if (href) {
    return <a className={className} href={href} target="_blank" rel="noopener noreferrer" aria-label={label} onClick={onClick}>{icon}</a>;
  }
  return <button type="button" className={className} aria-label={label} onClick={onClick}>{icon}</button>;
}
