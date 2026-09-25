import {useEffect, useState} from 'react';
import {Card} from '@astryxdesign/core/Card';
import {Text} from '@astryxdesign/core/Text';
import {Badge} from '@astryxdesign/core/Badge';
import {Calendar, Clock, Timer} from 'lucide-react';
import {api, type ElectionData, type Envelope} from '../api';
import {OFFICE, type Office} from '../labels';
import {fmtDateLong, fmtWeekday} from '../format';
import {ErrorState, ExternalLink, Loading, PageHeader, SourceFooter, Warnings} from '../components/common';

export function WhenPage() {
  const [env, setEnv] = useState<Envelope<ElectionData> | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.election().then(setEnv).catch(e => setError(String(e.message ?? e))); }, []);
  if (error) return <div className="page"><ErrorState message={error} /></div>;
  if (!env) return <div className="page"><Loading /></div>;
  const d = env.data!;
  return (
    <div className="page">
      <PageHeader title="Quando é a eleição?" lead={`${d.name}: data dos turnos, horário de votação e cargos em disputa.`} />
      <Warnings warnings={env.warnings} />
      <div className="tiles">
        {d.next_round ? (
          <Card padding={4} elevation="none" variant="muted">
            <div className="tile"><Timer size={20} aria-hidden /><span className="tile-big">{d.days_until_next_round}</span><Text size="sm" color="secondary">{d.days_until_next_round === 1 ? 'dia' : 'dias'} para o {d.next_round.number}º turno</Text></div>
          </Card>
        ) : null}
        {d.rounds.map(r => (
          <Card key={r.number} padding={4} elevation="none">
            <div className="tile"><Calendar size={20} aria-hidden /><span className="tile-mid">{fmtDateLong(r.date)}</span><Text size="sm" color="secondary">{r.number}º turno · {fmtWeekday(r.date)}</Text>{r.note ? <Text as="p" size="sm" color="secondary">{r.note}</Text> : null}</div>
          </Card>
        ))}
        <Card padding={4} elevation="none">
          <div className="tile"><Clock size={20} aria-hidden /><span className="tile-mid">{d.voting_hours.label}</span><Text size="sm" color="secondary">o mesmo horário em todo o país</Text></div>
        </Card>
      </div>
      <Card padding={3} elevation="none">
        <Text type="label" weight="semibold" as="p">Cargos em disputa</Text>
        <div className="chips">{d.offices.map(o => <Badge key={o} variant="neutral" label={OFFICE[o as Office] ?? o} />)}</div>
        <ul className="notes">{d.notes.map((n, i) => <li key={i}><Text size="sm">{n}</Text></li>)}</ul>
        <Text as="p" size="sm" color="secondary">Fonte: <ExternalLink href={d.calendar_source.url}>{d.calendar_source.title}</ExternalLink>, verificada em {d.calendar_source.verified_at}.</Text>
      </Card>
      <SourceFooter source={env.source} />
    </div>
  );
}
