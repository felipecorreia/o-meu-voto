/**
 * The page-only pieces of the Comparar page in choice mode (Tela 1 of the web-next redesign):
 * hero, unified search, "fora da urna" chip, load-more, filtered empty state and page footer.
 * The pieces the next screens reuse (state pill, sliding tabs, candidacy card, avatar, number
 * pill, tray) live in `components/cv/`; the data, the 2..4 rule and the API calls stay in
 * `pages/Compare.tsx`. Every colour comes through the `--cv-*` variables of the `.cv-page`
 * container (`cvTokens`, `themes/cde.ts`); no hex here.
 */
import type {ReactNode} from 'react';
import {Check, Search} from 'lucide-react';
import {MAX_MARKED, MIN_MARKED} from '../lib/marking';

export function PickHero() {
  return (
    <header className="pick-hero">
      <h1 className="pick-h1">Compare as candidaturas <span className="pick-mark">antes de votar</span></h1>
      <p className="pick-lead">Marque de {MIN_MARKED} a {MAX_MARKED} e veja, lado a lado, o que cada uma declarou ao TSE.</p>
    </header>
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
    </footer>
  );
}
