import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {CheckboxInput} from '@astryxdesign/core/CheckboxInput';
import {Selector} from '@astryxdesign/core/Selector';
import {SelectableCard} from '@astryxdesign/core/SelectableCard';
import {Text} from '@astryxdesign/core/Text';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Badge} from '@astryxdesign/core/Badge';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {ArrowLeft, Columns3, Share2, Users, X} from 'lucide-react';
import {api, type CandidateListItem, type CandidateProfile, type Envelope, type CandidatesData, type Source, type ElectionInfo} from '../api';
import {BALLOT_OFFICES, OFFICE, UFS, officesFor, type Office} from '../labels';
import {href, navigate} from '../router';
import {CandidateAvatar, ErrorState, Loading, NumberBadge, SourceFooter, StatusBadge, Warnings} from '../components/common';
import {CompareGrid, type DestinationStyle, type GrowthStyle, type GridLayout, type Pair} from '../components/CompareGrid';
import {ApiError} from '../api';

const MAX = 4;
const MIN = 2;
const UF_OPTIONS = [{value: 'BR', label: 'Brasil (presidente)'}, ...UFS.map(([v, l]) => ({value: v, label: `${v} · ${l}`}))];

function officeOptions(uf: string) {
  return officesFor(uf).map(o => ({value: o, label: OFFICE[o] + (o === 'deputado_distrital' ? ' (DF)' : '')}));
}

export function ComparePage({params}: {params: URLSearchParams}) {
  // Route state: uf, office and the selected sq list live in the hash, so a comparison is a link.
  const initialUf = params.get('uf') || 'SP';
  const initialOffice = (params.get('office') as Office) || officesFor(initialUf)[0];
  const initialSq = (params.get('sq') || '').split(',').filter(Boolean).map(Number);
  // Presentation switches for the design review (Lavish board questions 17 to 19); defaults are the recommendation.
  const destinationStyle = (params.get('dest') as DestinationStyle) || 'both';
  const growthStyle = (params.get('growth') as GrowthStyle) || 'line';
  // `tabs` (captain, 2026-09-25 evening: "gostei muito mais desse aqui! Vamos focar nessa") is the
  // default; `pair`, `columns` and `stacked` stay reachable for the review until the landing PR.
  const layout = (params.get('layout') as GridLayout) || 'tabs';
  const initialPair = ((params.get('pair') || '').split(',').filter(Boolean).map(Number));
  const initialTab = params.get('tab');

  const [uf, setUf] = useState(initialUf);
  const [office, setOffice] = useState<Office>(BALLOT_OFFICES.includes(initialOffice) ? initialOffice : officesFor(initialUf)[0]);
  const [name, setName] = useState('');
  const [party, setParty] = useState('');
  const [all, setAll] = useState(false);
  const [list, setList] = useState<Envelope<CandidatesData> | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Map<number, CandidateListItem>>(new Map());
  const [view, setView] = useState<'pick' | 'compare'>(initialSq.length >= MIN ? 'compare' : 'pick');
  const [profiles, setProfiles] = useState<CandidateProfile[] | null>(null);
  const [profileMeta, setProfileMeta] = useState<{source: Source; election: ElectionInfo | null; warnings: string[]} | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [booting, setBooting] = useState(initialSq.length > 0);
  const [byNumber, setByNumber] = useState('');
  const [byNumberMsg, setByNumberMsg] = useState<string | null>(null);
  // The two candidacies on screen in the pair layout on phones; kept in the URL so the link reproduces the screen.
  const [pair, setPair] = useState<Pair | null>(initialPair.length === 2 ? [initialPair[0], initialPair[1]] : null);
  // The open tab in the tabbed variant, also kept in the URL.
  const [tab, setTab] = useState<string | null>(initialTab);
  const reqId = useRef(0);

  // Keep office valid for the UF (the old page defaulted to "presidente" and errored for states).
  const onUf = (v: string) => { setUf(v); const ok = officesFor(v); if (!ok.includes(office)) setOffice(ok[0]); setSelected(new Map()); };
  const onOffice = (v: string) => { setOffice(v as Office); setSelected(new Map()); };

  const fetchList = useCallback(async (offset = 0) => {
    const id = ++reqId.current;
    setLoading(true); setListError(null);
    try {
      const env = await api.candidates({uf, office, name: name || undefined, party: party || undefined, on_ballot_only: !all, limit: 50, offset});
      if (id !== reqId.current) return;
      setList(prev => offset && prev?.data && env.data ? {...env, data: {...env.data, candidates: [...prev.data.candidates, ...env.data.candidates]}} : env);
    } catch (e) {
      if (id === reqId.current) { setList(null); setListError(String((e as Error).message ?? e)); }
    } finally { if (id === reqId.current) setLoading(false); }
  }, [uf, office, name, party, all]);

  useEffect(() => { const t = setTimeout(() => { void fetchList(0); }, name || party ? 250 : 0); return () => clearTimeout(t); }, [fetchList, name, party]);

  // Selected candidacies that arrived through the link but are not (yet) in the list: load them by profile.
  useEffect(() => {
    if (!initialSq.length) return;
    let alive = true;
    Promise.all(initialSq.map(sq => api.candidate(sq))).then(envs => {
      if (!alive) return;
      const m = new Map<number, CandidateListItem>();
      for (const e of envs) if (e.data) m.set(e.data.candidate.sq_candidato, e.data.candidate);
      setSelected(m);
    }).catch(() => { /* the picker still works without them */ }).finally(() => { if (alive) setBooting(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedList = useMemo(() => Array.from(selected.values()).sort((a, b) => a.number - b.number), [selected]);
  const toggle = (c: CandidateListItem, on: boolean) => setSelected(prev => {
    const m = new Map(prev);
    if (on) { if (m.size >= MAX) return prev; m.set(c.sq_candidato, c); } else m.delete(c.sq_candidato);
    return m;
  });

  // Question 16 of the research: on a 1,000+ list the voter usually knows the number.
  const addByNumber = async () => {
    const num = byNumber.trim();
    if (!num) return;
    if (selected.size >= MAX) { setByNumberMsg(`Já há ${MAX} marcadas; tire uma para adicionar.`); return; }
    setByNumberMsg(null);
    try {
      const env = await api.candidateByNumber({uf, office, number: num});
      if (env.data) { toggle(env.data.candidate, true); setByNumber(''); setByNumberMsg(`${env.data.candidate.ballot_name} (${num}) marcada.`); }
      else setByNumberMsg(env.not_found?.reason ?? 'Número não encontrado.');
    } catch (e) { setByNumberMsg(e instanceof ApiError ? e.message : String(e)); }
  };

  const compare = () => {
    navigate('/', {uf, office, sq: selectedList.map(c => c.sq_candidato).join(',')});
    setView('compare');
  };

  useEffect(() => {
    if (view !== 'compare' || booting) return;
    const sqs = selectedList.map(c => c.sq_candidato);
    if (sqs.length < MIN) { setView('pick'); return; }
    let alive = true;
    setProfiles(null); setProfileError(null);
    Promise.all(sqs.map(sq => api.candidate(sq))).then(envs => {
      if (!alive) return;
      const ps = envs.map(e => e.data?.candidate).filter((c): c is CandidateProfile => !!c);
      setProfiles(ps);
      setProfileMeta({source: envs[0].source, election: envs[0].election, warnings: Array.from(new Set(envs.flatMap(e => e.warnings)))});
    }).catch(e => { if (alive) setProfileError(String((e as Error).message ?? e)); });
    return () => { alive = false; };
  }, [view, selectedList, booting]);

  // Swapping a column or a tab must not remount the page (the route key is the hash), so both go in with replaceState.
  const paired = layout === 'pair' || layout === 'tabs';
  useEffect(() => {
    if (view !== 'compare' || !paired) return;
    const q = new URLSearchParams(location.hash.replace(/^#\/?\??/, ''));
    if (pair) q.set('pair', pair.join(',')); else q.delete('pair');
    if (layout === 'tabs' && tab) q.set('tab', tab); else q.delete('tab');
    history.replaceState(null, '', `#/?${q}`);
  }, [pair, tab, view, layout, paired]);

  const shareParams = {uf, office, sq: selectedList.map(c => c.sq_candidato).join(','), layout: layout === 'tabs' ? undefined : layout, pair: paired && pair ? pair.join(',') : undefined, tab: layout === 'tabs' && tab ? tab : undefined};
  const shareUrl = `${location.origin}${location.pathname}${location.search}${href('/', shareParams)}`;
  const waHref = `https://wa.me/?text=${encodeURIComponent(`Compare as candidaturas a ${OFFICE[office]} (${uf}) lado a lado, com os dados abertos do TSE: ${shareUrl}`)}`;

  if (view === 'compare') {
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
        {profileMeta ? <Warnings warnings={profileMeta.warnings} /> : null}
        {profileError ? <ErrorState message={profileError} /> : null}
        {!profiles && !profileError ? <Loading label="Montando a comparação…" /> : null}
        {profiles ? <CompareGrid profiles={profiles} destinationStyle={destinationStyle} growthStyle={growthStyle} layout={layout} pair={pair} onPairChange={setPair} tab={tab} onTabChange={setTab} onRemove={sq => setSelected(prev => { const m = new Map(prev); m.delete(sq); return m; })} /> : null}
        <Text as="p" size="sm" color="secondary">Conjunto de campos provisório (pesquisa do comparador, 25/09/2026): identidade, partido e aliança, chapa, registro, destino dos votos, ocupação, bens declarados e evolução em reais, redes e ficha oficial.</Text>
        {profileMeta ? <SourceFooter source={profileMeta.source} election={profileMeta.election} /> : null}
      </div>
    );
  }

  const data = list?.data;
  return (
    <div className="page">
      <header className="page-head hero">
        <div className="ribbons" aria-hidden><span className="rb rb-blue" /><span className="rb rb-green" /><span className="rb rb-gold" /></div>
        <h1 className="h1">Compare as candidaturas antes de votar</h1>
        <p className="lead">Escolha o estado e o cargo, marque de {MIN} a {MAX} candidaturas e veja lado a lado o que cada uma declarou ao TSE.</p>
      </header>

      <Card padding={3} elevation="none">
        <div className="form-row">
          <Selector label="Estado" options={UF_OPTIONS} value={uf} onChange={onUf} hasSearch searchPlaceholder="Buscar UF" presentation="adaptive" width="100%" />
          <Selector label="Cargo" options={officeOptions(uf)} value={office} onChange={onOffice} presentation="adaptive" width="100%" description={uf === 'BR' ? 'Presidente é a única disputa nacional.' : 'Para presidente, escolha Brasil no estado.'} />
        </div>
        <div className="form-row">
          <TextInput label="Nome" value={name} onChange={setName} placeholder="nome de urna ou civil" hasClear isOptional width="100%" />
          <TextInput label="Partido" value={party} onChange={setParty} placeholder="sigla ou número" hasClear isOptional width="100%" />
        </div>
        <CheckboxInput label="Incluir candidaturas fora da urna (registro indeferido, renúncia)" value={all} onChange={setAll} />
        <div className="by-number">
          <TextInput label="Adicionar pelo número da urna" value={byNumber} onChange={setByNumber} placeholder={uf === 'BR' ? 'ex.: 13' : office === 'deputado_federal' ? 'ex.: 1234' : 'ex.: 45'} onEnter={() => void addByNumber()} description="Para listas grandes: digite o número e marque direto, sem procurar na lista." width="100%" />
          <Button variant="secondary" label="Marcar" onClick={() => void addByNumber()} isDisabled={!byNumber.trim()} />
        </div>
        {byNumberMsg ? <Text as="p" size="sm" color="secondary">{byNumberMsg}</Text> : null}
      </Card>

      <section aria-labelledby="pick-title">
        <div className="bar">
          <h2 id="pick-title" className="h2">
            <Users size={18} aria-hidden /> {data ? `${data.total} candidaturas · ${OFFICE[office]} · ${data.round}º turno` : 'Candidaturas'}
          </h2>
          <Badge variant={selected.size >= MIN ? 'success' : 'neutral'} label={`${selected.size} de ${MAX} marcadas`} />
        </div>
        {listError ? <ErrorState message={listError} /> : null}
        {list ? <Warnings warnings={list.warnings} /> : null}
        {loading && !data ? <Loading /> : null}
        {list && !data && list.not_found ? <EmptyState isCompact title={list.not_found.reason} description={list.not_found.guidance} /> : null}
        {data && data.candidates.length === 0 ? <EmptyState isCompact title="Nenhuma candidatura com esse filtro" description="Tente outro nome ou partido, ou inclua as candidaturas fora da urna." /> : null}
        {data ? (
          <div className="pick-grid">
            {data.candidates.map(c => {
              const on = selected.has(c.sq_candidato);
              return (
                <SelectableCard key={c.sq_candidato} label={`${c.ballot_name}, número ${c.number}, ${c.party.acronym}`} isSelected={on} onChange={v => toggle(c, v)} isDisabled={!on && selected.size >= MAX} padding={2} elevation="none">
                  <div className="pick-card">
                    <CandidateAvatar c={c} size="md" />
                    <div className="pick-body">
                      <div className="cmp-head-name"><span className="ballot-name">{c.ballot_name}</span><NumberBadge n={c.number} /></div>
                      <Text size="sm" color="secondary" as="p">{c.party.acronym}{c.occupation ? <> · <span className="sentence">{c.occupation}</span></> : null}</Text>
                      {c.adjudication_status !== 'DEFERIDO' || !c.on_ballot ? <div className="chips chips-compact"><StatusBadge status={c.adjudication_status} />{!c.on_ballot ? <Badge variant="error" label="Fora da urna" /> : null}</div> : null}
                    </div>
                  </div>
                </SelectableCard>
              );
            })}
          </div>
        ) : null}
        {data && data.candidates.length < data.total ? (
          <div className="center"><Button variant="secondary" label={`Carregar mais (${data.candidates.length} de ${data.total})`} isLoading={loading} onClick={() => void fetchList(data.candidates.length)} /></div>
        ) : null}
        {list ? <SourceFooter source={list.source} election={list.election} /> : null}
      </section>

      <div className={`tray ${selected.size ? 'tray-on' : ''}`} role="region" aria-label="Candidaturas marcadas">
        <div className="tray-chips">
          {selectedList.map(c => (
            <span key={c.sq_candidato} className="chip">
              <span className="chip-n">{c.number}</span>{c.ballot_name}
              <button type="button" className="chip-x" aria-label={`Tirar ${c.ballot_name}`} onClick={() => toggle(c, false)}><X size={14} aria-hidden /></button>
            </span>
          ))}
          {!selectedList.length ? <Text size="sm" color="secondary">Marque de {MIN} a {MAX} candidaturas na lista.</Text> : null}
        </div>
        <Button variant="primary" label={selected.size < MIN ? `Comparar (marque ${MIN - selected.size} a mais)` : `Comparar ${selected.size}`} icon={<Columns3 size={16} aria-hidden />} isDisabled={selected.size < MIN} onClick={compare} />
      </div>
    </div>
  );
}
