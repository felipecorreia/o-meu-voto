import {describe, expect, it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import type {ComparedCandidate} from '../api';
import {MissingNotice, rowsFor} from './Comparison';
import {CompareRow} from './cv/CompareRow';

const candidate: ComparedCandidate = {
  sq_candidato: 1, number: 13, ballot_name: 'TEST CANDIDACY', name: 'Civil name',
  office: 'governador', party: {number: 13, acronym: 'PT', name: 'Party name'},
  federation: null, coalition: null, adjudication_status: 'DEFERIDO', on_ballot: true,
  occupation: null, photo_url: null, vote_destination: null, vote_destination_note: null,
  social_name: null, nomination_kind: 'partido_isolado', running_mates: [], social_links: [],
  divulgacandcontas_url: null, assets: {state: 'declarados', total: 2696808.4},
};

const render = (tab: 'chapa' | 'patrimonio' | 'ocupacao', c = candidate) =>
  rowsFor(tab, [c], 3).map(row => renderToStaticMarkup(<CompareRow {...row} />)).join('');

const nomination = (c: ComparedCandidate) =>
  renderToStaticMarkup(<CompareRow {...rowsFor('chapa', [c], 3).find(row => row.id === 'nomination')!} />);

describe('comparison rows', () => {
  it('shows coalition and federation separately when both are declared', () => {
    const html = nomination({...candidate, nomination_kind: 'coligacao',
      coalition: {name: 'Alliance name', composition: 'Party A / Party B'},
      federation: {acronym: 'FED', name: 'Federation name', composition: 'Party C / Party D'}});
    expect(html).toContain('<span class="cv-cell-badge">Coligação</span>');
    expect(html).toContain('<span class="cv-cell-badge">Federação</span>');
    expect(html).toContain('Alliance name');
    expect(html).toContain('Party A / Party B');
    expect(html).toContain('Federation name');
    expect(html).toContain('Party C / Party D');
    expect(html.indexOf('Coligação')).toBeLessThan(html.indexOf('Federação'));
  });

  it('keeps each single-alliance display', () => {
    const coalition = nomination({...candidate, nomination_kind: 'coligacao', coalition: {name: 'Alliance name', composition: 'Party A / Party B'}});
    const federation = nomination({...candidate, nomination_kind: 'federacao', federation: {acronym: 'FED', name: 'Federation name', composition: 'Party C / Party D'}});
    expect(coalition).toContain('<span class="cv-cell-badge">Coligação</span>');
    expect(coalition).toContain('Alliance name');
    expect(coalition).toContain('Party A / Party B');
    expect(coalition).not.toContain('Federação');
    expect(federation).toContain('<span class="cv-cell-badge">Federação</span>');
    expect(federation).toContain('Federation name');
    expect(federation).toContain('Party C / Party D');
    expect(federation).not.toContain('Coligação');
  });

  it('keeps the isolated-party display', () => {
    const html = nomination(candidate);
    expect(html).toContain('<span class="cv-cell-badge">Partido isolado</span>');
    expect(html).toContain('Party name');
    expect(html).not.toContain('Coligação');
    expect(html).not.toContain('Federação');
  });

  it('keeps both the compact declared-assets total and its exact value', () => {
    const html = render('patrimonio');
    expect(html).toContain('R$ 2,7 mi');
    expect(html).toMatch(/R\$\s*2\.696\.808,40 · como declarado ao TSE/);
    expect(html).toContain('Em preparação');
    expect(html).toContain('Até lá, só o total de 2026.');
  });

  it('distinguishes no assets from no published asset information', () => {
    expect(render('patrimonio', {...candidate, assets: {state: 'declarou_nao_possuir', total: 0}})).toContain('Declarou não possuir bens');
    expect(render('patrimonio', {...candidate, assets: {state: 'sem_informacao', total: null}})).toContain('Sem informação de bens no TSE');
  });

  it('names each cell for assistive technology and never renders profile-only fields', () => {
    const c = {...candidate, gender: 'private-gender', race_color: 'private-race', marital_status: 'private-status', education: 'private-education'};
    const html = render('chapa', c) + render('ocupacao', c) + render('patrimonio', c);
    expect(html).toContain('role="group" aria-label="Test Candidacy: Civil name"');
    expect(html).toContain('Não se aplica');
    expect(html).toContain('Não informado pelo TSE');
    expect(html).not.toContain('private-');
  });

  it('deduplicates social URLs and renders three links before the expand action', () => {
    const html = render('ocupacao', {...candidate, social_links: [
      'https://instagram.com/example', 'HTTPS://INSTAGRAM.COM/EXAMPLE',
      'https://facebook.com/example', 'https://x.com/example', 'https://youtube.com/@example',
    ]});
    expect((html.match(/target="_blank"/g) ?? [])).toHaveLength(3);
    expect(html).toContain('+1 redes');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(render('ocupacao')).toContain('Nenhuma rede declarada');
  });
});

describe('missing candidacy notice', () => {
  it('uses the requested sq when the missing profile has no name or number', () => {
    const html = renderToStaticMarkup(<MissingNotice missing={[{requested: 123, reason: 'nao_encontrado'}]} names={new Map()} />);
    expect(html).toContain('Candidatura 123: não foi encontrada neste cargo e estado.');
  });

  it('uses the ballot name and number when the profile responds', () => {
    const html = renderToStaticMarkup(<MissingNotice missing={[{requested: 123, reason: 'nao_encontrado'}]} names={new Map([[123, {ballot_name: 'MARIA SILVA', number: 42}]])} />);
    expect(html).toContain('Maria Silva (42): não foi encontrada neste cargo e estado.');
  });
});
