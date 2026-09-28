import {useId, type ComponentPropsWithoutRef, type Ref} from 'react';

export function InsetField({label, optional = false, value, onChange, placeholder, error, inputMode = 'numeric', inputRef}: {
  label: string; value: string; onChange: (value: string) => void; placeholder: string; error?: string;
  inputMode?: ComponentPropsWithoutRef<'input'>['inputMode']; inputRef?: Ref<HTMLInputElement>; optional?: boolean;
}) {
  const id = useId();
  return <div className="cv-insetfield">
    <label className={`cv-insetfield-box${error ? ' cv-insetfield-invalid' : ''}`}>
      <span>{label}{optional ? <> <span className="cv-field-optional">(opcional)</span></> : null}</span>
      <input ref={inputRef} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        inputMode={inputMode} autoComplete="off" aria-invalid={error ? true : undefined} aria-describedby={error ? id : undefined} />
    </label>
    {error ? <span id={id} className="cv-insetfield-error">{error}</span> : null}
  </div>;
}
