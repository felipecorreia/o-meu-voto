import {useEffect, useLayoutEffect, useRef, useState, type ReactNode} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Text} from '@astryxdesign/core/Text';
import {Badge} from '@astryxdesign/core/Badge';
import {Link} from '@astryxdesign/core/Link';
import {ToggleButton} from '@astryxdesign/core/ToggleButton';
import {TabList, Tab} from '@astryxdesign/core/TabList';
import {X, ExternalLink as ExternalIcon, UserRound, ArrowLeftRight, Users, Wallet, Briefcase, type LucideIcon} from 'lucide-react';
import type {ComparedAssets, ComparedCandidate} from '../api';
import {NOMINATION, OFFICE} from '../labels';
import {href} from '../router';
import {brl, brlFull} from '../format';
import {CandidateAvatar, CandidatePhoto, NumberBadge, OnBallotBadge, SocialLinks, StatusBadge} from './common';

export type DestinationStyle = 'badge' | 'sentence' | 'both';
/** columns: one column per candidacy, horizontal scroll on phones; stacked: one column, each
 *  attribute lists the candidacies; pair: sectioned continuous scroll, exactly two columns on
 *  phones (the pair chosen from the marked set), every column on wider screens; tabs: the pair
 *  layout with the three sections as tabs instead of one continuous page (captain, 2026-09-25
 *  evening, to compare against `pair`). */
export type GridLayout = 'columns' | 'stacked' | 'pair' | 'tabs';
/** The two candidacies on screen in the pair layout, by sq_candidato, left slot first. */
export type Pair = [number, number];

interface Row {
  key: string; label: string; hint?: string;
  /** A row the service does not serve yet: the label carries "em preparação" and one line
   *  across every column says so, instead of a value per candidacy (no invented data). */
  pending?: string;
  cell?: (c: ComparedCandidate, ctx: Ctx) => ReactNode;
}
interface Ctx { destinationStyle: DestinationStyle }

const PendingTag = () => <span className="pending-tag" title="Ainda não está no serviço">em preparação</span>;

function assetsCell(a: ComparedAssets): ReactNode {
  if (a.state === 'declarou_nao_possuir') return <Text>Declarou não possuir bens</Text>;
  if (a.state === 'sem_informacao' || a.total == null) return <Text color="secondary">Sem informação de bens no TSE</Text>;
  return <><span className="money">{brl(a.total)}</span><Text as="p" size="sm" color="secondary">{brlFull(a.total)} · como declarado ao TSE</Text></>;
}

/** The TSE's value verbatim with the service's one-line explanation (ADR 0008); neither is
 *  derived here. */
function destinationCell(c: ComparedCandidate, style: DestinationStyle): ReactNode {
  const d = c.vote_destination;
  if (!d) return <Text color="secondary">Não informado pelo TSE</Text>;
  const note = c.vote_destination_note ? <Text as="p" size="sm" color="secondary">{c.vote_destination_note}</Text> : null;
  if (style === 'badge') return <Badge variant="neutral" label={d} />;
  if (style === 'sentence') return <><Text as="p">Voto {d.toLowerCase()}.</Text>{note}</>;
  return <><div><Badge variant="neutral" label={d} /></div>{note}</>;
}

/**
 * The field set of ADR 0008 (codebase-design 8.7), plus the v1.1 growth line still pending.
 * Columns by ballot number, no sort, no colour and no bar scaled by money.
 */
const ROWS: Row[] = [
  {key: 'name', label: 'Nome civil', cell: c => <>{c.name}{c.social_name ? <Text as="p" size="sm" color="secondary">nome social: {c.social_name}</Text> : null}</>},
  {key: 'party', label: 'Partido', cell: c => <><span><strong>{c.party.acronym}</strong> · {c.party.number}</span><Text as="p" size="sm" color="secondary">{c.party.name}</Text></>},
  {key: 'nomination', label: 'Concorre por', hint: 'partido isolado, federação ou coligação', cell: c => (
    <>
      <Badge variant="neutral" label={NOMINATION[c.nomination_kind] ?? c.nomination_kind} />
      {c.federation ? <Text as="p" size="sm">{c.federation.acronym}: {c.federation.name}</Text> : null}
      {c.coalition ? <Text as="p" size="sm">{c.coalition.name}</Text> : null}
      {(c.coalition?.composition || c.federation?.composition) ? <Text as="p" size="sm" color="secondary">{c.coalition?.composition || c.federation?.composition}</Text> : null}
    </>
  )},
  {key: 'mates', label: 'Chapa', hint: 'vice ou suplentes, mesmo número', cell: c => c.running_mates.length ? (
    <ul className="plain">
      {c.running_mates.map(m => <li key={m.sq_candidato}><strong>{m.ballot_name}</strong> <Text size="sm" color="secondary">· {m.party.acronym} · {OFFICE[m.office as keyof typeof OFFICE] ?? m.office}</Text></li>)}
    </ul>
  ) : <Text color="secondary">Não se aplica</Text>},
  // Captain's Q20 answer (2026-09-25): neutral in the comparison, coloured in the picker and the profile.
  {key: 'status', label: 'Registro no TSE', hint: 'situação de julgamento e presença na urna', cell: c => <div className="chips chips-compact"><StatusBadge status={c.adjudication_status} tone="neutral" /><OnBallotBadge onBallot={c.on_ballot} tone="neutral" /></div>},
  {key: 'destination', label: 'Destino dos votos', hint: 'como o TSE classifica o voto nesta candidatura', cell: (c, ctx) => destinationCell(c, ctx.destinationStyle)},
  {key: 'occupation', label: 'Ocupação declarada', cell: c => <span className="sentence">{c.occupation ?? '—'}</span>},
  {key: 'assets', label: 'Bens declarados em 2026', hint: 'total, como declarado ao TSE', cell: c => assetsCell(c.assets)},
  // Growth needs the same person across elections (ADR 0009); until the service serves it the
  // row says so. When it lands, the captain's choice is to collapse it behind "Ver evolução".
  {key: 'growth', label: 'Evolução dos bens', hint: 'em reais, contra a última declaração anterior',
    pending: 'A comparação com as declarações de 2018 a 2024 ainda não está no serviço. Até lá, só o total de 2026.'},
  {key: 'social', label: 'Redes declaradas', cell: c => <SocialLinks links={c.social_links} compact />},
  {key: 'official', label: 'Ficha oficial', cell: c => c.divulgacandcontas_url
    ? <Button size="sm" variant="ghost" label="DivulgaCandContas" icon={<ExternalIcon size={14} aria-hidden />} href={c.divulgacandcontas_url} target="_blank" rel="noopener noreferrer" />
    : <Text color="secondary">—</Text>},
];

/**
 * Sections of the pair layout (captain, 2026-09-25): the proposal's dimensions with assets and
 * their evolution merged into one. In `layout=pair` they are sticky headers in one continuous
 * scroll, all open, with anchor jumps; in `layout=tabs` (captain, same evening: "imaginei que
 * veria as abas") the same three sections are tabs and only one is on screen. The rows and
 * their rules are identical in both, so the board compares the container only.
 */
// Tab icons (captain, 2026-09-25 evening: "inclua ícones, como no exemplo, busque ícones que não
// são de IA"): lucide, the hand-drawn open-source set the Astryx theme already registers.
const SECTIONS: Array<{key: string; title: string; short: string; icon: LucideIcon; rows: string[]}> = [
  {key: 'chapa', title: 'Chapa e registro', short: 'Chapa e registro', icon: Users, rows: ['name', 'party', 'nomination', 'mates', 'status', 'destination']},
  {key: 'patrimonio', title: 'Patrimônio', short: 'Patrimônio', icon: Wallet, rows: ['assets', 'growth']},
  // The three full titles do not fit a 390 px tab strip (measured 446 px); the phone label is shorter.
  {key: 'ocupacao', title: 'Ocupação e transparência', short: 'Ocupação', icon: Briefcase, rows: ['occupation', 'social', 'official']},
];

function useMedia(query: string): boolean {
  const [matches, setMatches] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatches(mq.matches);
    on();
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, [query]);
  return matches;
}

function RowCells({r, shown, ctx, who = false}: {r: Row; shown: ComparedCandidate[]; ctx: Ctx; who?: boolean}) {
  if (r.pending || !r.cell) return <div className="cmp-cell cmp-pending" role="cell"><Text color="secondary">{r.pending}</Text></div>;
  const cell = r.cell;
  return <>{shown.map(c => (
    <div key={c.sq_candidato} className="cmp-cell" role="cell">
      {who ? <span className="cmp-who">{c.number} · {c.ballot_name}</span> : null}
      {cell(c, ctx)}
    </div>
  ))}</>;
}

function RowLabel({r, extra}: {r: Row; extra?: ReactNode}) {
  return (
    <div className="cmp-label" role="rowheader">
      <span className="cmp-label-inner">
        <span className="cmp-label-text">{r.label}</span>
        {r.hint ? <span className="cmp-label-hint">{r.hint}</span> : null}
        {r.pending ? <PendingTag /> : null}
        {extra}
      </span>
    </div>
  );
}

/** Pair layout ("Lado a lado"). `profiles` are already sorted by ballot number.
 *  `tabs` swaps the sectioned page for a tab strip (same header, chips and swap). */
function PairGrid({profiles, ctx, pair, onPairChange, onRemove, tabs = false, tab = null, onTabChange}: {
  profiles: ComparedCandidate[]; ctx: Ctx; pair: Pair | null; onPairChange?: (p: Pair) => void; onRemove?: (sq: number) => void;
  tabs?: boolean; tab?: string | null; onTabChange?: (key: string) => void;
}) {
  const phone = useMedia('(max-width: 639px)');
  const n = profiles.length;
  const pairMode = phone && n > 2;
  // A pair from the URL that no longer matches the marked set falls back to the two lowest numbers.
  const validPair: Pair = pair && pair[0] !== pair[1] && pair.every(sq => profiles.some(p => p.sq_candidato === sq))
    ? pair : [profiles[0].sq_candidato, profiles[1].sq_candidato];
  const shown = pairMode ? validPair.map(sq => profiles.find(p => p.sq_candidato === sq)!) : profiles;
  const k = shown.length;
  const cols = {gridTemplateColumns: `repeat(${k}, minmax(0, 1fr))`};
  // The slot changed least recently is the one a chip tap replaces, so successive taps rotate.
  const lastSlot = useRef<0 | 1>(0);
  // Active tab (tabs variant): from the URL when valid, else the first section.
  const [activeTab, setActiveTab] = useState<string>(() => SECTIONS.some(s => s.key === tab) ? tab! : SECTIONS[0].key);
  const rootRef = useRef<HTMLDivElement>(null);
  const headRef = useRef<HTMLDivElement>(null);
  const stripRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // The column header sticks under the app's sticky top nav (AppShell height="auto" makes it
  // sticky; `.astryx-app-shell-header` is a stable class in 0.6.3) and the section headers (or
  // the tab strip) stick right under the column header, whatever its height (names wrap).
  useLayoutEffect(() => {
    const root = rootRef.current, head = headRef.current, strip = stripRef.current;
    if (!root || !head) return;
    const nav = document.querySelector<HTMLElement>('.astryx-app-shell-header');
    const set = () => {
      const navH = nav && getComputedStyle(nav).position === 'sticky' ? nav.getBoundingClientRect().height : 0;
      root.style.setProperty('--topnav-h', `${navH}px`);
      root.style.setProperty('--pair-head-h', `${navH + head.getBoundingClientRect().height}px`);
      root.style.setProperty('--pair-strip-h', `${strip ? strip.getBoundingClientRect().height : 0}px`);
    };
    set();
    const ro = new ResizeObserver(set);
    ro.observe(head);
    if (strip) ro.observe(strip);
    if (nav) ro.observe(nav);
    return () => ro.disconnect();
  }, [k, tabs]);

  const setSlot = (slot: 0 | 1, sq: number) => {
    const next: Pair = slot === 0 ? [sq, validPair[1]] : [validPair[0], sq];
    lastSlot.current = slot;
    onPairChange?.(next);
  };
  const bring = (sq: number) => setSlot(lastSlot.current === 0 ? 1 : 0, sq);
  const swap = (slot: 0 | 1) => {
    const current = shown[slot];
    const others = profiles.filter(p => !validPair.includes(p.sq_candidato));
    if (!others.length) return;
    const next = others.find(p => p.number > current.number) ?? others[0];
    setSlot(slot, next.sq_candidato);
  };
  const jump = (key: string) => document.getElementById(`cmp-sec-${key}`)?.scrollIntoView({behavior: 'smooth', block: 'start'});
  const pickTab = (key: string) => {
    setActiveTab(key);
    onTabChange?.(key);
    // A panel shorter than the scrolled distance would leave the reader below its end: when the
    // strip is stuck, bring the panel's top back under it.
    const strip = stripRef.current, panel = panelRef.current;
    if (strip && panel && strip.getBoundingClientRect().top <= parseFloat(getComputedStyle(strip).top) + 1) {
      requestAnimationFrame(() => panel.scrollIntoView({block: 'start'}));
    }
  };

  const renderRows = (rows: Row[]) => rows.map(r => (
    <div key={r.key} className="cmp-row" role="rowgroup">
      <RowLabel r={r} />
      <RowCells r={r} shown={shown} ctx={ctx} />
    </div>
  ));
  const sectionRows = (s: typeof SECTIONS[number]) => s.rows.map(key => ROWS.find(r => r.key === key)!);
  const active = SECTIONS.find(s => s.key === activeTab) ?? SECTIONS[0];

  return (
    <>
      {pairMode ? (
        <div className="pair-pick" role="group" aria-label="Candidaturas na tela">
          <Text as="p" size="sm" color="secondary">Na tela, 2 de {n}. Toque em outra candidatura para trazê-la, ou use a seta de troca em cada coluna.</Text>
          <div className="chips chips-compact">
            {profiles.map(c => {
              const on = validPair.includes(c.sq_candidato);
              return <ToggleButton key={c.sq_candidato} size="sm" label={`${c.number} · ${c.ballot_name}`} isPressed={on} onPressedChange={() => { if (!on) bring(c.sq_candidato); }} />;
            })}
          </div>
        </div>
      ) : null}
      <div className={`pair ${tabs ? 'pair-tabbed' : ''}`} ref={rootRef} role={tabs ? undefined : 'table'} aria-label={tabs ? undefined : 'Comparação de candidaturas, lado a lado'}>
        <div className="pair-head" ref={headRef} role={tabs ? 'group' : 'row'} aria-label={tabs ? 'Candidaturas na comparação' : undefined} style={cols}>
          {shown.map((c, i) => (
            <div key={c.sq_candidato} className="pair-col" role={tabs ? undefined : 'columnheader'}>
              <CandidatePhoto c={c} />
              <div className="pair-col-body">
                <div className="pair-col-top">
                  <NumberBadge n={c.number} />
                  <span className="grow" />
                  {pairMode
                    ? <Button size="sm" variant="ghost" isIconOnly icon={<ArrowLeftRight size={16} aria-hidden />} label={`Trocar ${c.ballot_name} pela próxima candidatura marcada`} onClick={() => swap(i as 0 | 1)} />
                    : onRemove && n > 2 ? <Button size="sm" variant="ghost" isIconOnly icon={<X size={16} aria-hidden />} label={`Tirar ${c.ballot_name} da comparação`} onClick={() => onRemove(c.sq_candidato)} /> : null}
                </div>
                <span className="pair-name"><Link href={href(`/candidato/${c.sq_candidato}`)}>{c.ballot_name}<span className="sr-only">, ver ficha</span></Link></span>
                <span className="pair-party"><Text size="sm" color="secondary">{c.party.acronym}</Text></span>
              </div>
            </div>
          ))}
        </div>
        {tabs ? (
          <>
            <div className="pair-strip" ref={stripRef}>
              <TabList role="tablist" value={active.key} onChange={pickTab} size="sm" hasDivider>
                {SECTIONS.map(s => <Tab key={s.key} value={s.key} label={phone ? s.short : s.title} icon={<s.icon size={16} aria-hidden />} panelId={`cmp-panel-${s.key}`} />)}
              </TabList>
            </div>
            <div ref={panelRef} id={`cmp-panel-${active.key}`} role="tabpanel" aria-label={active.title} className="pair-panel">
              <div className="pair-rows" role="table" aria-label={`${active.title}, lado a lado`} style={cols}>
                {renderRows(sectionRows(active))}
              </div>
            </div>
          </>
        ) : (
          <>
            <nav className="pair-jump" aria-label="Seções da comparação">
              <span className="pair-jump-label">Ir para</span>
              {SECTIONS.map(s => <Button key={s.key} size="sm" variant="ghost" label={s.title} onClick={() => jump(s.key)} />)}
            </nav>
            {SECTIONS.map(s => (
              <section key={s.key} id={`cmp-sec-${s.key}`} className="pair-section" aria-labelledby={`cmp-sec-${s.key}-h`}>
                <h3 id={`cmp-sec-${s.key}-h`} className="pair-sec-head">{s.title}</h3>
                <div className="pair-rows" style={cols}>
                  {renderRows(sectionRows(s))}
                </div>
              </section>
            ))}
          </>
        )}
      </div>
    </>
  );
}

export function CompareGrid({profiles: input, onRemove, destinationStyle = 'both', layout = 'tabs', pair = null, onPairChange, tab = null, onTabChange}: {
  profiles: ComparedCandidate[]; onRemove?: (sq: number) => void; destinationStyle?: DestinationStyle; layout?: GridLayout;
  pair?: Pair | null; onPairChange?: (p: Pair) => void; tab?: string | null; onTabChange?: (key: string) => void;
}) {
  // The service already answers in ballot-number order; sorting again only guards the invariant
  // (never by any value).
  const profiles = [...input].sort((a, b) => a.number - b.number);
  const n = profiles.length;
  const ctx: Ctx = {destinationStyle};
  const stacked = layout === 'stacked';
  return (
    <>
      {layout === 'pair' || layout === 'tabs' ? <PairGrid profiles={profiles} ctx={ctx} pair={pair} onPairChange={onPairChange} onRemove={onRemove} tabs={layout === 'tabs'} tab={tab} onTabChange={onTabChange} /> : (
      <div className={`cmp ${stacked ? 'cmp-stacked' : ''}`} role="table" aria-label="Comparação de candidaturas">
        <div className="cmp-grid" style={{gridTemplateColumns: stacked ? '1fr' : `repeat(${n}, minmax(190px, 1fr))`}}>
          {stacked ? (
            <div className="cmp-stack-head" role="row">
              {profiles.map(c => <span key={c.sq_candidato} className="chip"><span className="chip-n">{c.number}</span>{c.ballot_name}</span>)}
            </div>
          ) : (
            <div className="cmp-row cmp-head" role="row">
              {profiles.map(c => (
                <div key={c.sq_candidato} className="cmp-cell cmp-head-cell" role="columnheader">
                  <div className="cmp-head-top">
                    <CandidateAvatar c={c} size="lg" />
                    {onRemove && n > 2 ? <Button size="sm" variant="ghost" isIconOnly icon={<X size={16} aria-hidden />} label={`Tirar ${c.ballot_name} da comparação`} onClick={() => onRemove(c.sq_candidato)} /> : null}
                  </div>
                  <div className="cmp-head-name">
                    <span className="ballot-name">{c.ballot_name}</span>
                    <NumberBadge n={c.number} />
                  </div>
                  <Text size="sm" color="secondary">{c.party.acronym} · {OFFICE[c.office as keyof typeof OFFICE] ?? c.office}</Text>
                  <Button size="sm" variant="ghost" label="Ver ficha" icon={<UserRound size={14} aria-hidden />} href={href(`/candidato/${c.sq_candidato}`)} />
                </div>
              ))}
            </div>
          )}
          {ROWS.map(r => (
            <div key={r.key} className="cmp-row" role="rowgroup">
              <RowLabel r={r} />
              <RowCells r={r} shown={profiles} ctx={ctx} who={stacked} />
            </div>
          ))}
        </div>
      </div>
      )}
      <div className="caveats">
        <Text as="p" size="sm" color="secondary">Ordem por número de urna. Sem ranking, sem pontuação, sem recomendação de voto. Gênero, cor/raça, estado civil e escolaridade nunca entram nesta comparação (ADR 0004). Entenda <Link href={href('/duvidas', {abrir: 'destino'})}>o destino dos votos</Link>, <Link href={href('/duvidas', {abrir: 'evolucao'})}>a evolução dos bens</Link> e <Link href={href('/duvidas', {abrir: 'cpf'})}>o que fazemos com os seus dados</Link>.</Text>
        {/* The page's own wording of the service's assets_note, which names an API field for MCP clients. */}
        <Text as="p" size="sm" color="secondary">Bens: valores como declarados ao TSE pela própria candidatura, em geral pelo custo de aquisição, não pelo valor de mercado; nada é corrigido nem avaliado aqui. Detalhe oficial de cada bem na ficha do DivulgaCandContas.</Text>
      </div>
    </>
  );
}
