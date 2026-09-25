import {useMemo, useState, type FormEvent} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Selector} from '@astryxdesign/core/Selector';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Typeahead} from '@astryxdesign/core/Typeahead';
import {Text} from '@astryxdesign/core/Text';
import {Badge} from '@astryxdesign/core/Badge';
import {LocateFixed, MapPin, Search} from 'lucide-react';
import {api, type Envelope, type MunicipalityMatch, type PollingPlacesData} from '../api';
import {UFS} from '../labels';
import {cep, gmapsUrl, joinAddress, plural} from '../format';
import {ErrorState, Loading, NotFoundState, PageHeader, SourceFooter, Warnings} from '../components/common';

const UF_OPTIONS = [...UFS.map(([v, l]) => ({value: v, label: `${v} · ${l}`})), {value: 'ZZ', label: 'ZZ · Exterior'}];
interface MuniItem { id: string; label: string; auxiliaryData: MunicipalityMatch }

export function PlacesPage() {
  const [uf, setUf] = useState('SP');
  const [muni, setMuni] = useState<MuniItem | null>(null);
  const [neighborhood, setNeighborhood] = useState('');
  const [query, setQuery] = useState('');
  const [geo, setGeo] = useState<{lat: string; lon: string} | null>(null);
  const [geoMsg, setGeoMsg] = useState<string | null>(null);
  const [env, setEnv] = useState<Envelope<PollingPlacesData> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const searchSource = useMemo(() => ({
    async search(q: string): Promise<MuniItem[]> {
      const r = await api.municipalities(q, uf, 8);
      return (r.data?.municipalities ?? []).map(m => ({id: m.tse_code, label: `${m.name} (${m.uf})`, auxiliaryData: m}));
    },
    bootstrap: () => [] as MuniItem[],
  }), [uf]);

  const run = async (g: {lat: string; lon: string} | null) => {
    if (!muni) return;
    setLoading(true); setError(null); setEnv(null);
    try { setEnv(await api.pollingPlaces({uf, municipality: muni.auxiliaryData.tse_code, neighborhood: neighborhood || undefined, query: query || undefined, lat: g?.lat, lon: g?.lon, limit: 20})); }
    catch (err) { setError(String((err as Error).message ?? err)); }
    finally { setLoading(false); }
  };
  const submit = (e: FormEvent) => { e.preventDefault(); void run(geo); };
  const near = () => {
    if (!navigator.geolocation) { setGeoMsg('Este navegador não informa a localização.'); return; }
    setGeoMsg('Pedindo a localização ao navegador…');
    navigator.geolocation.getCurrentPosition(p => {
      const g = {lat: p.coords.latitude.toFixed(5), lon: p.coords.longitude.toFixed(5)};
      setGeo(g); setGeoMsg('Ordenado pela distância até você. A localização foi usada uma vez e não fica guardada.');
      void run(g);
    }, () => setGeoMsg('Sem permissão para a localização; a lista segue em ordem alfabética.'), {timeout: 8000});
  };

  const d = env?.data;
  return (
    <div className="page">
      <PageHeader title="Locais de votação da minha cidade" lead="Para quem não sabe a zona e a seção. Filtre por bairro, pelo nome do local ou pelo endereço, ou ordene pelos mais próximos." />
      <Card padding={3} elevation="none">
        <form onSubmit={submit} className="form">
          <div className="form-row">
            <Selector label="UF" options={UF_OPTIONS} value={uf} onChange={v => { setUf(v); setMuni(null); }} hasSearch presentation="adaptive" width="100%" />
            <Typeahead<MuniItem> label="Município" searchSource={searchSource} value={muni} onChange={setMuni} placeholder="ex.: Rio Branco" isRequired minQueryLength={2} emptySearchResultsText="Nenhum município com esse nome" width="100%" />
          </div>
          <div className="form-row">
            <TextInput label="Bairro" value={neighborhood} onChange={setNeighborhood} placeholder="ex.: Centro" isOptional hasClear width="100%" />
            <TextInput label="Nome do local ou endereço" value={query} onChange={setQuery} placeholder="ex.: escola, rua" isOptional hasClear width="100%" />
          </div>
          <div className="actions">
            <Button type="submit" variant="primary" label="Buscar" icon={<Search size={16} aria-hidden />} isLoading={loading} isDisabled={!muni} />
            <Button type="button" variant="secondary" label="Perto de mim" icon={<LocateFixed size={16} aria-hidden />} onClick={near} isDisabled={!muni} tooltip="Ordena pela distância; a localização não sai do navegador" />
          </div>
          {geoMsg ? <Text as="p" size="sm" color="secondary">{geoMsg}</Text> : null}
        </form>
      </Card>
      {error ? <ErrorState message={error} /> : null}
      {loading ? <Loading /> : null}
      {env ? <Warnings warnings={env.warnings} /> : null}
      {env && !d && env.not_found ? <NotFoundState nf={env.not_found} /> : null}
      {d ? (
        <section aria-label="Locais encontrados">
          <div className="bar"><h2 className="h2">{d.municipality.name} - {d.municipality.uf}</h2><Text size="sm" color="secondary">{plural(d.total, 'local', 'locais')}{d.total > d.places.length ? `, mostrando ${d.places.length}` : ''}</Text></div>
          {d.guidance ? <Text as="p" size="sm" color="secondary">{d.guidance}</Text> : null}
          <div className="place-list">
            {d.places.map(p => (
              <Card key={`${p.zone}-${p.number}`} padding={3} elevation="none">
                <div className="place-head">
                  <MapPin size={20} aria-hidden />
                  <div className="place-body">
                    <h3 className="h3">{p.name}</h3>
                    <Text as="p" size="sm">{joinAddress(p.address, p.neighborhood, p.postal_code ? `CEP ${cep(p.postal_code)}` : null)}</Text>
                    <div className="chips chips-compact">
                      {p.zone != null ? <Badge variant="info" label={`Zona ${p.zone}`} /> : null}
                      <Badge variant="neutral" label={`${p.section_count} seções`} />
                      {p.accessible_section_count ? <Badge variant="success" label={`${p.accessible_section_count} com acessibilidade`} /> : null}
                      {p.distance_km != null ? <Badge variant="neutral" label={`${p.distance_km.toFixed(1)} km`} /> : null}
                      {p.status !== 'ativo' ? <Badge variant="warning" label="Bloqueado pelo TSE" /> : null}
                    </div>
                  </div>
                  {p.latitude != null && p.longitude != null ? <Button size="sm" variant="ghost" label="Mapa" icon={<MapPin size={14} aria-hidden />} href={gmapsUrl(p.latitude, p.longitude)} target="_blank" rel="noopener noreferrer" /> : null}
                </div>
              </Card>
            ))}
          </div>
        </section>
      ) : null}
      {env ? <SourceFooter source={env.source} election={env.election} /> : null}
    </div>
  );
}
