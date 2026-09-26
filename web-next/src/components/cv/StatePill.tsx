/**
 * The state pill (Tela 1 spec, section 5.2) IS the Astryx Selector (search, `presentation=
 * "adaptive"`: a bottom sheet on phones), restyled through the `.cv-pill` wrapper in styles.css
 * and drawing its own value (pin, label, UF name, yellow chevron) through `renderValue`; the
 * Selector's own chevron is hidden by CSS. So the trigger keeps its combobox semantics and focus
 * management and the bottom sheet is the existing one, not a rewrite. `aria-label` reaches the
 * trigger button; `label` is the sheet's heading ("Escolha o estado", spec 5.11).
 */
import {Selector} from '@astryxdesign/core/Selector';
import {ChevronDown, MapPin} from 'lucide-react';
import {UFS, ufName} from '../../labels';

export const UF_OPTIONS = [{value: 'BR', label: 'Brasil (presidente)'}, ...UFS.map(([v, l]) => ({value: v, label: `${v} · ${l}`}))];

export function StatePill({uf, onChange}: {uf: string; onChange: (uf: string) => void}) {
  const name = ufName(uf);
  return (
    <div className="cv-pill">
      <Selector
        label="Escolha o estado" isLabelHidden options={UF_OPTIONS} value={uf} onChange={onChange}
        hasSearch searchPlaceholder="Buscar estado" presentation="adaptive" width="100%"
        aria-label={`Estado: ${name}. Trocar estado`}
        renderValue={() => (
          <span className="cv-pill-value">
            <span className="cv-pill-pin" aria-hidden><MapPin size={20} /></span>
            <span className="cv-pill-text">
              <span className="cv-pill-label">Estado</span>
              <span className="cv-pill-name">{name}</span>
            </span>
            <span className="cv-pill-chevron" aria-hidden><ChevronDown size={18} strokeWidth={2.2} /></span>
          </span>
        )}
      />
    </div>
  );
}
