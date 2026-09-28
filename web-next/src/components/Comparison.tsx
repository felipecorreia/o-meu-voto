/**
 * The page-only pieces of the Comparar page in comparison mode (Tela 2 of the web-next
 * redesign): the sticky action bar, the title, the notice of the candidacies left out, the
 * sticky block of column headers and tabs, the rows of each tab, the guardrails note, the
 * footers and the loading and problem states. The pieces the next screens reuse
 * (`CompareColumnHeader`, `PairPicker`, `CompareRow`, `IconButton`, and Tela 1's `SlidingTabs`,
 * `CvAvatar`, `NumberPill`) live in `components/cv/`; the pair rules in `lib/pair`; the data,
 * the URL state and the API calls stay in `pages/Compare.tsx`. Every colour comes through the
 * `--cv-*` variables of the `.cv-page` container (`cvTokens`, `themes/cde.ts`); no hex here.
 * Problem and missing-candidacy notices use spec section 5.11 and the approved fallback for
 * a missing profile; `not_found.reason` only selects a phrase, and the service's `guidance`
 * and HTTP details never reach the screen.
 */
import {useLayoutEffect, useMemo, useRef, useState, type CSSProperties} from 'react';
import {AtSign, ChevronLeft, ExternalLink as ExternalIcon, Info, Link2, Share, ShieldCheck} from 'lucide-react';
import type {ComparedCandidate, ElectionInfo, MissingCandidacy, Source} from '../api';
import {brl, brlFull, normalizeSocialUrl, sentenceCase, socialNetwork} from '../format';
import {NOMINATION, OFFICE, ufName, type Office} from '../labels';
import {bringIn, resolvePair, swapNext, type Column, type Pair, type PairState} from '../lib/pair';
import {slotOf} from '../lib/marking';
import {slotColor} from '../lib/slotColor';
import {toTitleCase} from '../lib/titleCase';
import {useMedia} from '../lib/useMedia';
import {href} from '../router';
import {Facebook, Instagram, Tiktok, XBrand, Youtube} from './brandIcons';
import {SourceFooter} from './common';
import {CompareColumnHeader} from './cv/CompareColumnHeader';
import {CompareRow, type CellPart, type CompareCell, type CompareLink, type CompareRowProps} from './cv/CompareRow';
import {IconButton} from './cv/IconButton';
import {PairPicker} from './cv/PairPicker';
import {SlidingTabs} from './cv/SlidingTabs';

// ---- Tabs and rows ---------------------------------------------------------------------------

export const COMPARE_TABS = [
  {value: 'chapa', label: 'Chapa'},
  {value: 'patrimonio', label: 'Patrimônio'},
  {value: 'ocupacao', label: 'Ocupação'},
] as const;
export type CompareTab = typeof COMPARE_TABS[number]['value'];
export const DEFAULT_TAB: CompareTab = 'chapa';
export function isCompareTab(v: string | null | undefined): v is CompareTab {
  return COMPARE_TABS.some(t => t.value === v);
}

const NOT_INFORMED = 'Não informado pelo TSE';
/** Social pills before "+N redes": three on phones, six from 1024 px (spec 5.6 and 5.12). */
const LINKS_PHONE = 3;
const LINKS_WIDE = 6;

const NET_ICON = {instagram: Instagram, facebook: Facebook, x: XBrand, youtube: Youtube, tiktok: Tiktok, kwai: Tiktok, threads: AtSign, site: Link2} as const;

/** The declared networks as link pills: normalised once, exact duplicates of the TSE file
 *  dropped, TSE order kept; a value that is not a URL stays text. */
function socialPills(links: string[]): CompareLink[] {
  const out: CompareLink[] = [];
  const seen = new Set<string>();
  for (const raw of links) {
    const n = normalizeSocialUrl(raw);
    const key = n.href ?? n.label;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    const Icon = n.href ? NET_ICON[socialNetwork(n.href)] : null;
    out.push({key, href: n.href, label: n.label, icon: Icon ? <Icon size={14} aria-hidden /> : undefined});
  }
  return out;
}

const cell = (c: ComparedCandidate, parts: CellPart[]): CompareCell => ({key: c.sq_candidato, who: toTitleCase(c.ballot_name), parts});
const main = (text: string, extra: Partial<Extract<CellPart, {kind: 'main'}>> = {}): CellPart => ({kind: 'main', text, ...extra});
const sub = (text: string): CellPart => ({kind: 'sub', text});
const badge = (text: string): CellPart => ({kind: 'badge', text});

function nominationParts(c: ComparedCandidate): CellPart[] {
  if (c.coalition && c.federation) return [
    badge('Coligação'), main(c.coalition.name), ...(c.coalition.composition ? [sub(c.coalition.composition)] : []),
    badge('Federação'), main(c.federation.name), ...(c.federation.composition ? [sub(c.federation.composition)] : []),
  ];
  const parts: CellPart[] = [badge(NOMINATION[c.nomination_kind] ?? sentenceCase(c.nomination_kind.replace(/_/g, ' ')))];
  if (c.coalition) {
    parts.push(main(c.coalition.name));
    if (c.coalition.composition) parts.push(sub(c.coalition.composition));
  } else if (c.federation) {
    parts.push(main(c.federation.name));
    if (c.federation.composition) parts.push(sub(c.federation.composition));
  } else {
    parts.push(main(c.party.name));
  }
  return parts;
}

function matesParts(c: ComparedCandidate): CellPart[] {
  if (!c.running_mates.length) return [main('Não se aplica', {muted: true})];
  return c.running_mates.flatMap(m => [
    main(toTitleCase(m.ballot_name)),
    sub(`${m.party.acronym} · ${(OFFICE[m.office as Office] ?? m.office).toLocaleLowerCase('pt-BR')}`),
  ]);
}

function assetsParts(c: ComparedCandidate): CellPart[] {
  const a = c.assets;
  if (a.state === 'declarou_nao_possuir') return [main('Declarou não possuir bens')];
  if (a.state === 'sem_informacao' || a.total == null) return [main('Sem informação de bens no TSE', {muted: true})];
  return [main(brl(a.total), {big: true}), sub(`${brlFull(a.total)} · como declarado ao TSE`)];
}

/**
 * The rows of one tab for the columns on screen (spec 5.6): the field set of ADR 0008
 * (codebase-design 8.7), never gender, race/colour, marital status or education; nothing
 * sorted, scored or coloured by value. `linksMax` is the number of social pills before
 * "+N redes".
 */
export function rowsFor(tab: CompareTab, shown: readonly ComparedCandidate[], linksMax: number): CompareRowProps[] {
  const each = (f: (c: ComparedCandidate) => CellPart[]) => shown.map(c => cell(c, f(c)));
  switch (tab) {
    case 'chapa': return [
      {id: 'name', label: 'Nome civil', cells: each(c => [main(c.name), ...(c.social_name ? [sub(`Nome social: ${c.social_name}`)] : [])])},
      {id: 'party', label: 'Partido', cells: each(c => [main(`${c.party.acronym} · ${c.party.number}`), sub(c.party.name)])},
      {id: 'nomination', label: 'Concorre por', cells: each(nominationParts)},
      {id: 'mates', label: 'Chapa', hint: 'Vice ou suplentes, com o mesmo número', cells: each(matesParts)},
      {id: 'status', label: 'Registro no TSE', cells: each(c => [badge(sentenceCase(c.adjudication_status)), sub(c.on_ballot ? 'Na urna' : 'Fora da urna')])},
      {id: 'destination', label: 'Destino dos votos', hint: 'Termo do TSE e o que ele significa', cells: each(c => c.vote_destination
        ? [badge(c.vote_destination), ...(c.vote_destination_note ? [sub(c.vote_destination_note)] : [])]
        : [main(NOT_INFORMED, {muted: true})])},
    ];
    case 'patrimonio': return [
      {id: 'assets', label: 'Bens declarados em 2026', hint: 'Valor pelo custo de aquisição, como declarado', cells: each(assetsParts)},
      // Growth needs the same person across elections (ADR 0009); until the service serves it
      // the row says so, in one note across the columns, and nothing is invented.
      {id: 'growth', label: 'Evolução dos bens', tag: 'Em preparação', full: 'A comparação com as declarações de 2018 a 2024 ainda não está no serviço. Até lá, só o total de 2026.'},
    ];
    case 'ocupacao': return [
      {id: 'occupation', label: 'Ocupação declarada', cells: each(c => [c.occupation ? main(sentenceCase(c.occupation)) : main(NOT_INFORMED, {muted: true})])},
      {id: 'social', label: 'Redes declaradas', cells: each(c => {
        const links = socialPills(c.social_links);
        return links.length ? [{kind: 'links', links, max: linksMax}] : [main('Nenhuma rede declarada', {muted: true})];
      })},
      {id: 'official', label: 'Ficha oficial', hint: 'No site do TSE, abre em nova aba', cells: each(c => c.divulgacandcontas_url
        ? [{kind: 'links', links: [{key: 'dcc', label: 'DivulgaCandContas', href: c.divulgacandcontas_url, icon: <ExternalIcon size={14} aria-hidden />}], max: 1}]
        : [main(NOT_INFORMED, {muted: true})])},
    ];
  }
}

// ---- The body: pair picker, sticky headers and tabs, rows -----------------------------------

export interface ComparisonBodyProps {
  /** The compared candidacies, as the service answers them (ballot order). */
  candidates: readonly ComparedCandidate[];
  /** The URL's `sq`, in the order of marking: the slot (colour) of each candidacy. */
  sqOrder: readonly number[];
  pair: Pair | null;
  onPairChange: (pair: Pair) => void;
  tab: CompareTab;
  onTabChange: (tab: CompareTab) => void;
  /** Wide screens with more than two columns: redo the comparison without one candidacy. */
  onRemove: (sq: number) => void;
  profileContext: {uf: string; office: string};
}

export function ComparisonBody({candidates, sqOrder, pair, onPairChange, tab, onTabChange, onRemove, profileContext}: ComparisonBodyProps) {
  const phone = useMedia('(max-width: 639px)');
  const wide = useMedia('(min-width: 1024px)');
  // The service already answers in ballot-number order; sorting again only guards the
  // invariant (never by any value).
  const sorted = useMemo(() => [...candidates].sort((a, b) => a.number - b.number), [candidates]);
  const pairMode = phone && sorted.length > 2;
  const current = resolvePair(sorted, pair);
  // The column changed least recently, the one the next "Trazer" replaces (lib/pair).
  const older = useRef<Column>(0);
  const [announce, setAnnounce] = useState('');

  const apply = (next: PairState) => {
    older.current = next.older;
    onPairChange(next.pair);
    const changed = next.pair.findIndex(sq => !current.includes(sq));
    const c = sorted.find(x => x.sq_candidato === next.pair[changed]);
    if (c) setAnnounce(`${toTitleCase(c.ballot_name)} na coluna ${changed + 1}`);
  };
  const bring = (sq: number) => {
    const state: PairState = {pair: current, older: older.current};
    const next = bringIn(state, sq, sorted);
    if (next !== state) apply(next);
  };
  const swap = (column: Column) => {
    const state: PairState = {pair: current, older: older.current};
    const next = swapNext(state, sorted, column);
    if (next !== state) apply(next);
  };

  const shown = pairMode ? current.map(sq => sorted.find(c => c.sq_candidato === sq)!) : sorted;
  const slotFor = (c: ComparedCandidate) => slotOf(sqOrder, c.sq_candidato, sorted.indexOf(c) + 1);
  const grid = {'--cv-n': shown.length} as CSSProperties;
  const rows = rowsFor(tab, shown, wide ? LINKS_WIDE : LINKS_PHONE);

  return (
    <>
      {pairMode ? <PairPicker items={sorted.map(c => ({sq_candidato: c.sq_candidato, ballot_name: c.ballot_name, photo_url: c.photo_url, slot: slotFor(c)}))} pair={current} onBring={bring} /> : null}
      <span className="sr-only" aria-live="polite">{announce}</span>
      <div className="comp-sticky">
        <div className="comp-cols" style={grid} role="group" aria-label="Candidaturas na comparação">
          {shown.map((c, i) => (
            <CompareColumnHeader key={c.sq_candidato} c={c} slot={slotFor(c)}
              profileHref={href(`/candidato/${c.sq_candidato}`, {...profileContext, cmp: sqOrder.join(','), pair: pair?.join(','), tab})}
              action={pairMode ? {kind: 'swap', onClick: () => swap(i as Column)} : sorted.length > 2 ? {kind: 'remove', onClick: () => onRemove(c.sq_candidato)} : null} />
          ))}
        </div>
        <div className="comp-tabs">
          <SlidingTabs options={COMPARE_TABS} value={tab} onChange={onTabChange} ariaLabel="Seção da comparação" fill />
        </div>
      </div>
      <div className="comp-rows" style={grid}>
        {rows.map(r => <CompareRow key={r.id} {...r} />)}
      </div>
    </>
  );
}

// ---- Bar, title, notices, footers, states ---------------------------------------------------

export interface ShareContent { title: string; text: string; url: string }

/** The sticky action bar (5.1): "Escolher outras" back to the picker with the candidacies
 *  still marked, and share through `navigator.share` when the browser has it, else a link to
 *  WhatsApp with the same text (5.11). */
export function CompareBar({backHref, share}: {backHref: string; share: ShareContent}) {
  const native = typeof navigator !== 'undefined' && typeof navigator.share === 'function';
  const waHref = `https://wa.me/?text=${encodeURIComponent(share.text)}`;
  const onShare = () => { navigator.share({title: share.title, text: share.text, url: share.url}).catch(() => { /* cancelled or refused: nothing to do */ }); };
  const icon = <Share size={19} aria-hidden />;
  return (
    <div className="comp-bar">
      <a className="comp-back" href={backHref}><ChevronLeft size={18} strokeWidth={2.2} aria-hidden />Escolher outras</a>
      {native ? <IconButton label="Compartilhar comparação" icon={icon} onClick={onShare} /> : <IconButton label="Compartilhar comparação" icon={icon} href={waHref} />}
    </div>
  );
}

/** "{Cargo} · {Estado por extenso}"; the national race reads "Presidente · Brasil". */
export function placeName(uf: string): string {
  return uf === 'BR' ? 'Brasil' : ufName(uf);
}

export function CompareTitle({office, uf, round}: {office: Office; uf: string; round: number | null}) {
  return (
    <header className="comp-head">
      <span className="comp-kicker">{round ? `Eleições 2026 · ${round}º turno` : 'Eleições 2026'}</span>
      <h1 className="comp-h1">{OFFICE[office]} · <span className="cv-mark">{placeName(uf)}</span></h1>
      <p className="comp-lead">O que cada candidatura declarou ao TSE, lado a lado. Sem ranking, sem recomendação de voto.</p>
    </header>
  );
}

const MISSING_PHRASE: Record<string, string> = {
  nao_encontrado: 'não foi encontrada neste cargo e estado',
  fora_da_urna: 'não está na urna',
  fora_do_turno: 'não disputa este turno',
};

export type MissingName = {ballot_name: string; number: number};

/** The candidacies the service left out (5.7), named through their profile when it exists. */
export function MissingNotice({missing, names}: {missing: readonly MissingCandidacy[]; names: ReadonlyMap<number, MissingName>}) {
  return (
    <section className="comp-missing" aria-labelledby="comp-missing-title">
      <Info size={20} aria-hidden />
      <div>
        <span id="comp-missing-title" className="comp-missing-title">Ficaram fora da comparação</span>
        <ul>
          {missing.map(m => {
            const n = names.get(m.requested);
            return <li key={m.requested}>{n ? `${toTitleCase(n.ballot_name)} (${n.number})` : m.reason === 'nao_encontrado' ? `Candidatura ${m.requested}` : 'Uma candidatura marcada'}: {MISSING_PHRASE[m.reason] ?? 'ficou fora da comparação'}.</li>;
          })}
        </ul>
      </div>
    </section>
  );
}

export function GuardrailsNote() {
  return (
    <section className="comp-note" aria-label="Regras da comparação">
      <ShieldCheck size={20} aria-hidden />
      <div className="comp-note-body">
        <span><strong>Ordem pelo número de urna.</strong> Sem ranking, sem pontuação. Gênero, cor/raça, estado civil e escolaridade nunca entram na comparação.</span>
        <span className="comp-note-links">
          <a href={href('/duvidas', {abrir: 'destino'})}>Destino dos votos</a>
          <a href={href('/duvidas', {abrir: 'evolucao'})}>Evolução dos bens</a>
          <a href={href('/duvidas', {abrir: 'cpf'})}>Por que sem CPF</a>
        </span>
      </div>
    </section>
  );
}

export function CompareFoot({source, election, assetsSource}: {source: Source; election?: ElectionInfo | null; assetsSource?: Source | null}) {
  return (
    <footer className="comp-foot">
      <SourceFooter source={source} election={election} />
      {assetsSource ? <SourceFooter source={assetsSource} /> : null}
    </footer>
  );
}

/** Loading (5.10): two column skeletons on the tints of slots 1 and 2 and four grey lines,
 *  no spinner; the text is for the screen reader. */
export function CompareSkeleton() {
  return (
    <div className="comp-skel" role="status">
      <span className="sr-only">Montando a comparação…</span>
      <div className="comp-skel-cols" aria-hidden>
        <span className="comp-skel-col" style={{'--cv-slot-tint': slotColor(1).tint} as CSSProperties} />
        <span className="comp-skel-col" style={{'--cv-slot-tint': slotColor(2).tint} as CSSProperties} />
      </div>
      <div className="comp-skel-lines" aria-hidden>
        {[0, 1, 2, 3].map(i => <span key={i} className="comp-skel-line" />)}
      </div>
    </div>
  );
}

/** Error, not_found and insufficient (5.10): one centred block with the 5.11 phrases. */
export function CompareProblem({title, text, action}: {title: string; text?: string; action: {label: string; onClick: () => void}}) {
  return (
    <div className="comp-problem" role="alert">
      <span className="comp-problem-title">{title}</span>
      {text ? <p className="comp-problem-text">{text}</p> : null}
      <button type="button" className="comp-problem-btn" onClick={action.onClick}>{action.label}</button>
    </div>
  );
}

/** The height of the app's top nav while it is sticky (from 640 px; on phones styles.css
 *  makes it static), so the page's own sticky bar and block sit under it. */
export function useTopNavOffset(): number {
  const [height, setHeight] = useState(0);
  useLayoutEffect(() => {
    const nav = document.querySelector<HTMLElement>('.astryx-app-shell-header');
    if (!nav) return;
    const set = () => setHeight(getComputedStyle(nav).position === 'sticky' ? Math.round(nav.getBoundingClientRect().height) : 0);
    set();
    const ro = new ResizeObserver(set);
    ro.observe(nav);
    window.addEventListener('resize', set);
    return () => { ro.disconnect(); window.removeEventListener('resize', set); };
  }, []);
  return height;
}
