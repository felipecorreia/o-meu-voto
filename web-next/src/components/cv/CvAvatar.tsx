/**
 * Avatar with initials or the candidate photo (Tela 1 spec, sections 5.6 and 5.10). With `slot`
 * it is painted with the colour of marking slot 1 to 4 (`lib/slotColor`): the colour follows the
 * order of marking, never the candidacy or the party (ADR 0008). Without it, the neutral avatar
 * of the candidacy card. Decorative: the control around it carries the accessible name.
 */
import {useState, type CSSProperties} from 'react';
import {initials} from '../../format';
import {slotColor, type Slot} from '../../lib/slotColor';

export interface CvAvatarProps {
  /** The ballot name; the initials are the first letters of its first two words. */
  name: string;
  photoUrl?: string | null;
  /** Diameter in px: 52 in the candidacy card, 36 in the tray. */
  size: number;
  /** Marking slot 1 to 4; paints the avatar with that slot's colours. */
  slot?: Slot;
  /** A 2.5 px white ring inside the diameter, for the overlapping avatars of the tray. */
  ring?: boolean;
  /** Font size of the initials; about a third of the diameter when omitted. */
  initialsSize?: number;
}

export function CvAvatar({name, photoUrl, size, slot, ring = false, initialsSize}: CvAvatarProps) {
  // A photo that fails to load (mirror gap, network) falls back to the initials.
  const [failed, setFailed] = useState(false);
  const src = failed ? null : photoUrl ?? null;
  const style: CSSProperties = {width: size, height: size, fontSize: initialsSize ?? Math.round(size * 0.31)};
  if (slot) { const c = slotColor(slot); style.background = c.bg; style.color = c.fg; }
  return (
    <span className={ring ? 'cv-avatar cv-avatar-ring' : 'cv-avatar'} style={style} data-slot={slot} aria-hidden>
      {src ? <img src={src} alt="" loading="lazy" width={size} height={size} onError={() => setFailed(true)} /> : initials(name)}
    </span>
  );
}
