import {useEffect, useRef, useState, type CSSProperties, type FormEvent} from 'react';
import {ArrowRight, Calendar, ChevronRight, ExternalLink, Map, MapPin, Search, SearchX, TriangleAlert} from 'lucide-react';
import {api, ApiError, type Envelope, type PollingPlaceData} from '../api';
import {ufName} from '../labels';
import {cep} from '../format';
import {href} from '../router';
import {cvTokens} from '../themes/cde';
import {TSE_ONDE_VOTAR_URL} from '../lib/links';
import {numericError, POLLING_ROUNDS, POLLING_UF_OPTIONS, pollingMapsUrl, pollingSearchFromUrl, pollingVotingDate, validPollingSearch, type PollingPlaceSearch} from '../lib/pollingPlace';
import {toTitleCase} from '../lib/titleCase';
import {useMedia} from '../lib/useMedia';
import {SourceFooter} from '../components/common';
import {CvEmptyState} from '../components/cv/CvEmptyState';
import {DetailRow} from '../components/cv/DetailRow';
import {FloatingBar} from '../components/cv/FloatingBar';
import {InsetField} from '../components/cv/InsetField';
import {LinkCard} from '../components/cv/LinkCard';
import {LoadingState} from '../components/cv/LoadingState';
import {NoticeBanner} from '../components/cv/NoticeBanner';
import {NumberPill} from '../components/cv/NumberPill';
import {PlaceHero} from '../components/cv/PlaceHero';
import {SearchSummaryPill} from '../components/cv/SearchSummaryPill';
import {SlidingTabs} from '../components/cv/SlidingTabs';
import {StatePill} from '../components/cv/StatePill';
import {StatusBadge} from '../components/cv/StatusBadge';

type View = 'form' | 'loading' | 'result' | 'not_found' | 'error';
const urlSearch = () => pollingSearchFromUrl(new URLSearchParams(location.hash.split('?')[1] ?? ''));
const stateName = (uf: string) => uf === 'ZZ' ? 'Exterior' : ufName(uf);
const roundName = (round: string) => POLLING_ROUNDS.find(o => o.value === round)!.label;

export function WhereToVotePage() {
  const [search, setSearch] = useState<PollingPlaceSearch>(urlSearch);
  const [submitted, setSubmitted] = useState<PollingPlaceSearch>(urlSearch);
  const [view, setView] = useState<View>(() => validPollingSearch(urlSearch()) ? 'loading' : 'form');
  const [env, setEnv] = useState<Envelope<PollingPlaceData> | null>(null);
  const [serverInvalid, setServerInvalid] = useState(false);
  const desktop = useMedia('(min-width: 1024px)');
  const zoneRef = useRef<HTMLInputElement>(null);
  const sectionRef = useRef<HTMLInputElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const requestId = useRef(0);
  const zoneError = numericError(search.zone) ?? (serverInvalid ? 'Use só números.' : undefined);
  const sectionError = numericError(search.section) ?? (serverInvalid ? 'Use só números.' : undefined);
  const valid = validPollingSearch(search) && !serverInvalid;
  const showForm = desktop || view === 'form';

  async function runSearch(next: PollingPlaceSearch) {
    if (!validPollingSearch(next)) return;
    const id = ++requestId.current;
    setSubmitted(next); setEnv(null); setView('loading'); setServerInvalid(false);
    history.replaceState(null, '', href('/onde-voto', {...next, round: next.round || undefined}));
    try {
      const answer = await api.pollingPlace({...next, round: next.round || undefined});
      if (id !== requestId.current) return;
      setEnv(answer); setView(answer.data ? 'result' : 'not_found');
    } catch (error) {
      if (id !== requestId.current) return;
      if (error instanceof ApiError && error.status === 400) {
        setServerInvalid(true); setView('form'); zoneRef.current?.focus();
      } else setView('error');
    }
  }

  useEffect(() => {
    const openUrl = () => {
      if (location.hash.split('?')[0] !== '#/onde-voto') return;
      const next = urlSearch();
      ++requestId.current;
      setSearch(next); setSubmitted(next); setServerInvalid(false); setEnv(null);
      if (validPollingSearch(next)) void runSearch(next);
      else {
        setView('form');
        if (/^\d+$/.test(next.zone) && !next.section) requestAnimationFrame(() => sectionRef.current?.focus());
      }
    };
    openUrl();
    window.addEventListener('hashchange', openUrl);
    return () => { ++requestId.current; window.removeEventListener('hashchange', openUrl); };
  }, []);

  useEffect(() => {
    if (view === 'result' || view === 'not_found' || view === 'error') headingRef.current?.focus();
  }, [view]);

  const edit = () => {
    ++requestId.current;
    setSearch(submitted); setServerInvalid(false); setView('form');
    // The field mounts on the next render on phones.
    requestAnimationFrame(() => zoneRef.current?.focus());
  };
  const update = (key: keyof PollingPlaceSearch, value: string) => {
    setServerInvalid(false); setSearch(prev => ({...prev, [key]: value}));
  };
  const submit = (e: FormEvent) => { e.preventDefault(); if (valid) void runSearch(search); };
  const d = view === 'result' ? env?.data : null;
  const name = d ? toTitleCase(d.place.name) : '';
  const date = pollingVotingDate(env?.election ?? null);
  const directions = d ? <a className="cv-tray-cta" href={pollingMapsUrl(d)} target="_blank" rel="noopener" aria-label="Como chegar, abre o Google Maps em nova aba">Como chegar<ArrowRight size={18} aria-hidden /></a> : null;
  const zoneLink = (accent = false) => <LinkCard href={href('/locais', {uf: showForm ? search.uf : submitted.uf})} icon={<Map size={20} />} title="Não sei minha zona" caption="Veja os locais de votação da sua cidade" tone={accent ? 'accent' : 'default'} />;

  return <div className={`page cv-page voting${!desktop && (view === 'form' || view === 'result') ? ' voting-with-bar' : ''}`} style={cvTokens as CSSProperties}>
    <div className="voting-layout">
      {showForm ? <form id="polling-search" className="voting-form" onSubmit={submit}>
        <header className="voting-head"><h1>Onde eu <span>voto</span>?</h1><p>Com a zona e a seção do título de eleitor. Não pedimos nome, CPF nem número do título.</p></header>
        <StatePill uf={search.uf} onChange={value => update('uf', value)} label="Estado do título" options={POLLING_UF_OPTIONS} />
        <div className="voting-fields">
          <InsetField label="Zona eleitoral" value={search.zone} onChange={value => update('zone', value)} placeholder="ex.: 009" error={zoneError} inputRef={zoneRef} />
          <InsetField label="Seção" value={search.section} onChange={value => update('section', value)} placeholder="ex.: 0422" error={sectionError} inputRef={sectionRef} />
        </div>
        <div className="voting-round"><span id="polling-round-label">Turno</span><SlidingTabs options={POLLING_ROUNDS} value={search.round} onChange={value => update('round', value)} ariaLabel="Turno" ariaLabelledby="polling-round-label" role="tablist" fill /></div>
        <div className="voting-help">{zoneLink()}<a className="voting-faq" href={href('/duvidas', {abrir: 'zona'})}>Onde acho a zona e a seção?<ChevronRight size={16} aria-hidden /></a></div>
        {desktop ? <button className="cv-tray-cta voting-search" type="submit" disabled={!valid}><Search size={18} aria-hidden />Buscar local</button> : null}
      </form> : null}
      {desktop || view !== 'form' ? <div className="voting-body">
        {!desktop ? <SearchSummaryPill zone={submitted.zone} section={submitted.section} state={stateName(submitted.uf)} round={roundName(submitted.round)} onEdit={edit} /> : null}
        {view === 'form' ? <CvEmptyState icon={<MapPin size={30} />} title="Seu local aparece aqui" text="Preencha a zona e a seção ao lado." /> : null}
        {view === 'loading' ? <LoadingState /> : null}
        {d ? <div className="voting-result cv-voting-enter">
          {d.previous_place ? <NoticeBanner tone="wait" title="O local mudou" text={`Antes esta seção votava em ${d.previous_place.name}.`} /> : null}
          {env?.warnings.map((text, i) => <NoticeBanner key={i} tone="wait" text={text} />)}
          <PlaceHero name={name} originalName={d.place.name} headingRef={headingRef}
            addressLine1={<span aria-label={[d.place.address, d.place.neighborhood].filter(Boolean).join(' · ')}>{[d.place.address, d.place.neighborhood].filter(Boolean).map(toTitleCase).join(' · ')}</span>}
            addressLine2={`${d.municipality.name} - ${d.municipality.uf}${d.place.postal_code ? ` · CEP ${cep(d.place.postal_code)}` : ''}`}
            chips={<><NumberPill n={`Zona ${d.zone} · Seção ${d.section}`} />
              {d.accessibility === 'com_acessibilidade' ? <StatusBadge status="Com acessibilidade" tone="ok" /> : null}
              {/* Issue #45: hide place status until the TSE field's meaning is settled. */}
              {d.section_kind === 'agregada' ? <StatusBadge status={`Seção agregada: vota na seção ${d.votes_at_section}`} tone="neutral" /> : null}</>}
            action={desktop ? directions : undefined} />
          <section className="voting-section" aria-labelledby="polling-details-title"><h2 id="polling-details-title">Sobre o local</h2>
            {d.place.kind ? <DetailRow label="Tipo do local">{d.place.kind}</DetailRow> : null}
            {d.place.section_count != null ? <DetailRow label="Seções neste local" secondary={d.place.accessible_section_count != null ? `${d.place.accessible_section_count} com acessibilidade` : undefined}>{d.place.section_count} seções</DetailRow> : null}
            {d.voters_in_section != null ? <DetailRow label="Eleitores na sua seção">{d.voters_in_section}</DetailRow> : null}
            {d.place.phone ? <DetailRow label="Telefone"><a href={`tel:${d.place.phone}`} className="voting-phone">{d.place.phone}</a></DetailRow> : null}
          </section>
          {date ? <section className="voting-section voting-when" aria-labelledby="polling-date-title"><h2 id="polling-date-title">Quando votar</h2><LinkCard href={href('/quando')} icon={<Calendar size={20} />} title={date.title} caption={date.caption} /></section> : null}
        </div> : null}
        {view === 'not_found' ? <div className="voting-result cv-voting-enter">
          <CvEmptyState icon={<SearchX size={30} />} headingRef={headingRef} title="Não achamos essa seção" text="Confira a zona e a seção no título de eleitor ou no app e-Título e tente de novo." action={<button type="button" onClick={edit}>Corrigir zona e seção</button>} />
          {env?.warnings.map((text, i) => <NoticeBanner key={i} tone="wait" text={text} />)}
          <section className="voting-section voting-paths" aria-labelledby="polling-paths-title"><h2 id="polling-paths-title">Outros caminhos</h2><div>{zoneLink(true)}<LinkCard href={TSE_ONDE_VOTAR_URL} icon={<ExternalLink size={20} />} title="Onde votar, no site do TSE" caption="Serviço oficial, abre em nova aba" /></div></section>
        </div> : null}
        {view === 'error' ? <CvEmptyState icon={<TriangleAlert size={30} />} headingRef={headingRef} title="Não foi possível consultar agora" text="Tente de novo em instantes." action={<button type="button" onClick={() => void runSearch(submitted)}>Tentar de novo</button>} /> : null}
      </div> : null}
    </div>
    <footer className="voting-foot">{env ? <SourceFooter source={env.source} election={env.election} /> : null}</footer>
    {!desktop && view === 'form' ? <FloatingBar className="voting-floating" role="region" aria-label="Buscar local de votação">
      <span className="cv-tray-text"><span className="cv-tray-title">{valid ? `Zona ${search.zone} · Seção ${search.section}` : 'Preencha zona e seção'}</span><span className="cv-tray-sub">{stateName(search.uf)} · {roundName(search.round)}</span></span>
      <button className="cv-tray-cta" type="submit" form="polling-search" disabled={!valid}><Search size={18} aria-hidden />Buscar local</button>
    </FloatingBar> : null}
    {!desktop && d ? <FloatingBar className="voting-floating" role="region" aria-label="Como chegar ao local de votação"><span className="cv-tray-text"><span className="cv-tray-title">{name}</span><span className="cv-tray-sub">Zona {d.zone} · Seção {d.section}</span></span>{directions}</FloatingBar> : null}
  </div>;
}
