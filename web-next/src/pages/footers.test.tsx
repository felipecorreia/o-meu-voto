import {afterEach, describe, expect, it, vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {CandidatePage} from './Candidate';
import {WhereToVotePage} from './WhereToVote';

const {candidateEnvelope, placeEnvelope} = vi.hoisted(() => {
  const source = {kind: 'dataset', attribution: 'TSE', license: 'CC-BY', stale: true, age_hours: 60};
  return {
    candidateEnvelope: {
      data: {candidate: {
        sq_candidato: 2, number: 11, ballot_name: 'MARIA SILVA', name: 'Civil name',
        office: 'governador', party: {number: 11, acronym: 'PP', name: 'Party name'},
        federation: null, coalition: null, adjudication_status: 'DEFERIDO', on_ballot: true,
        occupation: null, photo_url: null, vote_destination: null, round: 1,
        social_name: null, nomination_kind: 'partido_isolado', gender: null, race_color: null,
        marital_status: null, education: null, running_mates: [], social_links: [] as string[],
        divulgacandcontas_url: null,
      }},
      warnings: [], election: null, not_found: null, source,
    },
    placeEnvelope: {data: null, not_found: null, warnings: [], election: null, source},
  };
});

vi.mock('../api', () => ({api: {}, ApiError: class extends Error {}}));

// Force the loaded API state so the pages render their result surface.
let loaded: unknown = null;
vi.mock('react', async importOriginal => {
  const react = await importOriginal<typeof import('react')>();
  return {...react, useState: <T,>(initial: T | (() => T)) => react.useState(initial === null && loaded ? loaded as T : initial)};
});

afterEach(() => { loaded = null; vi.unstubAllGlobals(); });

const NOTICE = 'Projeto independente';

function stubBrowser(hash: string) {
  vi.stubGlobal('location', {href: `https://example.com/${hash}`, hash});
  vi.stubGlobal('navigator', {});
  vi.stubGlobal('window', {matchMedia: () => ({matches: false, addEventListener() {}, removeEventListener() {}})});
}

describe('independent-project notice lives only in the shell footer (issues #80, #85)', () => {
  it('candidate profile page footer keeps the source and the 48 h badge, without the notice', () => {
    loaded = candidateEnvelope;
    stubBrowser('#/candidato/2');
    const html = renderToStaticMarkup(<CandidatePage sq={2} backHref="#/candidato/2" />);
    expect(html).toContain('TSE (CC-BY)');
    expect(html).toContain('Dados com mais de 48 h');
    expect(html).not.toContain(NOTICE);
    expect(html).not.toContain('Nada é guardado');
  });

  it('where-to-vote page footer keeps the source and the 48 h badge, without the notice', () => {
    loaded = placeEnvelope;
    stubBrowser('#/onde-voto?uf=AC&zone=1&section=1');
    const html = renderToStaticMarkup(<WhereToVotePage />);
    expect(html).toContain('class="voting-foot"');
    expect(html).toContain('TSE (CC-BY)');
    expect(html).toContain('Dados com mais de 48 h');
    expect(html).not.toContain(NOTICE);
    expect(html).not.toContain('não acessa o cadastro eleitoral');
  });

  it('where-to-vote form state (no answer yet) renders no notice either', () => {
    stubBrowser('#/onde-voto');
    const html = renderToStaticMarkup(<WhereToVotePage />);
    expect(html).toContain('class="voting-foot"');
    expect(html).not.toContain(NOTICE);
  });
});
