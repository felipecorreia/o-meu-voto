import {useEffect, useId, useRef, useState, type Ref} from 'react';
import {MapPin} from 'lucide-react';
import type {MunicipalityMatch} from '../../api';
import {toTitleCase} from '../../lib/titleCase';

type Status = 'idle' | 'loading' | 'empty' | 'error';

export function ComboField({label, value, onInput, options, onPick, emptyText = 'Nenhum município com esse nome.', status = 'idle', selected = false, inputRef}: {
  label: string; value: string; onInput: (value: string) => void; options: MunicipalityMatch[];
  onPick: (option: MunicipalityMatch) => void; emptyText?: string; status?: Status; selected?: boolean; inputRef?: Ref<HTMLInputElement>;
}) {
  const id = useId();
  const listId = `${id}-list`;
  const fieldRef = useRef<HTMLDivElement>(null);
  const [focused, setFocused] = useState(false);
  const [active, setActive] = useState(-1);
  const open = focused && !selected && value.trim().length >= 2;

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (!fieldRef.current?.contains(event.target as Node)) setFocused(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, []);
  useEffect(() => setActive(-1), [options]);

  return <div ref={fieldRef} className="cv-combofield">
    <label className="cv-insetfield-box">
      <span>{label}</span>
      <input ref={inputRef} value={value} onChange={event => {onInput(event.target.value); setFocused(true); setActive(-1);}}
        onFocus={() => setFocused(true)} onKeyDown={event => {
          if (event.key === 'Escape') { setFocused(false); return; }
          if (!open || !options.length) return;
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            setActive(i => event.key === 'ArrowDown' ? (i + 1) % options.length : (i - 1 + options.length) % options.length);
          } else if (event.key === 'Enter' && active >= 0) {
            event.preventDefault(); onPick(options[active]); setFocused(false);
          }
        }}
        role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls={open ? listId : undefined}
        aria-activedescendant={open && active >= 0 ? `${id}-option-${active}` : undefined}
        autoComplete="off" inputMode="text" placeholder="Digite 2 letras ou mais" />
    </label>
    {open ? <div id={listId} className="cv-combofield-list" role="listbox">
      {status === 'loading' ? <span className="cv-combofield-message">Buscando municípios…</span> : null}
      {status === 'error' ? <span className="cv-combofield-message">Não foi possível buscar municípios agora.</span> : null}
      {status === 'empty' ? <span className="cv-combofield-message">{emptyText}</span> : null}
      {status === 'idle' ? options.slice(0, 8).map((option, i) => <button key={option.tse_code} id={`${id}-option-${i}`} type="button" role="option"
        aria-selected={i === active} className={i === active ? 'cv-combofield-option active' : 'cv-combofield-option'}
        onMouseDown={event => event.preventDefault()} onClick={() => {onPick(option); setFocused(false);}}>
        <MapPin size={18} aria-hidden /><span>{toTitleCase(option.name)} <span>({option.uf})</span></span>
      </button>) : null}
    </div> : null}
    <span className="cv-sr-only" role="status" aria-live="polite">
      {open && status === 'idle' ? `${options.length} ${options.length === 1 ? 'município encontrado' : 'municípios encontrados'}` : open && status === 'loading' ? 'Buscando municípios…' : ''}
    </span>
  </div>;
}
