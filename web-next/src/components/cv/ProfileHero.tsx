import type {CSSProperties, ReactNode} from 'react';
import type {CandidateProfile} from '../../api';
import {slotColor, type Slot} from '../../lib/slotColor';
import {toTitleCase} from '../../lib/titleCase';
import {CvAvatar} from './CvAvatar';
import {NumberPill} from './NumberPill';
import {StatusBadge} from './StatusBadge';

export function ProfileHero({candidate: c, slot, office, place, action}: {candidate: CandidateProfile; slot?: Slot; office: string; place: string; action: ReactNode}) {
  const style: CSSProperties = {background: slot ? slotColor(slot).tint : 'var(--cv-surface-2)'};
  return <header className="cv-profilehero" style={style} data-slot={slot}>
    <CvAvatar key={c.sq_candidato} name={c.ballot_name} photoUrl={c.photo_url} size={96} initialsSize={32} slot={slot} />
    <div className="cv-profilehero-body">
      <h1>{toTitleCase(c.ballot_name)}</h1>
      <div className="cv-profilehero-party"><NumberPill n={c.number} /><span>{c.party.acronym}</span></div>
      <span className="cv-profilehero-race">{[office, place, `${c.round}º turno`].filter(Boolean).join(' · ')}</span>
      <div className="cv-profilehero-badges"><StatusBadge status={c.adjudication_status} /><StatusBadge status={c.on_ballot ? 'Na urna' : 'Fora da urna'} kind="neutral" /></div>
      <div className="cv-profilehero-action">{action}</div>
    </div>
  </header>;
}
