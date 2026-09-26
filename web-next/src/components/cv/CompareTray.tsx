/**
 * The floating tray (Tela 1 spec, section 5.10): always on screen in choice mode, even with
 * nothing marked. `marked` is in the order of marking, which is what the avatar colours follow
 * (slot 1 to 4, `lib/slotColor`), and tapping an avatar unmarks. The CTA is disabled under
 * `MIN_MARKED`.
 */
import {ArrowRight} from 'lucide-react';
import type {CandidateListItem} from '../../api';
import {MAX_MARKED, MIN_MARKED} from '../../lib/marking';
import type {Slot} from '../../lib/slotColor';
import {CvAvatar} from './CvAvatar';

export type TrayCandidacy = Pick<CandidateListItem, 'sq_candidato' | 'ballot_name'>;

export interface CompareTrayProps {
  marked: readonly TrayCandidacy[];
  onRemove: (sq: number) => void;
  onCompare: () => void;
}

export function CompareTray({marked, onRemove, onCompare}: CompareTrayProps) {
  const n = marked.length;
  const title = n === 0 ? `Marque ${MIN_MARKED} para comparar` : n === 1 ? '1 marcada' : `${n} marcadas`;
  const sub = n === 0 ? 'Toque nos cards da lista' : n === 1 ? 'Falta mais 1' : n < MAX_MARKED ? `Cabem mais ${MAX_MARKED - n}` : `Limite de ${MAX_MARKED}`;
  return (
    <div className="cv-tray" role="region" aria-label="Candidaturas marcadas">
      {n ? (
        <span className="cv-tray-avs">
          {marked.map((c, i) => (
            <button key={c.sq_candidato} type="button" className="cv-tray-av" aria-label={`Tirar ${c.ballot_name} da comparação`} onClick={() => onRemove(c.sq_candidato)}>
              <CvAvatar name={c.ballot_name} size={36} slot={(i + 1) as Slot} ring initialsSize={13} />
            </button>
          ))}
        </span>
      ) : null}
      <span className="cv-tray-text" aria-live="polite">
        <span className="cv-tray-title">{title}</span>
        <span className="cv-tray-sub">{sub}</span>
      </span>
      <button type="button" className="cv-tray-cta" disabled={n < MIN_MARKED} onClick={onCompare}>
        {n >= MIN_MARKED ? `Comparar ${n}` : 'Comparar'}
        <ArrowRight size={18} strokeWidth={2.2} aria-hidden />
      </button>
    </div>
  );
}
