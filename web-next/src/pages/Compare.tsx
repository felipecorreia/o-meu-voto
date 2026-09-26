import {useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode} from 'react';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {api, ApiError, type CandidateListItem, type ComparisonData, type Envelope, type CandidatesData} from '../api';
import {BALLOT_OFFICES, OFFICE, OFFICE_SHORT, officesFor, ufName, type Office} from '../labels';
import {href, navigate} from '../router';
import {plural} from '../format';
import {ErrorState, Loading, SourceFooter, Warnings} from '../components/common';
import {StatusBadge} from '../components/cv/StatusBadge';
import {CompareBar, CompareFoot, CompareProblem, CompareSkeleton, CompareTitle, ComparisonBody, DEFAULT_TAB, GuardrailsNote, isCompareTab, MissingNotice, placeName, useTopNavOffset, type CompareTab, type MissingName} from '../components/Comparison';
import {FilteredEmpty, LoadMore, OffBallotChip, PickFooter, PickHero, SearchField} from '../components/Picker';
import {CandidateCard} from '../components/cv/CandidateCard';
import {CompareTray} from '../components/cv/CompareTray';
import {SlidingTabs} from '../components/cv/SlidingTabs';
import {StatePill} from '../components/cv/StatePill';
import {compareParams, loadPreloaded, MAX_MARKED, mergePreloaded, MIN_MARKED, parseSqList} from '../lib/marking';
import {pairAfterRemoval, type Pair} from '../lib/pair';
import {cvTokens} from '../themes/cde';

const MAX = MAX_MARKED;
const MIN = MIN_MARKED;
const PAGE = 50;
/** Search text in the unified field that goes to `by-number` instead of `name` (spec 5.4.1). */
const NUMBER_QUERY = /^\d{2,5}$/;
/** A name search with no result is retried as a party acronym when the text is this short. */
const PARTY_FALLBACK_MAX = 12;

/** What the list is filtered by; remembered so "Carregar mais" repeats the same call. */
type ListFilter = {name?: string; party?: string};
type NumberHit = {kind: 'found'; number: string; c: CandidateListItem} | {kind: 'none'; number: string};
/** The call that failed, so "Tentar de novo" repeats it. The choice screen words every failure
 *  with the phrases of spec 5.11 and never shows the service's message, `not_found.reason` or
 *  `guidance` (some name MCP tools). */
type FailedCall = 'first' | 'more' | 'number';
/** How the comparison call failed (Tela 2 spec 5.11): a 400 for more than four `sq`, or
 *  anything else, each with its own phrase; the service's message never reaches the screen. */
type CompareFailure = 'too_many' | 'other';

export function ComparePage({params}: {params: URLSearchParams}) {
  // Route state: uf, office and the compared sq list live in the hash, so a comparison is a link.
  const initialUf = params.get('uf') || 'SP';
  const initialOffice = (params.get('office') as Office) || officesFor(initialUf)[0];
  // `sq` in the order of marking (Tela 1 writes it so): with two or more the page opens in
  // comparison mode and that order is the slot colour of each candidacy (Tela 2 spec 4.1).
  const initialSq = parseSqList(params.get('sq'));
  // `marcar`: the picker opens with these candidacies already marked, in this order (the
  // comparison's "Escolher outras", Tela 2 spec 3; the profile's "Comparar com outras" sends one `sq`).
  const initialMarcar = parseSqList(params.get('marcar'));
  const initialPair = parseSqList(params.get('pair'));
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
  // The candidacies the comparison asks for, by sq_candidato, in the order of marking; one call
  // to compare_candidates answers them all (in ballot order).
  const [compareSq, setCompareSq] = useState<number[]>(initialSq.length >= MIN ? initialSq : []);
  const [comparison, setComparison] = useState<Envelope<ComparisonData> | null>(null);
  const [compareFailure, setCompareFailure] = useState<CompareFailure | null>(null);
  // Bumped by "Tentar de novo" after a failed comparison call.
  const [compareAttempt, setCompareAttempt] = useState(0);
  // Ballot name and number of the requested candidacies the service left out, to name them in the notice.
  const [missingNames, setMissingNames] = useState<Map<number, MissingName>>(new Map());
  // The two candidacies on screen in pair mode on phones; kept in the URL so the link reproduces the screen.
  const [pair, setPair] = useState<Pair | null>(initialPair.length === 2 ? [initialPair[0], initialPair[1]] : null);
  // The open tab of the comparison, also kept in the URL (values unchanged from the first version).
  const [tab, setTab] = useState<CompareTab | null>(isCompareTab(initialTab) ? initialTab : null);
  const topNav = useTopNavOffset();
  const reqId = useRef(0);
  const appliedFilter = useRef<ListFilter>({});
  const touched = useRef(new Set<number>());
  const preloadContext = useRef(0);

  const officeOptions = useMemo(() => officesFor(uf).map(o => ({value: o, label: OFFICE_SHORT[o]})), [uf]);
  // Keep office valid for the UF (the old page defaulted to "presidente" and errored for states).
  const onUf = (v: string) => { preloadContext.current++; touched.current.clear(); setUf(v); const ok = officesFor(v); if (!ok.includes(office)) setOffice(ok[0]); setSelected(new Map()); };
  const onOffice = (v: Office) => { preloadContext.current++; touched.current.clear(); setOffice(v); setSelected(new Map()); };

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
  useEffect(() => { if (view === 'pick') void fetchFirst(); }, [fetchFirst, view]);

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

  // A link that opens the picker with candidacies already marked: `marcar=a,b,c` (the
  // comparison's "Escolher outras") or a single `sq` (the profile's "Comparar com outras").
  // Load them by profile, in the link's order (the order of marking), at most MAX of them.
  useEffect(() => {
    if (view !== 'pick') return;
    const preload = (initialSq.length ? initialSq : initialMarcar).slice(0, MAX);
    if (!preload.length) return;
    let alive = true;
    const context = preloadContext.current;
    loadPreloaded(preload, async sq => (await api.candidate(sq)).data?.candidate ?? null).then(profiles => {
      if (!alive || context !== preloadContext.current) return;
      setSelected(prev => context === preloadContext.current ? mergePreloaded(preload, profiles, prev, touched.current) : prev);
    });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The order of marking: the tray's slot colours and the exit link follow it (spec 4.1), so
  // the comparison screen can paint each candidacy with the same colour.
  const marked = useMemo(() => Array.from(selected.values()), [selected]);
  const toggle = (c: CandidateListItem) => { touched.current.add(c.sq_candidato); setSelected(prev => {
    const m = new Map(prev);
    if (m.has(c.sq_candidato)) m.delete(c.sq_candidato);
    else { if (m.size >= MAX) return prev; m.set(c.sq_candidato, c); }
    return m;
  }); };
  const unmark = (sq: number) => { touched.current.add(sq); setSelected(prev => { const m = new Map(prev); m.delete(sq); return m; }); };
  const clearSearch = () => { setQuery(''); setAll(false); };

  const compare = () => {
    navigate('/', compareParams(uf, office, marked));
    setCompareSq(marked.map(c => c.sq_candidato));
    setView('compare');
  };

  // ---- Comparison mode (Tela 2): data -------------------------------------------------------
  const compareKey = compareSq.join(',');
  useEffect(() => {
    if (view !== 'compare') return;
    if (compareSq.length < MIN) { setView('pick'); return; }
    let alive = true;
    setComparison(null); setCompareFailure(null); setMissingNames(new Map());
    api.compare({uf, office, sq: compareSq}).then(env => {
      if (!alive) return;
      setComparison(env);
      const missing = env.data?.missing ?? [];
      if (missing.length) {
        // Only to name them in the notice; a profile that fails or is not found leaves the generic wording.
        Promise.all(missing.map(m => api.candidate(m.requested).then(e => e.data?.candidate, () => undefined))).then(cs => {
          if (!alive) return;
          setMissingNames(new Map(cs.flatMap(c => c ? [[c.sq_candidato, {ballot_name: c.ballot_name, number: c.number}] as [number, MissingName]] : [])));
        });
      }
    }).catch(e => {
      if (!alive) return;
      setCompareFailure(e instanceof ApiError && e.status === 400 && compareSq.length > MAX ? 'too_many' : 'other');
    });
    return () => { alive = false; };
    // compareKey stands for compareSq; uf and office only change in the picker.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, compareKey, compareAttempt]);

  // "Tirar da comparação" (wide screens, more than two columns): the same comparison without it.
  const removeFromComparison = (sq: number) => {
    setCompareSq(prev => prev.filter(x => x !== sq));
    setPair(prev => pairAfterRemoval(comparison?.data?.candidates ?? [], prev, sq));
  };

  // Bringing a candidacy in, swapping a column or changing the tab must not remount the page
  // (the route key is the hash), so `sq`, `pair` and `tab` go in with replaceState. The review
  // variants of the first layout (`layout`, `dest`) are gone and leave the URL.
  useEffect(() => {
    if (view !== 'compare') return;
    const q = new URLSearchParams(location.hash.replace(/^#\/?\??/, ''));
    q.set('sq', compareKey);
    if (pair) q.set('pair', pair.join(',')); else q.delete('pair');
    if (tab) q.set('tab', tab); else q.delete('tab');
    q.delete('layout'); q.delete('dest');
    history.replaceState(null, '', `#/?${q}`);
  }, [pair, tab, view, compareKey]);

  if (view === 'compare') {
    const data = comparison?.data;
    const round = data?.round ?? comparison?.election?.round.number ?? null;
    const shareUrl = `${location.origin}${location.pathname}${location.search}${href('/', {uf, office, sq: compareKey, pair: pair?.join(','), tab})}`;
    const share = {
      title: `Compare o voto · ${OFFICE[office]} · ${placeName(uf)}`,
      text: `Compare as candidaturas a ${OFFICE[office]} (${uf}) lado a lado, com os dados abertos do TSE: ${shareUrl}`,
      url: shareUrl,
    };
    const toPicker = () => navigate('/', {uf, office});
    const choose = {label: 'Escolher candidaturas', onClick: toPicker};
    let body: ReactNode;
    if (compareFailure === 'too_many') body = <CompareProblem title="Escolha de 2 a 4 candidaturas para comparar." action={choose} />;
    else if (compareFailure) body = <CompareProblem title="Não foi possível montar a comparação agora." text="Tente de novo em instantes." action={{label: 'Tentar de novo', onClick: () => setCompareAttempt(n => n + 1)}} />;
    else if (!comparison) body = <CompareSkeleton />;
    else if (!data || data.candidates.length < MIN) body = (!data && comparison.not_found?.reason !== 'candidaturas_insuficientes')
      ? <CompareProblem title="Não encontramos essa comparação" text="Volte e escolha as candidaturas de novo." action={choose} />
      : <CompareProblem title="Não há candidaturas suficientes para comparar" text="Marque pelo menos 2 candidaturas do mesmo cargo e estado." action={choose} />;
    else body = (
      <>
        {data.missing.length ? <MissingNotice missing={data.missing} names={missingNames} /> : null}
        <ComparisonBody candidates={data.candidates} sqOrder={compareSq} pair={pair} onPairChange={setPair} tab={tab ?? DEFAULT_TAB} onTabChange={setTab} onRemove={removeFromComparison} profileContext={{uf, office}} />
        <GuardrailsNote />
      </>
    );
    return (
      <div className="page cv-page comp" style={{...cvTokens, '--cv-topnav': `${topNav}px`} as CSSProperties}>
        <CompareBar backHref={href('/', {uf, office, marcar: compareKey})} share={share} />
        <CompareTitle office={office} uf={uf} round={round} />
        {comparison?.warnings.length ? <div className="comp-warn"><Warnings warnings={comparison.warnings} /></div> : null}
        {body}
        {comparison ? <CompareFoot source={comparison.source} election={comparison.election} assetsSource={data?.assets_source} /> : null}
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
        badges={flagged ? <><StatusBadge status={c.adjudication_status} />{!c.on_ballot ? <StatusBadge status="Fora da urna" kind="bad" /> : null}</> : undefined} />
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
