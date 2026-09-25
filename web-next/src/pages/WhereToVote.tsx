import {useState, type FormEvent} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Selector} from '@astryxdesign/core/Selector';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Text} from '@astryxdesign/core/Text';
import {Badge} from '@astryxdesign/core/Badge';
import {Banner} from '@astryxdesign/core/Banner';
import {MetadataList, MetadataListItem} from '@astryxdesign/core/MetadataList';
import {MapPin, Search} from 'lucide-react';
import {api, type Envelope, type PollingPlaceData} from '../api';
import {ACCESS, PLACE_STATUS, UFS} from '../labels';
import {cep, gmapsUrl, joinAddress} from '../format';
import {ErrorState, Loading, NotFoundState, PageHeader, SourceFooter, Warnings} from '../components/common';

const UF_OPTIONS = [...UFS.map(([v, l]) => ({value: v, label: `${v} · ${l}`})), {value: 'ZZ', label: 'ZZ · Exterior'}];
const ROUND_OPTIONS = [{value: '', label: 'Próximo turno'}, {value: '1', label: '1º turno'}, {value: '2', label: '2º turno'}];

export function WhereToVotePage() {
  const [uf, setUf] = useState('SP');
  const [zone, setZone] = useState('');
  const [section, setSection] = useState('');
  const [round, setRound] = useState('');
  const [env, setEnv] = useState<Envelope<PollingPlaceData> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true); setError(null); setEnv(null);
    try { setEnv(await api.pollingPlace({uf, zone, section, round: round || undefined})); }
    catch (err) { setError(String((err as Error).message ?? err)); }
    finally { setLoading(false); }
  };

  const d = env?.data;
  return (
    <div className="page">
      <PageHeader title="Onde eu voto?" lead="Digite a UF, a zona e a seção impressas no seu título ou no e-Título. Não pedimos nome, CPF nem número do título." />
      <Card padding={3} elevation="none">
        <form onSubmit={submit} className="form">
          <div className="form-row form-row-4">
            <Selector label="UF" options={UF_OPTIONS} value={uf} onChange={setUf} hasSearch presentation="adaptive" width="100%" />
            <TextInput label="Zona eleitoral" value={zone} onChange={setZone} placeholder="ex.: 009" isRequired width="100%" />
            <TextInput label="Seção" value={section} onChange={setSection} placeholder="ex.: 0422" isRequired width="100%" />
            <Selector label="Turno" options={ROUND_OPTIONS} value={round} onChange={setRound} presentation="adaptive" width="100%" />
          </div>
          <div className="actions"><Button type="submit" variant="primary" label="Buscar" icon={<Search size={16} aria-hidden />} isLoading={loading} /></div>
        </form>
      </Card>
      {error ? <ErrorState message={error} /> : null}
      {loading ? <Loading /> : null}
      {env ? <Warnings warnings={env.warnings} /> : null}
      {env && !d && env.not_found ? <NotFoundState nf={env.not_found} /> : null}
      {d ? (
        <Card padding={4} elevation="none">
          {d.previous_place ? <Banner status="warning" title="O local mudou" description={`Antes: ${d.previous_place.name}, ${d.previous_place.address} (nº ${d.previous_place.number}).`} container="card" elevation="none" collapsible={false} /> : null}
          <div className="place-head">
            <MapPin size={22} aria-hidden />
            <div>
              <h2 className="h2">{d.place.name}</h2>
              <Text as="p">{joinAddress(d.place.address, d.place.neighborhood)}</Text>
              <Text as="p" color="secondary">{joinAddress(`${d.municipality.name} - ${d.municipality.uf}`, d.place.postal_code ? `CEP ${cep(d.place.postal_code)}` : null)}</Text>
            </div>
          </div>
          <div className="chips chips-compact">
            <Badge variant="info" label={`Zona ${d.zone} · Seção ${d.section}`} />
            <Badge variant={d.accessibility === 'com_acessibilidade' ? 'success' : 'neutral'} label={ACCESS[d.accessibility] ?? d.accessibility} />
            <Badge variant={d.place.status === 'ativo' ? 'neutral' : 'warning'} label={PLACE_STATUS[d.place.status] ?? d.place.status} />
            {d.section_kind === 'agregada' ? <Badge variant="warning" label={`Seção agregada: vota na seção ${d.votes_at_section}`} /> : null}
          </div>
          <MetadataList columns="multi" label={{position: 'top'}}>
            <MetadataListItem label="Tipo do local">{d.place.kind}</MetadataListItem>
            <MetadataListItem label="Seções no local">{d.place.section_count} ({d.place.accessible_section_count} com acessibilidade)</MetadataListItem>
            <MetadataListItem label="Eleitores na seção">{d.voters_in_section}</MetadataListItem>
            <MetadataListItem label="Telefone">{d.place.phone ?? '—'}</MetadataListItem>
          </MetadataList>
          {d.place.latitude != null && d.place.longitude != null ? <div className="actions"><Button variant="secondary" label="Abrir no Google Maps" icon={<MapPin size={16} aria-hidden />} href={gmapsUrl(d.place.latitude, d.place.longitude)} target="_blank" rel="noopener noreferrer" /></div> : null}
        </Card>
      ) : null}
      {env ? <SourceFooter source={env.source} election={env.election} /> : null}
    </div>
  );
}
