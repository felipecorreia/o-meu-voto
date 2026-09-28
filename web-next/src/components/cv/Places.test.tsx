import {describe, expect, it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import type {PollingPlace} from '../../api';
import {mapsUrl} from '../../lib/links';
import {appendPlacesPage} from '../../lib/placePages';
import {LoadMore} from './LoadMore';
import {PlaceCard} from './PlaceCard';
import {SearchSummaryPill} from './SearchSummaryPill';

const place = {
  number: 41, name: 'ESCOLA CENTRO', address: 'RUA DAS FLORES, 10', neighborhood: 'CENTRO',
  latitude: -9.9, longitude: -67.8, zone: 9, section_count: 1, accessible_section_count: 1,
  status: 'bloqueado', distance_km: 0.4,
} as PollingPlace;
const municipality = {name: 'Rio Branco', uf: 'AC'};

describe('places by city', () => {
  it('links each place to its zone and Google Maps, preserving the original accessible name', () => {
    const html = renderToStaticMarkup(<PlaceCard place={place} showDistance uf="AC" municipality={municipality} />);
    expect(html).toContain('href="#/onde-voto?uf=AC&amp;zone=9"');
    expect(html).toContain('aria-label="ESCOLA CENTRO"');
    expect(html).toContain('Escola Centro');
    expect(html).toContain('0,4 km');
    expect(html).toContain('1 seção');
    expect(html).toContain('Local bloqueado pelo TSE');
    expect(html).toContain('target="_blank" rel="noopener"');
    expect(html).toContain('query=-9.9%2C-67.8');
  });
  it('uses an address for the map when coordinates are unavailable', () => {
    const url = mapsUrl({...place, latitude: null, longitude: null, municipality});
    expect(new URL(url).searchParams.get('query')).toBe('RUA DAS FLORES, 10, CENTRO, Rio Branco - AC');
  });
  it('announces added places and stops offering another page at the end', () => {
    const more = renderToStaticMarkup(<LoadMore shown={40} total={45} loading={false} onMore={() => {}} added={20} />);
    expect(more).toContain('Mostrando 40 de 45');
    expect(more).toContain('Carregar mais 5');
    expect(more).toContain('Mais 20 locais carregados.');
    const done = renderToStaticMarkup(<LoadMore shown={45} total={45} loading={false} onMore={() => {}} />);
    expect(done).not.toContain('<button');
  });
  it('loads every place through an API that honors offset, 20 at a time', async () => {
    const all = Array.from({length: 45}, (_, index) => ({...place, number: index + 1}));
    const calls: Array<[number, number]> = [];
    const fakeApi = async (offset: number, limit: number) => {
      calls.push([offset, limit]);
      return all.slice(offset, offset + limit);
    };
    const second = await appendPlacesPage(all.slice(0, 20), fakeApi);
    const last = await appendPlacesPage(second.places, fakeApi);
    expect(calls).toEqual([[20, 20], [40, 20]]);
    expect([second.added, last.added]).toEqual([20, 5]);
    expect(last.places.map(item => item.number)).toEqual(all.map(item => item.number));
    expect(renderToStaticMarkup(<LoadMore shown={last.places.length} total={all.length} loading={false} onMore={() => {}} />)).not.toContain('<button');
  });
  it('names the summary edit action with city, count, filter and order', () => {
    const html = renderToStaticMarkup(<SearchSummaryPill title="Rio Branco · AC" caption="233 locais · com filtro · de A a Z" onEdit={() => {}} />);
    expect(html).toContain('aria-label="Editar busca: Rio Branco · AC, 233 locais · com filtro · de A a Z"');
  });
});
