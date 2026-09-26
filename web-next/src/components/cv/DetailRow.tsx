import type {ReactNode} from 'react';

/** A labelled detail with an optional secondary explanation, for detail screens. */
export function DetailRow({label, children, secondary}: {label: string; children: ReactNode; secondary?: ReactNode}) {
  return <div className="cv-detailrow" role="group" aria-label={label}>
    <span className="cv-detailrow-label">{label}</span>
    <div className="cv-detailrow-value">{children}</div>
    {secondary ? <div className="cv-detailrow-secondary">{secondary}</div> : null}
  </div>;
}
