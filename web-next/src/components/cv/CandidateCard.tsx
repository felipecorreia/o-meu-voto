/**
 * One candidacy as a whole-card `<button aria-pressed>` (Tela 1 spec, section 5.6): avatar,
 * title-cased ballot name, number pill, party and occupation, the animated green check. `badges`
 * carries the registration badges of the candidacies not simply DEFERIDO and on the ballot
 * (status colours, never party colours). The accessible name keeps the upper-case ballot name
 * and names those statuses too.
 */
import type {ReactNode} from 'react';
import {Check} from 'lucide-react';
import type {CandidateListItem} from '../../api';
import {sentenceCase} from '../../format';
import {toTitleCase} from '../../lib/titleCase';
import {CvAvatar} from './CvAvatar';
import {NumberPill} from './NumberPill';

export interface CandidateCardProps {
  c: CandidateListItem;
  /** Marked. */
  on: boolean;
  /** Four already marked and this one is not among them. */
  disabled: boolean;
  onToggle: () => void;
  badges?: ReactNode;
}

export function CandidateCard({c, on, disabled, onToggle, badges}: CandidateCardProps) {
  const status = c.adjudication_status.toUpperCase() === 'DEFERIDO' ? '' : `, ${c.adjudication_status.toLowerCase()}`;
  const label = `${c.ballot_name}, número ${c.number}, ${c.party.acronym}${c.on_ballot ? '' : ', fora da urna'}${status}`;
  return (
    <button type="button" className="cv-card" aria-pressed={on} aria-label={label} disabled={disabled} onClick={onToggle}>
      <CvAvatar name={c.ballot_name} photoUrl={c.photo_url} size={52} />
      <span className="cv-card-body">
        <span className="cv-card-line1">
          <span className="cv-card-name">{toTitleCase(c.ballot_name)}</span>
          <NumberPill n={c.number} />
        </span>
        <span className="cv-card-line2">{c.party.acronym}{c.occupation ? ` · ${sentenceCase(c.occupation)}` : ''}</span>
        {badges ? <span className="cv-card-badges">{badges}</span> : null}
      </span>
      <span className="cv-card-chk" aria-hidden><Check size={16} strokeWidth={2.6} /></span>
    </button>
  );
}
