/**
 * The pieces of the Comparar page in choice mode (Tela 1 of the web-next redesign): hero, state
 * pill, office tabs with the sliding highlight, unified search, "fora da urna" chip, candidacy
 * card, load-more, filtered empty state, page footer and the floating tray. Presentation only:
 * the data, the 2..4 rule and the API calls stay in `pages/Compare.tsx`.
 *
 * Every colour comes through the `--cv-*` variables `ComparePage` sets from `pickTokens`
 * (`themes/cde.ts`); no hex here. The tray avatar colour follows the order of marking, never
 * the candidacy or the party (ADR 0008).
 */
import {useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode} from 'react';
import {Selector} from '@astryxdesign/core/Selector';
import {ArrowRight, Check, ChevronDown, MapPin, Search, ShieldCheck} from 'lucide-react';
import type {CandidateListItem} from '../api';
import {initials, sentenceCase, toTitleCase} from '../format';
import {OFFICE_SHORT, UFS, ufName, type Office} from '../labels';

export const MIN_MARKED = 2;
export const MAX_MARKED = 4;

export const UF_OPTIONS = [{value: 'BR', label: 'Brasil (presidente)'}, ...UFS.map(([v, l]) => ({value: v, label: `${v} · ${l}`}))];

export function PickHero() {
  return (
    <header className="pick-hero">
      <h1 className="pick-h1">Compare as candidaturas <span className="pick-mark">antes de votar</span></h1>
      <p className="pick-lead">Marque de {MIN_MARKED} a {MAX_MARKED} e veja, lado a lado, o que cada uma declarou ao TSE.</p>
    </header>
  );
}

/** The state pill IS the Astryx Selector (search, `presentation="adaptive"`: a bottom sheet on
 *  phones), restyled through the `.state-pill` wrapper in styles.css and drawing its own value
 *  (pin, label, UF name, yellow chevron) through `renderValue`; the Selector's own chevron is
 *  hidden by CSS. So the trigger keeps its combobox semantics and focus management and the
 *  bottom sheet is the existing one, not a rewrite. `aria-label` reaches the trigger button. */
export function StatePill({uf, onChange}: {uf: string; onChange: (uf: string) => void}) {
  const name = ufName(uf);
  return (
    <div className="state-pill">
      <Selector
        label="Estado" isLabelHidden options={UF_OPTIONS} value={uf} onChange={onChange}
        hasSearch searchPlaceholder="Buscar UF" presentation="adaptive" width="100%"
        aria-label={`Estado: ${name}. Trocar estado`}
        renderValue={() => (
          <span className="state-pill-value">
            <span className="state-pill-pin" aria-hidden><MapPin size={20} /></span>
            <span className="state-pill-text">
              <span className="state-pill-label">Estado</span>
              <span className="state-pill-name">{name}</span>
            </span>
            <span className="state-pill-chevron" aria-hidden><ChevronDown size={18} strokeWidth={2.2} /></span>
          </span>
        )}
      />
    </div>
  );
}

/** Office tabs on a rail: a radiogroup (a choice of value, not of panel) whose white highlight
 *  slides to the checked button. `left`/`width` are measured from the checked button and
 *  re-measured on resize, when the options change and when the font finishes loading. The rail
 *  scrolls sideways when the labels do not fit; ←/→ (and ↑/↓, Home, End) move the choice. */
export function OfficeTabs({options, value, onChange}: {options: Office[]; value: Office; onChange: (o: Office) => void}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [highlight, setHighlight] = useState<{left: number; width: number} | null>(null);
  const userPicked = useRef(false);

  const measure = useCallback(() => {
    const active = trackRef.current?.querySelector<HTMLButtonElement>('[role="radio"][aria-checked="true"]');
    if (!active) { setHighlight(null); return; }
    setHighlight(prev => prev && prev.left === active.offsetLeft && prev.width === active.offsetWidth ? prev : {left: active.offsetLeft, width: active.offsetWidth});
  }, []);

  useLayoutEffect(measure, [measure, value, options]);
  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    const ro = new ResizeObserver(measure);
    ro.observe(track);
    for (const b of track.querySelectorAll('button')) ro.observe(b);
    window.addEventListener('resize', measure);
    void document.fonts?.ready.then(measure);
    return () => { ro.disconnect(); window.removeEventListener('resize', measure); };
  }, [measure, options]);

  // A tab activated while partly off the rail scrolls into view; not on mount, only after a pick.
  useEffect(() => {
    if (!userPicked.current) return;
    const active = trackRef.current?.querySelector<HTMLButtonElement>('[role="radio"][aria-checked="true"]');
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    active?.scrollIntoView({inline: 'nearest', block: 'nearest', behavior: reduced ? 'auto' : 'smooth'});
  }, [value]);

  const pick = (o: Office, focus = false) => {
    userPicked.current = true;
    if (o !== value) onChange(o);
    if (focus) trackRef.current?.querySelector<HTMLButtonElement>(`[data-office="${o}"]`)?.focus();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = options.indexOf(value);
    let next: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (i + 1) % options.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (i - 1 + options.length) % options.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = options.length - 1;
    if (next === null) return;
    e.preventDefault();
    pick(options[next], true);
  };

  return (
    <div className="office-scroll">
      <div ref={trackRef} className="office-track" role="radiogroup" aria-label="Cargo" onKeyDown={onKeyDown}>
        {highlight ? <span className="office-hl" aria-hidden style={{left: highlight.left, width: highlight.width}} /> : null}
        {options.map(o => (
          <button key={o} type="button" role="radio" aria-checked={o === value} tabIndex={o === value ? 0 : -1} data-office={o} className="office-tab" onClick={() => pick(o)}>
            {OFFICE_SHORT[o]}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SearchField({value, onChange}: {value: string; onChange: (v: string) => void}) {
  return (
    <label className="search">
      <Search size={18} aria-hidden />
      <input type="search" name="q" value={value} onChange={e => onChange(e.target.value)} placeholder="Nome, partido ou número"
        aria-label="Buscar por nome, partido ou número" autoComplete="off" autoCorrect="off" autoCapitalize="off" spellCheck={false} enterKeyHint="search" />
    </label>
  );
}

export function OffBallotChip({on, onChange}: {on: boolean; onChange: (v: boolean) => void}) {
  return (
    <button type="button" className="chip-toggle" aria-pressed={on} onClick={() => onChange(!on)}>
      <Check size={14} strokeWidth={2.4} aria-hidden />
      Incluir fora da urna
    </button>
  );
}

function CardAvatar({c}: {c: Pick<CandidateListItem, 'ballot_name' | 'photo_url'>}) {
  const [failed, setFailed] = useState(false);
  const src = failed ? null : c.photo_url;
  return (
    <span className="cand-avatar" aria-hidden>
      {src ? <img src={src} alt="" loading="lazy" width={52} height={52} onError={() => setFailed(true)} /> : initials(c.ballot_name)}
    </span>
  );
}

/** One candidacy: a whole-card `<button aria-pressed>` (avatar, title-cased ballot name, number
 *  pill, party and occupation, the green check). `badges` carries the registration badges of
 *  the candidacies not simply DEFERIDO and on the ballot (status colours, never party colours).
 *  The accessible name keeps the upper-case ballot name and names those statuses too. */
export function CandidateCard({c, on, disabled, onToggle, badges}: {c: CandidateListItem; on: boolean; disabled: boolean; onToggle: () => void; badges?: ReactNode}) {
  const status = c.adjudication_status.toUpperCase() === 'DEFERIDO' ? '' : `, ${c.adjudication_status.toLowerCase()}`;
  const label = `${c.ballot_name}, número ${c.number}, ${c.party.acronym}${c.on_ballot ? '' : ', fora da urna'}${status}`;
  return (
    <button type="button" className="cand" aria-pressed={on} aria-label={label} disabled={disabled} onClick={onToggle}>
      <CardAvatar c={c} />
      <span className="cand-body">
        <span className="cand-line1">
          <span className="cand-name">{toTitleCase(c.ballot_name)}</span>
          <span className="cand-num">{c.number}</span>
        </span>
        <span className="cand-line2">{c.party.acronym}{c.occupation ? ` · ${sentenceCase(c.occupation)}` : ''}</span>
        {badges ? <span className="cand-badges">{badges}</span> : null}
      </span>
      <span className="cand-chk" aria-hidden><Check size={16} strokeWidth={2.6} /></span>
    </button>
  );
}

export function LoadMore({shown, total, loading, onClick}: {shown: number; total: number; loading: boolean; onClick: () => void}) {
  return (
    <button type="button" className="pick-more" disabled={loading} aria-busy={loading || undefined} onClick={onClick}>
      {loading ? 'Carregando…' : `Carregar mais (${shown} de ${total})`}
    </button>
  );
}

export function FilteredEmpty({onClear}: {onClear: () => void}) {
  return (
    <div className="pick-empty" role="status">
      <span className="pick-empty-title">Nenhuma candidatura com esse filtro</span>
      <span className="pick-empty-text">Confira o nome ou tente pelo número de urna.</span>
      <button type="button" className="pick-clear" onClick={onClear}>Limpar busca</button>
    </div>
  );
}

export function PickFooter({children}: {children?: ReactNode}) {
  return (
    <footer className="pick-foot">
      {children}
      <span className="pick-indep">
        <ShieldCheck size={16} aria-hidden />
        <span>Projeto independente, não oficial. Sem cadastro, sem CPF, sem título: nada é guardado.</span>
      </span>
    </footer>
  );
}

/** The floating tray: always on screen in choice mode, even with nothing marked. `marked` is in
 *  the order of marking, which is what the slot colours follow (`data-slot`). */
export function PickTray({marked, onRemove, onCompare}: {marked: CandidateListItem[]; onRemove: (sq: number) => void; onCompare: () => void}) {
  const n = marked.length;
  const title = n === 0 ? `Marque ${MIN_MARKED} para comparar` : n === 1 ? '1 marcada' : `${n} marcadas`;
  const sub = n === 0 ? 'Toque nos cards da lista' : n === 1 ? 'Falta mais 1' : n < MAX_MARKED ? `Cabem mais ${MAX_MARKED - n}` : `Limite de ${MAX_MARKED}`;
  return (
    <div className="pick-tray" role="region" aria-label="Candidaturas marcadas">
      {n ? (
        <span className="pick-tray-avs">
          {marked.map((c, i) => (
            <button key={c.sq_candidato} type="button" className="tray-av" data-slot={i} aria-label={`Tirar ${c.ballot_name} da comparação`} onClick={() => onRemove(c.sq_candidato)}>
              {initials(c.ballot_name)}
            </button>
          ))}
        </span>
      ) : null}
      <span className="pick-tray-text" aria-live="polite">
        <span className="pick-tray-title">{title}</span>
        <span className="pick-tray-sub">{sub}</span>
      </span>
      <button type="button" className="cta" disabled={n < MIN_MARKED} onClick={onCompare}>
        {n >= MIN_MARKED ? `Comparar ${n}` : 'Comparar'}
        <ArrowRight size={18} strokeWidth={2.2} aria-hidden />
      </button>
    </div>
  );
}
