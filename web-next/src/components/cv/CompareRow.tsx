/**
 * One attribute of the comparison (Tela 2 spec, section 5.6): the label with its hint (and
 * the yellow "Em preparação" tag of a row the service does not serve yet), then one cell per
 * column on the same grid as the column headers (`--cv-n` columns, set by the page; from
 * 1024 px the label takes a 220 px column of its own), or one full-width note on
 * `--cv-surface-2` instead of cells. A cell is data, not markup: an ordered list of parts
 * (neutral badge, main value, secondary text, link pills), so every row renders the same way
 * and the cell's `aria-label` ("{Nome}: {valor}") is the same text a sighted reader sees.
 * Cells are top-aligned and wrap anywhere; nothing is cut.
 */
import {useState, type ReactNode} from 'react';

export interface CompareLink {
  key: string;
  label: string;
  /** Null when the value is not a URL: shown as text, not as a pill. */
  href: string | null;
  icon?: ReactNode;
}

export type CellPart =
  | {kind: 'badge'; text: string}
  | {kind: 'main'; text: string; big?: boolean; muted?: boolean}
  | {kind: 'sub'; text: string}
  | {kind: 'links'; links: CompareLink[]; max: number};

export interface CompareCell {
  /** The column's candidacy, by sq_candidato: the parent keys the cell by it. */
  key: number;
  /** The candidacy's name, for the cell's accessible name. */
  who: string;
  parts: CellPart[];
}

export interface CompareRowProps {
  id: string;
  label: string;
  hint?: string;
  tag?: string;
  cells?: CompareCell[];
  /** One note across every column instead of cells. */
  full?: string;
}

const moreLabel = (n: number) => `+${n} redes`;

function LinkPills({links, max}: {links: CompareLink[]; max: number}) {
  const [open, setOpen] = useState(false);
  const shown = open ? links : links.slice(0, max);
  const hidden = links.length - shown.length;
  return (
    <span className="cv-cell-links">
      {shown.map(l => l.href
        ? <a key={l.key} className="cv-linkpill" href={l.href} target="_blank" rel="noopener noreferrer"><span>{l.label}</span>{l.icon}</a>
        : <span key={l.key} className="cv-cell-sub">{l.label}</span>)}
      {hidden > 0 ? <button type="button" className="cv-linkpill cv-linkmore" onClick={() => setOpen(true)}>{moreLabel(hidden)}</button> : null}
      {open && links.length > max ? <button type="button" className="cv-linkpill cv-linkmore" onClick={() => setOpen(false)}>Mostrar menos</button> : null}
    </span>
  );
}

function partText(p: CellPart): string {
  return p.kind === 'links' ? p.links.map(l => l.label).join(', ') : p.text;
}

export function cellText(cell: CompareCell): string {
  return `${cell.who}: ${cell.parts.map(partText).filter(Boolean).join(', ')}`;
}

function Part({p}: {p: CellPart}) {
  switch (p.kind) {
    case 'badge': return <span className="cv-cell-badge">{p.text}</span>;
    case 'main': return <span className={['cv-cell-main', p.big ? 'cv-cell-main-big' : '', p.muted ? 'cv-cell-main-muted' : ''].filter(Boolean).join(' ')}>{p.text}</span>;
    case 'sub': return <span className="cv-cell-sub">{p.text}</span>;
    case 'links': return <LinkPills links={p.links} max={p.max} />;
  }
}

export function CompareRow({id, label, hint, tag, cells, full}: CompareRowProps) {
  const labelId = `cv-row-${id}`;
  return (
    <div className="cv-row" role="group" aria-labelledby={labelId}>
      <div className="cv-row-label">
        <span className="cv-row-label-line">
          <span id={labelId} className="cv-row-label-text">{label}</span>
          {tag ? <span className="cv-row-tag">{tag}</span> : null}
        </span>
        {hint ? <span className="cv-row-hint">{hint}</span> : null}
      </div>
      {full !== undefined
        ? <p className="cv-row-full">{full}</p>
        : cells?.map(cell => (
          <div key={cell.key} className="cv-cell cv-col-in" role="group" aria-label={cellText(cell)}>
            {cell.parts.map((p, i) => <Part key={i} p={p} />)}
          </div>
        ))}
    </div>
  );
}
