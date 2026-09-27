import {afterEach, describe, expect, it, vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {CandidatePage} from './Candidate';

const {envelope} = vi.hoisted(() => ({envelope: {
  data: {candidate: {
    sq_candidato: 2, number: 11, ballot_name: 'MARIA SILVA', name: 'Civil name',
    office: 'governador', party: {number: 11, acronym: 'PP', name: 'Party name'},
    federation: null, coalition: null, adjudication_status: 'DEFERIDO', on_ballot: true,
    occupation: null, photo_url: null, vote_destination: null, round: 1,
    social_name: null, nomination_kind: 'partido_isolado', gender: null, race_color: null,
    marital_status: null, education: null, running_mates: [], social_links: [] as string[],
    divulgacandcontas_url: 'https://divulgacandcontas.tse.jus.br/divulga/#/candidato/NORTE/AC/20322002026/2/2026/AC',
  }},
  warnings: [], election: null, source: {kind: 'dataset', attribution: 'TSE', license: 'CC-BY'},
}}));

// Render the loaded API state through the actual profile and its network list.
vi.mock('../api', () => ({api: {}}));
vi.mock('react', async importOriginal => {
  const react = await importOriginal<typeof import('react')>();
  return {...react, useState: <T,>(initial: T | (() => T)) => react.useState(initial === null ? envelope as T : initial)};
});

afterEach(() => { vi.unstubAllGlobals(); });

function render(links: string[]) {
  envelope.data.candidate.social_links = links;
  vi.stubGlobal('location', {href: 'https://example.com/#/candidato/2'});
  vi.stubGlobal('navigator', {});
  return renderToStaticMarkup(<CandidatePage sq={2} backHref="#/candidato/2" />);
}

describe('profile links from normalized REST data', () => {
  it('renders accepted HTTP(S) links and the official LinkCard', () => {
    const html = render(['https://www.instagram.com/candidate', 'http://candidate.com.br/bio']);
    expect(html).toContain('Redes declaradas');
    for (const url of ['https://www.instagram.com/candidate', 'http://candidate.com.br/bio']) {
      expect(html).toContain(`href="${url}" target="_blank" rel="noopener"`);
    }
    expect(html).toContain('@candidate');
    expect(html).toContain('class="cv-linkcard"');
    expect(html).toContain(`href="${envelope.data.candidate.divulgacandcontas_url}"`);
  });
  it('renders the empty state when ingestion drops every declared entry', () => {
    const html = render([]);
    expect(html).toContain('Nenhuma rede declarada');
    expect(html).not.toContain('class="profile-social"');
  });
});
