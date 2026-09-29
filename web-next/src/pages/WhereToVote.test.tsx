// @vitest-environment happy-dom
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {WhereToVotePage} from './WhereToVote';

(globalThis as {IS_REACT_ACT_ENVIRONMENT?: boolean}).IS_REACT_ACT_ENVIRONMENT = true;

describe('where-to-vote result', () => {
  let root: Root;
  let host: HTMLDivElement;

  afterEach(async () => {
    if (root) await act(() => root.unmount());
    host?.remove();
    vi.unstubAllGlobals();
  });

  it('shows the place without a blocked badge when the API reports blocked status', async () => {
    location.hash = '#/onde-voto?uf=AC&zone=9&section=1';
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      data: {
        municipality: {tse_code: '1200401', ibge_code: null, name: 'Rio Branco', uf: 'AC'},
        round: 1, zone: 9, section: 1, section_kind: 'principal', votes_at_section: 1,
        voters_in_section: 100, accessibility: 'com_acessibilidade', previous_place: null,
        place: {
          number: 41, name: 'ESCOLA CENTRO', kind: 'Escola', address: 'RUA DAS FLORES, 10',
          neighborhood: 'CENTRO', postal_code: '', phone: null, latitude: -9.9, longitude: -67.8,
          status: 'bloqueado', section_count: 1, accessible_section_count: 1,
        },
      },
      not_found: null, warnings: [], election: null,
      source: {kind: 'dataset', attribution: 'TSE', license: 'CC-BY'},
    }), {status: 200})));
    host = document.body.appendChild(document.createElement('div'));
    root = createRoot(host);
    await act(async () => {root.render(<WhereToVotePage />);});

    expect(host.textContent).toContain('Escola Centro');
    expect(host.textContent).toContain('Com acessibilidade');
    expect(host.textContent).not.toContain('Local bloqueado pelo TSE');
  });
});
