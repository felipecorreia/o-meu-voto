/**
 * "Na tela: 2 de N" (Tela 2 spec, section 5.3): on phones with three or four candidacies, one
 * button per candidacy with the 48 px slot avatar, the short name and its state, "Coluna 1",
 * "Coluna 2" or "Trazer". A candidacy on screen has the slot colour as border, the slot tint
 * as background, the double ring on the avatar and `aria-pressed="true"`; tapping one off
 * screen brings it into the column changed least recently (`lib/pair`). The colour never is
 * the only signal: the state text and `aria-pressed` say the same.
 */
import type {CSSProperties} from 'react';
import type {CandidateListItem} from '../../api';
import type {Pair} from '../../lib/pair';
import {slotColor, type Slot} from '../../lib/slotColor';
import {shortName, toTitleCase} from '../../lib/titleCase';
import {CvAvatar} from './CvAvatar';

export interface PairPickerItem extends Pick<CandidateListItem, 'sq_candidato' | 'ballot_name' | 'photo_url'> { slot: Slot }

export interface PairPickerProps {
  /** The compared candidacies in ballot order. */
  items: readonly PairPickerItem[];
  /** The two on screen, left column first. */
  pair: Pair;
  onBring: (sq: number) => void;
}

export function PairPicker({items, pair, onBring}: PairPickerProps) {
  return (
    <section className="cv-pairpick" aria-label="Candidaturas na tela">
      <div className="cv-pairpick-head">
        <span className="cv-pairpick-title">Na tela: 2 de {items.length}</span>
        <span className="cv-pairpick-hint">Toque para trazer</span>
      </div>
      <div className="cv-pairpick-list">
        {items.map(it => {
          const column = pair.indexOf(it.sq_candidato);
          const on = column >= 0;
          const name = toTitleCase(it.ballot_name);
          const colour = slotColor(it.slot);
          const style = {'--cv-slot-color': colour.bg, '--cv-slot-tint': colour.tint} as CSSProperties;
          return (
            <button key={it.sq_candidato} type="button" className="cv-pairpick-item" style={style} aria-pressed={on}
              aria-label={on ? `${name} já está na tela` : `Trazer ${name} para a tela`} onClick={() => { if (!on) onBring(it.sq_candidato); }}>
              <CvAvatar name={it.ballot_name} photoUrl={it.photo_url} size={48} slot={it.slot} initialsSize={15} />
              <span className="cv-pairpick-name">{shortName(it.ballot_name)}</span>
              <span className="cv-pairpick-state">{on ? `Coluna ${column + 1}` : 'Trazer'}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
