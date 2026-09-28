import {useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode} from 'react';
import {Clock, Columns2, ExternalLink, MapPin, TriangleAlert} from 'lucide-react';
import {api, type ElectionData, type Envelope} from '../api';
import {officeChips} from '../labels';
import {href} from '../router';
import {cvTokens} from '../themes/cde';
import {TSE_SITE_URL} from '../lib/links';
import {calendarDay, daysUntil, electionPhase, formatHour, formatRoundDate, formatShortDate, formatVotingHours, formatWeekday, roundTags} from '../lib/electionDates';
import {SourceFooter} from '../components/common';
import {CountdownHero} from '../components/cv/CountdownHero';
import {CvChip} from '../components/cv/CvChip';
import {CvEmptyState} from '../components/cv/CvEmptyState';
import {InfoStrip} from '../components/cv/InfoStrip';
import {LinkCard} from '../components/cv/LinkCard';
import {LoadingState} from '../components/cv/LoadingState';
import {NoticeBanner} from '../components/cv/NoticeBanner';
import {RoundTile} from '../components/cv/RoundTile';

export type WhenView = 'loading' | 'ok' | 'no_data' | 'error';

/** Quando (Tela 6): one `GET /election` on open, the hero driven by the Brasília civil day. */
export function WhenPage() {
  const [env, setEnv] = useState<Envelope<ElectionData> | null>(null);
  const [view, setView] = useState<WhenView>('loading');
  const [now, setNow] = useState(() => new Date());
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setEnv(null); setView('loading');
    try {
      const answer = await api.election();
      if (id !== requestId.current) return;
      setEnv(answer); setView(answer.data ? 'ok' : 'no_data'); setNow(new Date());
    } catch {
      if (id !== requestId.current) return;
      setView('error');
    }
  }, []);

  useEffect(() => { void load(); return () => { ++requestId.current; }; }, [load]);
  // A tab left open from one day to the next recounts when it comes back (spec 5.1: no timer).
  useEffect(() => {
    const onVisible = () => { if (document.visibilityState === 'visible') setNow(new Date()); };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, []);

  return <WhenScreen env={env} view={view} now={now} onRetry={() => void load()} />;
}

const whereToVote = <LinkCard href={href('/onde-voto')} icon={<MapPin size={20} />} title="Onde eu voto?" caption="Ache o local pela zona e pela seção" />;

/** The screen for a given answer and instant, so every phase and state renders without a network. */
export function WhenScreen({env, view, now, onRetry}: {env: Envelope<ElectionData> | null; view: WhenView; now: Date; onRetry: () => void}) {
  const d = view === 'ok' ? env?.data ?? null : null;
  const retry = <button type="button" onClick={onRetry}>Tentar de novo</button>;
  const warnings = env?.warnings.map((text, i) => <NoticeBanner key={i} tone="wait" text={text} />) ?? null;
  return <div className={`page cv-page when${d ? ' when-wide' : ''}`} style={cvTokens as CSSProperties}>
    <header className="when-head"><h1>Quando é a <span>eleição</span>?</h1><p>Eleições Gerais 2026: datas dos turnos, horário de votação e cargos em disputa.</p></header>
    <div className="when-body">
      {view === 'loading' ? <LoadingState /> : null}
      {view === 'error' ? <CvEmptyState icon={<TriangleAlert size={30} />} title="Não foi possível consultar agora" text="Tente de novo em instantes." action={retry} /> : null}
      {view === 'no_data' ? <div className="when-column cv-voting-enter">
        <CvEmptyState icon={<CalendarQuestionIcon />} title="O calendário não carregou" text="O serviço ainda não trouxe as datas desta eleição. Tente de novo em instantes." action={retry} />
        {warnings}
        <section className="when-section when-links" aria-labelledby="when-meanwhile-title"><h2 id="when-meanwhile-title">Enquanto isso</h2>
          <LinkCard href={TSE_SITE_URL} icon={<ExternalLink size={20} />} title="Calendário no site do TSE" caption="Site oficial, abre em nova aba" />
          {whereToVote}
        </section>
      </div> : null}
      {d ? <Calendar data={d} now={now} warnings={warnings} /> : null}
    </div>
    {env && view !== 'loading' ? <footer className="when-foot"><SourceFooter source={env.source} election={env.election} /></footer> : null}
  </div>;
}

function Calendar({data: d, now, warnings}: {data: ElectionData; now: Date; warnings: ReactNode}) {
  const rounds = (d.rounds ?? []).map(r => ({number: r.number, date: calendarDay(r.date)}));
  const hours = formatVotingHours(d.voting_hours);
  const phase = electionPhase(rounds, now, d.voting_hours?.end);
  const tags = roundTags(phase);
  const target = rounds.find(r => r.number === (phase.endsWith('-2') ? 2 : 1));
  const roundLabel = target ? `${target.number}º turno` : '';
  const dateLabel = target?.date ? `${formatWeekday(target.date)}, ${formatRoundDate(target.date)}` : '';
  let hero: ReactNode = null;
  if (target?.date) {
    if (phase === 'before-1' || phase === 'before-2') hero = <CountdownHero variant="count" days={daysUntil(target.date, now)} roundLabel={roundLabel} dateLabel={dateLabel} hours={hours} />;
    else if (phase === 'today-1' || phase === 'today-2') hero = <CountdownHero variant="today" roundLabel={roundLabel} dateLabel={dateLabel} hours={hours} />;
    else if (phase === 'closed-today-1' || phase === 'closed-today-2') hero = <CountdownHero variant="closed" roundLabel={roundLabel} dateLabel={dateLabel} hours={formatHour(d.voting_hours?.end)} />;
    else if (phase === 'after') hero = <CountdownHero variant="after" roundLabel={roundLabel} dateLabel={dateLabel} year={(rounds.find(r => r.number === 2)?.date ?? target.date).slice(0, 4)} />;
  }
  const chips = officeChips(d.offices ?? []);
  const notes = (d.notes ?? []).filter(Boolean);
  const source = d.calendar_source;
  const verified = calendarDay(source?.verified_at);
  return <div className="when-columns">
    <div className="when-column">
      {hero}
      {phase === 'before-2' || phase === 'today-2' ? <NoticeBanner tone="info" title="Só onde houver 2º turno" text="Para presidente e governador, quando ninguém passa de metade dos votos válidos no 1º turno." /> : null}
      {warnings}
      {rounds.length ? <section className="when-section" aria-labelledby="when-rounds-title"><h2 id="when-rounds-title">Turnos</h2>
        <ul className={`cv-roundtiles${rounds.length === 1 ? ' cv-roundtiles-single' : ''}`}>
          {rounds.map(r => { const t = r.number === 1 ? tags.first : tags.second; return <RoundTile key={r.number} roundNumber={r.number} date={r.date} tag={t.tag} highlighted={t.highlighted} />; })}
        </ul>
      </section> : null}
      {hours ? <InfoStrip icon={<Clock size={20} />} title={hours} subtitle="Horário de Brasília, o mesmo em todo o país" /> : null}
    </div>
    <div className="when-column">
      {chips.length || notes.length || source?.url ? <section className="when-section" aria-labelledby={chips.length ? 'when-offices-title' : undefined}>
        {chips.length ? <><h2 id="when-offices-title">Cargos em disputa</h2><ul className="cv-chips">{chips.map(c => <CvChip key={c}>{c}</CvChip>)}</ul></> : null}
        {notes.length ? <ul className="when-notes">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul> : null}
        {source?.url ? <p className="when-source">Fonte: <a href={source.url} target="_blank" rel="noopener">{source.title || source.url}</a>{verified ? `, verificada em ${formatShortDate(verified)}` : ''}.</p> : null}
      </section> : null}
      <section className="when-section when-links" aria-labelledby="when-before-title"><h2 id="when-before-title">Antes de sair de casa</h2>
        {whereToVote}
        <LinkCard href={href('/')} icon={<Columns2 size={20} />} title="Compare as candidaturas" caption="Veja lado a lado o que cada uma declarou" />
      </section>
    </div>
  </div>;
}

/** A calendar with a question mark, which lucide does not ship (the prototype's glyph). */
function CalendarQuestionIcon() {
  return <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <rect x="4" y="5" width="16" height="16" rx="2" /><path d="M16 3v4M8 3v4M4 10h16M10 14.5a2 2 0 1 1 2.5 1.9V17M12 19.5h.01" />
  </svg>;
}
