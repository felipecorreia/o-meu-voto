import {useEffect, useRef, useState, type CSSProperties, type FormEvent} from 'react';
import {ArrowDownAZ, LockKeyhole, LocateFixed, MapPin, Search, SearchX, TriangleAlert, LoaderCircle} from 'lucide-react';
import {api, callApi, type Envelope, type MunicipalityMatch, type PollingPlacesData} from '../api';
import {ufName} from '../labels';
import {href} from '../router';
import {cvTokens} from '../themes/cde';
import {useMedia} from '../lib/useMedia';
import {POLLING_UF_OPTIONS} from '../lib/pollingPlace';
import {appendPlacesPage, PLACES_PAGE_SIZE} from '../lib/placePages';
import {SourceFooter} from '../components/common';
import {ComboField} from '../components/cv/ComboField';
import {CvEmptyState} from '../components/cv/CvEmptyState';
import {FloatingBar} from '../components/cv/FloatingBar';
import {InsetField} from '../components/cv/InsetField';
import {LoadingState} from '../components/cv/LoadingState';
import {LoadMore} from '../components/cv/LoadMore';
import {NoticeBanner} from '../components/cv/NoticeBanner';
import {PlaceCard} from '../components/cv/PlaceCard';
import {SearchSummaryPill} from '../components/cv/SearchSummaryPill';
import {SlidingTabs} from '../components/cv/SlidingTabs';
import {StatePill} from '../components/cv/StatePill';

type View = 'form' | 'loading' | 'list' | 'empty' | 'not_found' | 'error';
type Order = 'alpha' | 'near';
type LocationNotice = 'none' | 'asking' | 'success' | 'denied' | 'unavailable';
type Selection = {code: string; name: string};
type SearchValues = {uf: string; municipality: Selection; neighborhood: string; query: string};
type Geo = {lat: string; lon: string};
const validUf = (uf: string) => POLLING_UF_OPTIONS.some(option => option.value === uf) ? uf : 'SP';
const urlValues = () => {
  const params = new URLSearchParams(location.hash.split('?')[1] ?? '');
  return {uf: validUf(params.get('uf') ?? 'SP'), code: params.get('mun') ?? '', neighborhood: params.get('bairro') ?? '', query: params.get('q') ?? ''};
};
const countLabel = (n: number) => `${n} ${n === 1 ? 'local' : 'locais'}`;

export function PlacesPage() {
  const initial = urlValues();
  const [uf, setUf] = useState(initial.uf);
  const [municipality, setMunicipality] = useState<Selection | null>(initial.code ? {code: initial.code, name: ''} : null);
  const [municipalityText, setMunicipalityText] = useState('');
  const [neighborhood, setNeighborhood] = useState(initial.neighborhood);
  const [query, setQuery] = useState(initial.query);
  const [suggestions, setSuggestions] = useState<MunicipalityMatch[]>([]);
  const [suggestionStatus, setSuggestionStatus] = useState<'idle' | 'loading' | 'empty' | 'error'>('idle');
  const [submitted, setSubmitted] = useState<SearchValues | null>(null);
  const [view, setView] = useState<View>(initial.code ? 'loading' : 'form');
  const [env, setEnv] = useState<Envelope<PollingPlacesData> | null>(null);
  const [places, setPlaces] = useState<PollingPlacesData['places']>([]);
  const [order, setOrder] = useState<Order>('alpha');
  const [notice, setNotice] = useState<LocationNotice>('none');
  const [moreLoading, setMoreLoading] = useState(false);
  const [added, setAdded] = useState(0);
  const desktop = useMedia('(min-width: 1024px)');
  const headingRef = useRef<HTMLHeadingElement>(null);
  const municipalityRef = useRef<HTMLInputElement>(null);
  const firstNewCardRef = useRef<HTMLElement>(null);
  const requestId = useRef(0);
  const geoRef = useRef<Geo | null>(null);
  const shown = places.length;
  const data = env?.data;
  const showForm = desktop || view === 'form';

  useEffect(() => {
    if (municipality || municipalityText.trim().length < 2) {
      setSuggestions([]); setSuggestionStatus('idle'); return;
    }
    let live = true;
    setSuggestionStatus('loading');
    const timer = window.setTimeout(async () => {
      try {
        const answer = await api.municipalities(municipalityText.trim(), uf, 8);
        if (!live) return;
        const matches = answer.data?.municipalities ?? [];
        setSuggestions(matches); setSuggestionStatus(matches.length ? 'idle' : 'empty');
      } catch {
        if (live) {setSuggestions([]); setSuggestionStatus('error');}
      }
    }, 250);
    return () => {live = false; window.clearTimeout(timer);};
  }, [municipalityText, municipality, uf]);

  async function runSearch(values: SearchValues, geo: Geo | null = null, updateUrl = false) {
    const id = ++requestId.current;
    setSubmitted(values); setEnv(null); setPlaces([]); setAdded(0); setView('loading');
    if (updateUrl) history.replaceState(null, '', href('/locais', {uf: values.uf, mun: values.municipality.code, bairro: values.neighborhood || undefined, q: values.query || undefined}));
    try {
      const answer = await api.pollingPlaces({uf: values.uf, municipality: values.municipality.code, neighborhood: values.neighborhood || undefined, query: values.query || undefined, lat: geo?.lat, lon: geo?.lon, limit: PLACES_PAGE_SIZE});
      if (id !== requestId.current) return;
      setEnv(answer);
      if (!answer.data) {setView('not_found'); return;}
      const name = answer.data.municipality.name;
      setSubmitted({...values, municipality: {code: values.municipality.code, name}});
      setMunicipality({code: values.municipality.code, name});
      setMunicipalityText(`${name} (${answer.data.municipality.uf})`);
      setPlaces(answer.data.places);
      setView(answer.data.places.length ? 'list' : values.neighborhood || values.query ? 'empty' : 'not_found');
    } catch {
      if (id === requestId.current) setView('error');
    }
  }

  useEffect(() => {
    const openUrl = () => {
      if (location.hash.split('?')[0] !== '#/locais') return;
      const next = urlValues();
      ++requestId.current;
      setUf(next.uf); setNeighborhood(next.neighborhood); setQuery(next.query);
      setOrder('alpha'); setNotice('none'); geoRef.current = null;
      if (next.code) {
        const values = {uf: next.uf, municipality: {code: next.code, name: ''}, neighborhood: next.neighborhood, query: next.query};
        setMunicipality(values.municipality); setMunicipalityText('');
        void runSearch(values);
      } else {
        setMunicipality(null); setMunicipalityText(''); setSubmitted(null); setEnv(null); setPlaces([]); setView('form');
        if (location.hash.includes('?')) requestAnimationFrame(() => municipalityRef.current?.focus());
      }
    };
    openUrl();
    window.addEventListener('hashchange', openUrl);
    return () => {++requestId.current; window.removeEventListener('hashchange', openUrl);};
  }, []);

  useEffect(() => {
    if (view === 'list' || view === 'empty' || view === 'not_found' || view === 'error') headingRef.current?.focus();
  }, [view]);

  const pick = (match: MunicipalityMatch) => {
    setMunicipality({code: match.tse_code, name: match.name});
    setMunicipalityText(`${match.name} (${match.uf})`);
    setSuggestions([]);
  };
  const edit = () => {
    ++requestId.current;
    setView('form');
    requestAnimationFrame(() => municipalityRef.current?.focus());
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!municipality) return;
    setOrder('alpha'); setNotice('none'); geoRef.current = null;
    void runSearch({uf, municipality, neighborhood, query}, null, true);
  };
  const changeOrder = (next: Order) => {
    if (!submitted || next === order) return;
    if (next === 'alpha') {
      ++requestId.current;
      setOrder('alpha'); setNotice('none'); geoRef.current = null;
      void runSearch(submitted);
      return;
    }
    setOrder('near'); setNotice('asking');
    const id = requestId.current;
    navigator.geolocation.getCurrentPosition(position => {
      if (id !== requestId.current) return;
      const geo = {lat: position.coords.latitude.toFixed(5), lon: position.coords.longitude.toFixed(5)};
      geoRef.current = geo; setNotice('success');
      void runSearch(submitted, geo);
    }, error => {
      if (id !== requestId.current) return;
      setOrder('alpha'); setNotice(error.code === 1 ? 'denied' : 'unavailable');
    }, {timeout: 8000});
  };
  const more = async () => {
    if (!submitted || !data || moreLoading || shown >= data.total) return;
    const id = requestId.current;
    setMoreLoading(true); setAdded(0);
    try {
      const next = await appendPlacesPage(places, async (offset, limit) => {
        const answer = await callApi<PollingPlacesData>('/polling-places', {
          uf: submitted.uf, municipality: submitted.municipality.code,
          neighborhood: submitted.neighborhood || undefined, query: submitted.query || undefined,
          lat: geoRef.current?.lat, lon: geoRef.current?.lon, limit, offset,
        });
        if (!answer.data) throw new Error('Places page unavailable');
        return answer.data.places;
      });
      if (id !== requestId.current) return;
      setPlaces(next.places); setAdded(next.added);
      if (next.places.length >= data.total) requestAnimationFrame(() => firstNewCardRef.current?.focus());
    } catch {
      // Keep the loaded page available; the same control can retry.
    } finally {
      if (id === requestId.current) setMoreLoading(false);
    }
  };
  const clearFilters = () => {
    if (!submitted) return;
    setNeighborhood(''); setQuery('');
    setOrder('alpha'); setNotice('none'); geoRef.current = null;
    void runSearch({...submitted, neighborhood: '', query: ''}, null, true);
  };
  const orderLabel = order === 'alpha' ? 'de A a Z' : 'mais perto primeiro';
  const summary = submitted && data ? `${countLabel(data.total)}${submitted.neighborhood || submitted.query ? ' · com filtro' : ''} · ${orderLabel}`
    : view === 'not_found' ? 'Não achamos locais nesta cidade'
    : view === 'error' ? 'Não foi possível consultar agora'
    : 'Consultando os dados abertos do TSE…';
  const options = [{value: 'alpha' as const, label: 'De A a Z', icon: <ArrowDownAZ size={16} />},
    {value: 'near' as const, label: 'Perto de mim', icon: <LocateFixed size={16} />}].filter(option => option.value === 'alpha' || !!navigator.geolocation);

  const form = <form id="places-search" className="places-form" onSubmit={submit}>
    <header className="places-head"><h1>Locais de votação da <span>sua cidade</span></h1><p>Para quem não sabe a zona e a seção. Escolha a cidade e veja todos os locais.</p></header>
    <StatePill uf={uf} onChange={value => {setUf(value); setMunicipality(null); setMunicipalityText(''); setNeighborhood(''); setQuery('');}} options={POLLING_UF_OPTIONS} />
    <div className="places-fields">
      <ComboField label="Município" value={municipalityText} onInput={value => {setMunicipalityText(value); setMunicipality(null);}} options={suggestions} onPick={pick} status={suggestionStatus} selected={!!municipality} inputRef={municipalityRef} />
      <InsetField label="Bairro" optional value={neighborhood} onChange={setNeighborhood} placeholder="ex.: Centro" inputMode="text" />
      <InsetField label="Nome do local ou endereço" optional value={query} onChange={setQuery} placeholder="ex.: escola, rua" inputMode="text" />
    </div>
    {desktop ? <button className="cv-tray-cta places-search-button" type="submit" disabled={!municipality}><Search size={18} aria-hidden />Ver locais</button> : null}
  </form>;
  const warnings = env?.warnings.map((text, index) => <NoticeBanner key={index} tone="wait" text={text} />);
  const body = <div className="places-body">
    {!desktop && view !== 'form' && submitted ? <SearchSummaryPill title={`${submitted.municipality.name || 'Município'} · ${submitted.uf}`} caption={summary} onEdit={edit} /> : null}
    {desktop && view === 'form' ? <CvEmptyState icon={<MapPin size={30} />} title="Os locais aparecem aqui" text="Escolha o município ao lado." /> : null}
    {view === 'loading' ? <LoadingState /> : null}
    {view === 'list' && data ? <>
      <SlidingTabs options={options} value={order} onChange={changeOrder} ariaLabel="Ordem da lista" role="tablist" fill />
      {notice === 'asking' ? <NoticeBanner tone="info" role="status" text="Pedindo a localização ao navegador…" icon={<LoaderCircle className="cv-location-spin" size={20} />} /> : null}
      {notice === 'success' ? <NoticeBanner tone="info" role="status" title="Mais perto de você primeiro" text="A localização foi usada uma vez e não fica guardada." icon={<LockKeyhole size={20} />} /> : null}
      {notice === 'denied' ? <NoticeBanner tone="info" role="status" title="Sem permissão para a localização" text="A lista segue de A a Z." /> : null}
      {notice === 'unavailable' ? <NoticeBanner tone="info" role="status" title="Não foi possível obter a localização" text="A lista segue de A a Z." /> : null}
      {warnings}
      <div className="places-count"><h1 ref={headingRef} tabIndex={-1}>{countLabel(data.total)}</h1><span>{order === 'alpha' ? 'De A a Z' : 'Mais perto primeiro'}</span></div>
      <div className="places-cards">{places.map((place, index) => <PlaceCard key={`${place.zone}-${place.number}`} place={place} showDistance={order === 'near'} uf={submitted?.uf ?? uf} municipality={data.municipality} cardRef={index === shown - added ? firstNewCardRef : undefined} />)}</div>
      <LoadMore shown={shown} total={data.total} loading={moreLoading} onMore={() => void more()} added={added} />
    </> : null}
    {view === 'empty' ? <><CvEmptyState icon={<SearchX size={30} />} headingRef={headingRef} title="Nenhum local com esse filtro" text="Confira o bairro ou o nome, ou veja todos os locais da cidade." action={<button type="button" onClick={clearFilters}>Limpar filtros</button>} />{warnings}</> : null}
    {view === 'not_found' ? <><CvEmptyState icon={<SearchX size={30} />} headingRef={headingRef} title="Não achamos locais nesta cidade" text="Confira o estado e o município e tente de novo." action={<button type="button" onClick={edit}>Corrigir busca</button>} />{warnings}</> : null}
    {view === 'error' ? <CvEmptyState icon={<TriangleAlert size={30} />} headingRef={headingRef} title="Não foi possível consultar agora" text="Tente de novo em instantes." action={<button type="button" onClick={() => submitted && void runSearch(submitted, geoRef.current)}>Tentar de novo</button>} /> : null}
  </div>;
  return <div className={`page cv-page places${!desktop && view === 'form' ? ' places-with-bar' : ''}`} style={cvTokens as CSSProperties}>
    <div className="places-layout">{showForm ? form : null}{desktop || view !== 'form' ? body : null}</div>
    <footer className="places-foot">{env ? <SourceFooter source={env.source} election={env.election} /> : <span>Dados abertos do TSE.</span>}</footer>
    {!desktop && view === 'form' ? <FloatingBar className="places-floating" role="region" aria-label="Buscar locais de votação">
      <span className="cv-tray-text"><span className="cv-tray-title">{municipality?.name || 'Escolha o município'}</span><span className="cv-tray-sub">{uf === 'ZZ' ? 'Exterior' : ufName(uf)}</span></span>
      <button className="cv-tray-cta" type="submit" form="places-search" disabled={!municipality}><Search size={18} aria-hidden />Ver locais</button>
    </FloatingBar> : null}
  </div>;
}
