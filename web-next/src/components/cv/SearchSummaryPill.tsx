import {Pencil, Search} from 'lucide-react';

type Props = ({zone: string; section: string; state: string; round: string} | {title: string; caption: string}) & {onEdit: () => void};

export function SearchSummaryPill(props: Props) {
  const {onEdit} = props;
  const title = 'title' in props ? props.title : `Zona ${props.zone} · Seção ${props.section}`;
  const caption = 'caption' in props ? props.caption : `${props.state} · ${props.round}`;
  return <button type="button" className="cv-summary cv-pill-value" aria-label={`Editar busca: ${title}, ${caption}`} onClick={onEdit}>
    <span className="cv-pill-pin" aria-hidden><Search size={20} /></span>
    <span className="cv-pill-text"><span className="cv-pill-name">{title}</span><span className="cv-pill-label">{caption}</span></span>
    <span className="cv-pill-chevron" aria-hidden><Pencil size={18} strokeWidth={2.2} /></span>
  </button>;
}
