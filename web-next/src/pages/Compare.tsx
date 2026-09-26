import {useCallback, useEffect, useMemo, useRef, useState, type CSSProperties} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Badge} from '@astryxdesign/core/Badge';
import {Banner} from '@astryxdesign/core/Banner';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {ArrowLeft, Share2} from 'lucide-react';
import {api, ApiError, type CandidateListItem, type ComparisonData, type Envelope, type CandidatesData, type MissingCandidacy} from '../api';
import {BALLOT_OFFICES, OFFICE, OFFICE_SHORT, officesFor, ufName, type Office} from '../labels';
import {href, navigate} from '../router';
import {plural} from '../format';
import {ErrorState, Loading, NotFoundState, SourceFooter, StatusBadge, Warnings} from '../components/common';
import {CompareGrid, type DestinationStyle, type GridLayout, type Pair} from '../components/CompareGrid';
import {FilteredEmpty, LoadMore, OffBallotChip, PickFooter, PickHero, SearchField} from '../components/Picker';
import {CandidateCard} from '../components/cv/CandidateCard';
import {CompareTray} from '../components/cv/CompareTray';
import {SlidingTabs} from '../components/cv/SlidingTabs';
import {StatePill} from '../components/cv/StatePill';
import {compareParams, MAX_MARKED, MIN_MARKED} from '../lib/marking';
import {cvTokens} from '../themes/cde';

const MAX = MAX_MARKED;
const MIN = MIN_MARKED;
const PAGE = 50;
/** Search text in the unified field that goes to `by-number` instead of `name` (spec 5.4.1). */
const NUMBER_QUERY = /^\d{2,5}$/;
/** A name search with no result is retried as a party acronym when the text is this short. */
const PARTY_FALLBACK_MAX = 12;

const MISSING_REASON: Record<MissingCandidacy['reason'], string> = {
  nao_encontrado: 'não foi encontrada neste cargo e estado',
  fora_da_urna: 'não está na urna',
  fora_do_turno: 'não disputa este turno',
};

/** What the list is filtered by; remembered so "Carregar mais" repeats the same call. */
type ListFilter = {name?: string; party?: string};
type NumberHit = {kind: 'found'; number: string; c: CandidateListItem} | {kind: 'none'; number: string};
/** The call that failed, so "Tentar de novo" repeats it. The choice screen words every failure
 *  with the phrases of spec 5.11 and never shows the service's message, `not_found.reason` or
 *  `guidance` (some name MCP tools). */
type FailedCall = 'first' | 'more' | 'number';

export function ComparePage({params}: {params: URLSearchParams}) {
  // Route state: uf, office and the selected sq list live in the hash, so a comparison is a link.
  const initialUf = params.get('uf') || 'SP';
  const initialOffice = (params.get('office') as Office) || officesFor(initialUf)[0];
  const initialSq = (params.get('sq') || '').split(',').filter(Boolean).map(Number);
  // Presentation switches for the design review (Lavish board questions 17 to 19); defaults are the recommendation.
  const destinationStyle = (params.get('dest') as DestinationStyle) || 'both';
  // `tabs` (captain, 2026-09-25 evening: "gostei muito mais desse aqui! Vamos focar nessa") is the
  // default; `pair`, `columns` and `stacked` stay reachable for the review until the landing PR.
  const layout = (params.get('layout') as GridLayout) || 'tabs';
  const initialPair = ((params.get('pair') || '').split(',').filter(Boolean).map(Number));
  const initialTab = params.get('tab');

  const [uf, setUf] = useState(initialUf);
  const [office, setOffice] = useState<Office>(BALLOT_OFFICES.includes(initialOffice) ? initialOffice : officesFor(initialUf)[0]);
  // The unified search field (name, party acronym or ballot number) and its debounced value.
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [all, setAll] = useState(false);
  const [list, setList] = useState<Envelope<CandidatesData> | null>(null);
  const [failed, setFailed] = useState<FailedCall | null>(null);
  const [loading, setLoading] = useState(false);
  // The candidacy found by ballot number for a numeric query, shown on top of the unfiltered list.
  const [numberHit, setNumberHit] = useState<NumberHit | null>(null);
  // Bumped by "Tentar de novo" after a failed by-number call, to run it again.
  const [numberAttempt, setNumberAttempt] = useState(0);
  // Insertion order is the order of marking, which the tray's slot colours follow.
  const [selected, setSelected] = useState<Map<number, CandidateListItem>>(new Map());
  const [view, setView] = useState<'pick' | 'compare'>(initialSq.length >= MIN ? 'compare' : 'pick');
  // The candidacies the comparison asks for, by sq_candidato; one call to compare_candidates answers them all.
  const [compareSq, setCompareSq] = useState<number[]>(initialSq.length >= MIN ? initialSq : []);
  const [comparison, setComparison] = useState<Envelope<ComparisonData> | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);
  // Ballot name and number of the requested candidacies the service left out, to name them in the notice.
  const [missingNames, setMissingNames] = useState<Map<number, string>>(new Map());
  // The two candidacies on screen in the pair layout on phones; kept in the URL so the link reproduces the screen.
  const [pair, setPair] = useState<Pair | null>(initialPair.length === 2 ? [initialPair[0], initialPair[1]] : null);
  // The open tab in the tabbed variant, also kept in the URL.
  const [tab, setTab] = useState<string | null>(initialTab);
  const reqId = useRef(0);
  const appliedFilter = useRef<ListFilter>({});

  const officeOptions = useMemo(() => officesFor(uf).map(o => ({value: o, label: OFFICE_SHORT[o]})), [uf]);
  // Keep office valid for the UF (the old page defaulted to "presidente" and errored for states).
  const onUf = (v: string) => { setUf(v); const ok = officesFor(v); if (!ok.includes(office)) setOffice(ok[0]); setSelected(new Map()); };
  const onOffice = (v: Office) => { setOffice(v); setSelected(new Map()); };

  // 250 ms debounce on the text; clearing the field goes back to the unfiltered list at once.
  useEffect(() => {
    if (!query.trim()) { setDebounced(''); return; }
    const t = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);
  const isNumberQuery = NUMBER_QUERY.test(debounced);
  // A numeric query keeps the list unfiltered (the number goes to by-number); text goes as `name`.
  const nameQuery = debounced && !isNumberQuery ? debounced : '';

  const listParams = useCallback((filter: ListFilter, offset: number) =>
    ({uf, office, ...filter, on_ballot_only: !all, limit: PAGE, offset}), [uf, office, all]);

  // First page for the current filters. Rule 5.4.2: a text with no name match, up to 12
  // characters, is retried as a party acronym (so "PSOL" finds the party's candidacies).
  const fetchFirst = useCallback(async () => {
    const id = ++reqId.current;
    setLoading(true); setFailed(null);
    try {
      let filter: ListFilter = nameQuery ? {name: nameQuery} : {};
      let env = await api.candidates(listParams(filter, 0));
      if (id !== reqId.current) return;
      if (nameQuery && env.data?.total === 0 && nameQuery.length <= PARTY_FALLBACK_MAX) {
        filter = {party: nameQuery};
        env = await api.candidates(listParams(filter, 0));
        if (id !== reqId.current) return;
      }
      appliedFilter.current = filter;
      setList(env);
    } catch {
      if (id === reqId.current) { setList(null); setFailed('first'); }
    } finally { if (id === reqId.current) setLoading(false); }
  }, [listParams, nameQuery]);
  useEffect(() => { void fetchFirst(); }, [fetchFirst]);

  // "Carregar mais": the same call with the next offset, results appended.
  const fetchMore = async () => {
    const offset = list?.data?.candidates.length ?? 0;
    const id = ++reqId.current;
    setLoading(true); setFailed(null);
    try {
      const env = await api.candidates(listParams(appliedFilter.current, offset));
      if (id !== reqId.current) return;
      setList(prev => prev?.data && env.data ? {...env, data: {...env.data, candidates: [...prev.data.candidates, ...env.data.candidates]}} : env);
    } catch {
      if (id === reqId.current) setFailed('more');
    } finally { if (id === reqId.current) setLoading(false); }
  };

  // Rule 5.4.1: two to five digits look the candidacy up by ballot number (the voter usually
  // knows it on a 1,000+ list); found, it heads the list; not found, one discreet line.
  useEffect(() => {
    // A new lookup (or a cleared field) drops a banner left by a failed by-number call.
    setFailed(f => f === 'number' ? null : f);
    if (!isNumberQuery) { setNumberHit(null); return; }
    const number = debounced;
    let alive = true;
    api.candidateByNumber({uf, office, number}).then(env => {
      if (!alive) return;
      setNumberHit(env.data ? {kind: 'found', number, c: env.data.candidate} : {kind: 'none', number});
    }).catch(e => {
      if (!alive) return;
      // A 4xx (a malformed number for the office) reads as "not found"; anything else is the
      // service failing, worded like a list error (spec 5.11), never with its message.
      if (e instanceof ApiError && e.status < 500) setNumberHit({kind: 'none', number});
      else { setNumberHit(null); setFailed('number'); }
    });
    return () => { alive = false; };
  }, [uf, office, debounced, isNumberQuery, numberAttempt]);
  const retry = () => {
    if (failed === 'more') void fetchMore();
    else if (failed === 'number') { setFailed(null); setNumberAttempt(n => n + 1); }
    else void fetchFirst();
  };

  // A link that opens the picker with candidacies already marked (the profile's "Comparar com
  // outras"): load them by profile. A comparison link marks them from the comparison instead.
  useEffect(() => {
    if (!initialSq.length || initialSq.length >= MIN) return;
    let alive = true;
    Promise.all(initialSq.map(sq => api.candidate(sq))).then(envs => {
      if (!alive) return;
      const m = new Map<number, CandidateListItem>();
      for (const e of envs) if (e.data) m.set(e.data.candidate.sq_candidato, e.data.candidate);
      setSelected(m);
    }).catch(() => { /* the picker still works without them */ });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The order of marking: the tray's slot colours and the exit link follow it (spec 4.1), so
  // the comparison screen can paint each candidacy with the same colour.
  const marked = useMemo(() => Array.from(selected.values()), [selected]);
  const toggle = (c: CandidateListItem) => setSelected(prev => {
    const m = new Map(prev);
    if (m.has(c.sq_candidato)) m.delete(c.sq_candidato);
    else { if (m.size >= MAX) return prev; m.set(c.sq_candidato, c); }
    return m;
  });
  const unmark = (sq: number) => setSelected(prev => { const m = new Map(prev); m.delete(sq); return m; });
  const clearSearch = () => { setQuery(''); setAll(false); };

  const compare = () => {
    navigate('/', compareParams(uf, office, marked));
    setCompareSq(marked.map(c => c.sq_candidato));
    setView('compare');
  };

  const compareKey = compareSq.join(',');
  useEffect(() => {
    if (view !== 'compare') return;
    if (compareSq.length < MIN) { setView('pick'); return; }
    let alive = true;
    setComparison(null); setCompareError(null); setMissingNames(new Map());
    api.compare({uf, office, sq: compareSq}).then(env => {
      if (!alive) return;
      setComparison(env);
      if (env.data) setSelected(new Map(env.data.candidates.map(c => [c.sq_candidato, c])));
      const missing = env.data?.missing ?? [];
      if (missing.length) {
        Promise.all(missing.map(m => api.candidate(m.requested).then(e => e.data?.candidate, () => undefined))).then(cs => {
          if (!alive) return;
          setMissingNames(new Map(cs.flatMap(c => c ? [[c.sq_candidato, `${c.ballot_name} (${c.number})`] as [number, string]] : [])));
        });
      }
    }).catch(e => { if (alive) setCompareError(e instanceof ApiError ? e.message : String((e as Error).message ?? e)); });
    return () => { alive = false; };
    // compareKey stands for compareSq; uf and office only change in the picker.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, compareKey]);

  const removeFromComparison = (sq: number) => {
    setCompareSq(prev => prev.filter(x => x !== sq));
    setSelected(prev => { const m = new Map(prev); m.delete(sq); return m; });
  };

  // Swapping a column or a tab must not remount the page (the route key is the hash), so both go in with replaceState.
  const paired = layout === 'pair' || layout === 'tabs';
  useEffect(() => {
    if (view !== 'compare') return;
    const q = new URLSearchParams(location.hash.replace(/^#\/?\??/, ''));
    q.set('sq', compareKey);
    if (paired && pair) q.set('pair', pair.join(',')); else q.delete('pair');
    if (paired && layout === 'tabs' && tab) q.set('tab', tab); else q.delete('tab');
    history.replaceState(null, '', `#/?${q}`);
  }, [pair, tab, view, layout, paired, compareKey]);

  const shareParams = {uf, office, sq: compareKey, layout: layout === 'tabs' ? undefined : layout, pair: paired && pair ? pair.join(',') : undefined, tab: layout === 'tabs' && tab ? tab : undefined};
  const shareUrl = `${location.origin}${location.pathname}${location.search}${href('/', shareParams)}`;
  const waHref = `https://wa.me/?text=${encodeURIComponent(`Compare as candidaturas a ${OFFICE[office]} (${uf}) lado a lado, com os dados abertos do TSE: ${shareUrl}`)}`;

  if (view === 'compare') {
    const data = comparison?.data;
    return (
      <div className="page">
        <div className="bar">
          <Button variant="ghost" size="sm" label="Escolher outras" icon={<ArrowLeft size={16} aria-hidden />} onClick={() => { setView('pick'); navigate('/', {uf, office}); }} />
          <Button variant="secondary" size="sm" label="Compartilhar" icon={<Share2 size={16} aria-hidden />} href={waHref} target="_blank" rel="noopener noreferrer" />
        </div>
        <header className="page-head">
          <h1 className="h1">{OFFICE[office]} · {uf === 'BR' ? 'Brasil' : uf}</h1>
          <p className="lead">O que cada candidatura declarou ao TSE, lado a lado. Sem ranking, sem recomendação de voto.</p>
        </header>
        {comparison ? <Warnings warnings={comparison.warnings} /> : null}
        {compareError ? <ErrorState message={compareError} /> : null}
        {!comparison && !compareError ? <Loading label="Montando a comparação…" /> : null}
        {comparison && !data && comparison.not_found ? (
          // The service's guidance names MCP tools; the page words the one reason it expects itself.
          comparison.not_found.reason === 'candidaturas_insuficientes'
            ? <EmptyState isCompact title="Não há candidaturas suficientes para comparar" description="Menos de duas das candidaturas marcadas estão na urna neste turno. Volte à lista e marque de 2 a 4 candidaturas na urna." />
            : <NotFoundState nf={comparison.not_found} />
        ) : null}
        {data && data.missing.length ? (
          <Banner status="info" container="card" elevation="none" collapsible={false} title="Ficaram fora da comparação"
            description={data.missing.map(m => `${missingNames.get(m.requested) ?? 'Uma candidatura marcada'}: ${MISSING_REASON[m.reason]}.`).join(' ')} />
        ) : null}
        {data ? <CompareGrid profiles={data.candidates} destinationStyle={destinationStyle} layout={layout} pair={pair} onPairChange={setPair} tab={tab} onTabChange={setTab} onRemove={removeFromComparison} /> : null}
        {comparison ? <SourceFooter source={comparison.source} election={comparison.election} /> : null}
        {data ? <SourceFooter source={data.assets_source} /> : null}
      </div>
    );
  }

  // ---- Choice mode (Tela 1) -------------------------------------------------------------------
  const data = list?.data;
  const full = selected.size >= MAX;
  const hit = numberHit?.kind === 'found' ? numberHit.c : null;
  // The hit heads the list; the same candidacy is not repeated below it.
  const candidates = data ? (hit ? data.candidates.filter(c => c.sq_candidato !== hit.sq_candidato) : data.candidates) : [];
  const card = (c: CandidateListItem) => {
    const flagged = c.adjudication_status.toUpperCase() !== 'DEFERIDO' || !c.on_ballot;
    return (
      <CandidateCard key={c.sq_candidato} c={c} on={selected.has(c.sq_candidato)} disabled={full && !selected.has(c.sq_candidato)} onToggle={() => toggle(c)}
        badges={flagged ? <><StatusBadge status={c.adjudication_status} />{!c.on_ballot ? <Badge variant="error" label="Fora da urna" /> : null}</> : undefined} />
    );
  };
  // "{Cargo} em {UF por extenso}" of the spec 5.11 phrases ("Governador em São Paulo"; the
  // national race reads "Presidente no Brasil").
  const race = `${OFFICE[office]} ${uf === 'BR' ? 'no Brasil' : `em ${ufName(uf)}`}`;

  return (
    <div className="page cv-page pick" style={cvTokens as CSSProperties}>
      <PickHero />
      <div className="pick-filters">
        <StatePill uf={uf} onChange={onUf} />
        <SlidingTabs options={officeOptions} value={office} onChange={onOffice} ariaLabel="Cargo" />
      </div>
      <div className="pick-search">
        <SearchField value={query} onChange={setQuery} />
        <div className="pick-chips"><OffBallotChip on={all} onChange={setAll} /></div>
      </div>

      <section aria-labelledby="pick-title">
        <div className="pick-head">
          <h2 id="pick-title" className="pick-h2">{data ? plural(data.total, 'candidatura', 'candidaturas') : 'Candidaturas'}</h2>
          <span className="pick-round">{OFFICE_SHORT[office]}{data ? ` · ${data.round}º turno` : ''}</span>
        </div>
        {failed ? <ErrorState title="Não foi possível consultar os dados agora." message="Tente de novo em instantes." onRetry={retry} /> : null}
        {list ? <Warnings warnings={list.warnings} /> : null}
        {loading && !data ? <Loading /> : null}
        {/* The service answers an empty list, never not_found, for a race with no candidacy; both read the same (spec 5.11). */}
        {(list && !data && list.not_found) || (data && data.candidates.length === 0 && !hit && !nameQuery)
          ? <EmptyState isCompact title={`Não encontramos candidaturas para ${race}.`} description="Confira o estado e o cargo." /> : null}
        {hit ? (
          <div className="pick-hit">
            <span className="pick-hit-label">Número {numberHit?.number}</span>
            {card(hit)}
            {full && !selected.has(hit.sq_candidato) ? <p className="pick-hit-none">Já há {MAX} marcadas. Tire uma para adicionar.</p> : null}
          </div>
        ) : null}
        {numberHit?.kind === 'none' ? <p className="pick-hit-none">Nenhuma candidatura com o número {numberHit.number} para {race}.</p> : null}
        {data && data.candidates.length === 0 && !hit && nameQuery ? <FilteredEmpty onClear={clearSearch} /> : null}
        {candidates.length ? <div className="pick-grid">{candidates.map(card)}</div> : null}
        {data && data.candidates.length < data.total ? <LoadMore shown={data.candidates.length} total={data.total} loading={loading} onClick={() => void fetchMore()} /> : null}
      </section>

      <PickFooter>{list ? <SourceFooter source={list.source} election={list.election} /> : null}</PickFooter>
      <CompareTray marked={marked} onRemove={unmark} onCompare={compare} />
    </div>
  );
}
