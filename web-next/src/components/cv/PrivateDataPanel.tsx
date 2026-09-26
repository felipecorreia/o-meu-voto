import {useId, useState} from 'react';
import {ChevronDown, Lock} from 'lucide-react';
import type {CandidateProfile} from '../../api';

/** Closed on every new profile; personal fields are mounted only while expanded. */
export function PrivateDataPanel({candidate: c}: {candidate: Pick<CandidateProfile, 'gender' | 'race_color' | 'marital_status' | 'education'>}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const fields = [['Gênero', c.gender], ['Cor/raça', c.race_color], ['Estado civil', c.marital_status], ['Escolaridade', c.education]];
  return <section className="cv-private">
    <button className="cv-private-toggle" type="button" id={`${id}-toggle`} aria-expanded={open} aria-controls={`${id}-data`} onClick={() => setOpen(v => !v)}>
      <span className="cv-private-icon"><Lock size={20} aria-hidden /></span>
      <span className="cv-private-heading"><span className="cv-private-title">Dados pessoais declarados ao TSE</span><span className="cv-private-caption">Aparecem só nesta ficha. Nunca entram na lista nem na comparação.</span></span>
      <ChevronDown className="cv-private-chevron" size={20} strokeWidth={2.2} aria-hidden />
    </button>
    <div id={`${id}-data`} role="region" aria-labelledby={`${id}-toggle`} hidden={!open}>
      {open ? <div className="cv-private-grid">{fields.map(([label, value]) => <div key={label} className="cv-private-field"><span>{label}</span><strong>{value || 'Não informado'}</strong></div>)}</div> : null}
    </div>
  </section>;
}
