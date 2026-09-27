import type {ReactNode, Ref} from 'react';
import {MapPin} from 'lucide-react';

export function PlaceHero({name, originalName = name, addressLine1, addressLine2, chips, headingRef, action}: {
  name: string; originalName?: string; addressLine1: ReactNode; addressLine2: ReactNode; chips: ReactNode; headingRef?: Ref<HTMLHeadingElement>; action?: ReactNode;
}) {
  return <section className="cv-placehero">
    <span className="cv-placehero-pin" aria-hidden><MapPin size={32} strokeWidth={1.9} /></span>
    <span className="cv-placehero-eyebrow">Seu local de votação</span>
    <h1 tabIndex={-1} ref={headingRef} aria-label={originalName}>{name}</h1>
    <div className="cv-placehero-address">{addressLine1}<br />{addressLine2}</div>
    <div className="cv-placehero-chips">{chips}</div>
    {action}
  </section>;
}
