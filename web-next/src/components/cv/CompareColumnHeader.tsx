/**
 * The header of one comparison column (Tela 2 spec, section 5.4): a card on the light tint of
 * the candidacy's slot with the 44 px slot avatar, the swap button (pair mode) or the remove
 * button (three or four columns on a wide screen), the title-cased ballot name as a link to
 * the profile, the yellow number pill and the party acronym. The slot follows the candidacy's
 * position in the URL's `sq`, never the column (columns are in ballot order) and never the
 * party (ADR 0008). The parent keys the header by sq_candidato, so a column that changes
 * candidacy remounts and plays the enter animation (`cv-col-in`).
 */
import type {CSSProperties} from 'react';
import {ArrowLeftRight, ChevronRight, X} from 'lucide-react';
import type {CandidateListItem} from '../../api';
import {slotColor, type Slot} from '../../lib/slotColor';
import {toTitleCase} from '../../lib/titleCase';
import {href} from '../../router';
import {CvAvatar} from './CvAvatar';
import {IconButton} from './IconButton';
import {NumberPill} from './NumberPill';

export type ColumnCandidacy = Pick<CandidateListItem, 'sq_candidato' | 'ballot_name' | 'number' | 'party' | 'photo_url'>;

export type ColumnAction =
  /** Pair mode: bring the next candidacy off screen into this column. */
  | {kind: 'swap'; onClick: () => void}
  /** Wide screen with more than two columns: redo the comparison without this candidacy. */
  | {kind: 'remove'; onClick: () => void};

export interface CompareColumnHeaderProps {
  c: ColumnCandidacy;
  slot: Slot;
  action?: ColumnAction | null;
}

export function CompareColumnHeader({c, slot, action}: CompareColumnHeaderProps) {
  const name = toTitleCase(c.ballot_name);
  const style = {'--cv-slot-tint': slotColor(slot).tint} as CSSProperties;
  return (
    <div className="cv-colhead cv-col-in" style={style} data-slot={slot}>
      <div className="cv-colhead-top">
        <CvAvatar name={c.ballot_name} photoUrl={c.photo_url} size={44} slot={slot} initialsSize={15} />
        {action?.kind === 'swap' ? <IconButton variant="white" spin label={`Trocar ${name} pela próxima marcada`} icon={<ArrowLeftRight size={18} aria-hidden />} onClick={action.onClick} /> : null}
        {action?.kind === 'remove' ? <IconButton variant="white" label={`Tirar ${name} da comparação`} icon={<X size={18} aria-hidden />} onClick={action.onClick} /> : null}
      </div>
      <a className="cv-colhead-name" href={href(`/candidato/${c.sq_candidato}`)}>
        <span>{name}</span>
        <ChevronRight size={16} strokeWidth={2.2} aria-hidden />
        <span className="sr-only">, ver ficha</span>
      </a>
      <span className="cv-colhead-party">
        <NumberPill n={c.number} />
        <span>{c.party.acronym}</span>
      </span>
    </div>
  );
}
