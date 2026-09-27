import {Pencil, Search} from 'lucide-react';

export function SearchSummaryPill({zone, section, state, round, onEdit}: {zone: string; section: string; state: string; round: string; onEdit: () => void}) {
  const title = `Zona ${zone} · Seção ${section}`;
  const caption = `${state} · ${round}`;
  return <button type="button" className="cv-summary cv-pill-value" aria-label={`Editar busca: ${title}, ${caption}`} onClick={onEdit}>
    <span className="cv-pill-pin" aria-hidden><Search size={20} /></span>
    <span className="cv-pill-text"><span className="cv-pill-name">{title}</span><span className="cv-pill-label">{caption}</span></span>
    <span className="cv-pill-chevron" aria-hidden><Pencil size={18} strokeWidth={2.2} /></span>
  </button>;
}
