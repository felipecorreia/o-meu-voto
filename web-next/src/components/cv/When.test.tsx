import {describe, expect, it, vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import type {ElectionData, Envelope} from '../../api';
import {WhenScreen} from '../../pages/When';
import {CountdownHero} from './CountdownHero';
import {CvChip} from './CvChip';
import {InfoStrip} from './InfoStrip';
import {RoundTile} from './RoundTile';

// api.ts reads the page's <meta> at import; the screen renders from a given envelope, no fetch.
vi.mock('../../api', () => ({api: {}}));

// The real answer of GET /api/v1/election on 2026-09-28.
const data: ElectionData = {
  id: 'general-2026', name: 'Eleições Gerais 2026',
  rounds: [{number: 1, date: '2026-10-04', note: null}, {number: 2, date: '2026-10-25', note: 'Somente onde houver segundo turno: presidente e governador quando nenhum candidato alcança maioria absoluta no primeiro turno.'}],
  voting_hours: {start: '08:00', end: '17:00', timezone: 'America/Sao_Paulo', label: '8h às 17h (horário de Brasília)'},
  next_round: {number: 1, date: '2026-10-04', note: null}, days_until_next_round: 6,
  offices: ['presidente', 'governador', 'senador', 'deputado_federal', 'deputado_estadual', 'deputado_distrital'],
  notes: ['A votação é simultânea em todo o país e segue o horário de Brasília, inclusive nos estados com fuso horário diferente.', 'Quem está fora do domicílio eleitoral pode justificar a ausência no dia da votação, das 8h às 17h (horário de Brasília).'],
  calendar_source: {title: 'Resolução TSE nº 23.760, de 2 de março de 2026 (Calendário Eleitoral)', url: 'https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-760-de-2-de-marco-de-2026', verified_at: '2026-09-17'},
};
const envelope = (d: ElectionData | null, extra: Partial<Envelope<ElectionData>> = {}): Envelope<ElectionData> =>
  ({data: d, not_found: null, warnings: [], election: null, source: {kind: 'curated', license: 'CC-BY', attribution: 'Tribunal Superior Eleitoral - Portal de Dados Abertos', calendar_source: 'Resolução', verified_at: '2026-09-17'}, ...extra});
const at = (iso: string) => new Date(iso);
const screen = (d: ElectionData | null, now = at('2026-09-28T10:00:00-03:00'), extra: Partial<Envelope<ElectionData>> = {}, view: 'ok' | 'no_data' | 'error' | 'loading' = d ? 'ok' : 'no_data') =>
  renderToStaticMarkup(<WhenScreen env={view === 'error' ? null : envelope(d, extra)} view={view} now={now} onRetry={() => {}} />);

describe('the Quando screen by phase', () => {
  it('counts down to the first round on 28/09 (criterion 1)', () => {
    const html = screen(data);
    expect(html).toContain('<span class="cv-countdown-num" aria-hidden="true">6</span>');
    expect(html).toContain('dias para o 1º turno');
    expect(html).toContain('Domingo, 4 de outubro · 8h às 17h');
    expect(html).toContain('aria-label="6 dias para o 1º turno, Domingo, 4 de outubro"');
    expect(html).not.toContain('role="timer"');
    expect(html).not.toContain('aria-live');
    expect(html).toMatch(/cv-roundtile cv-roundtile-next" aria-label="1º turno, 4 de outubro, domingo, próximo"/);
    expect(html).toContain('aria-label="2º turno, 25 de outubro, domingo, só onde houver"');
    expect(html).toContain('>Próximo</span>');
    expect(html).toContain('>Só onde houver</span>');
    expect(html).not.toContain('Só onde houver 2º turno');
    expect(html).toContain('cv-infostrip-title">8h às 17h</span>');
    expect(html).toContain('Horário de Brasília, o mesmo em todo o país');
  });
  it('reads 1 dia on the eve (criterion 2)', () => {
    const html = screen(data, at('2026-10-03T21:00:00-03:00'));
    expect(html).toContain('aria-hidden="true">1</span>');
    expect(html).toContain('dia para o 1º turno');
    expect(html).toContain('aria-label="1 dia para o 1º turno, Domingo, 4 de outubro"');
  });
  it('is the voting day with the CTA, then closed after 17h (criterion 3)', () => {
    const day = screen(data, at('2026-10-04T10:00:00-03:00'));
    expect(day).toContain('Hoje é dia de votar');
    expect(day).toContain('1º turno · 8h às 17h (horário de Brasília)');
    expect(day).toContain('class="cv-countdown-cta" href="#/onde-voto"');
    expect(day).toContain('Ver onde eu voto');
    expect(day).toContain('>Hoje</span>');
    const closed = screen(data, at('2026-10-04T17:30:00-03:00'));
    expect(closed).toContain('A votação de hoje terminou');
    expect(closed).toContain('As seções fecharam às 17h (horário de Brasília).');
    expect(closed).not.toContain('cv-countdown-cta');
  });
  it('between the rounds counts down to the second with the notice (criterion 4)', () => {
    const html = screen(data, at('2026-10-10T12:00:00-03:00'));
    expect(html).toContain('aria-hidden="true">15</span>');
    expect(html).toContain('dias para o 2º turno');
    expect(html).toContain('Só onde houver 2º turno');
    expect(html).toContain('Para presidente e governador, quando ninguém passa de metade dos votos válidos no 1º turno.');
    expect(html).toContain('aria-label="1º turno, 4 de outubro, domingo, já aconteceu"');
    expect(html).toMatch(/cv-roundtile cv-roundtile-next" aria-label="2º turno, 25 de outubro, domingo, próximo · onde houver"/);
  });
  it('closes the election the day after the last round (criterion 5)', () => {
    const html = screen(data, at('2026-10-26T09:00:00-03:00'));
    expect(html).toContain('As votações de 2026 terminaram');
    expect(html).toContain('Os resultados oficiais são divulgados pelo TSE.');
    expect(html).toContain('href="https://www.tse.jus.br/" target="_blank" rel="noopener"');
    expect(html).toContain('Resultados no site do TSE');
    expect((html.match(/Já aconteceu/g) ?? []).length).toBe(2);
  });
  it('keeps the phase of Brasília with the device in another zone (criterion 6)', () => {
    // 01:00 UTC on 04/10 is still 03/10 in Brasília.
    expect(screen(data, at('2026-10-04T01:00:00Z'))).toContain('aria-label="1 dia para o 1º turno, Domingo, 4 de outubro"');
    expect(screen(data, at('2026-10-04T20:30:00Z'))).toContain('A votação de hoje terminou');
  });
});

describe('the Quando screen with missing data (criteria 7 to 9)', () => {
  it('shows the no-data state with retry and the meanwhile links, without service guidance', () => {
    const html = screen(null, undefined, {not_found: {reason: 'calendar_missing', guidance: 'Use the get_election MCP tool'}});
    expect(html).toContain('O calendário não carregou');
    expect(html).toContain('O serviço ainda não trouxe as datas desta eleição. Tente de novo em instantes.');
    expect(html).toContain('<button type="button">Tentar de novo</button>');
    expect(html).toContain('Enquanto isso');
    expect(html).toContain('href="https://www.tse.jus.br/" target="_blank" rel="noopener"');
    expect(html).toContain('Calendário no site do TSE');
    expect(html).toContain('Site oficial, abre em nova aba');
    expect(html).toContain('href="#/onde-voto"');
    expect(html).not.toContain('calendar_missing');
    expect(html).not.toContain('get_election');
    expect(html).not.toContain('cv-countdown');
  });
  it('shows the error state with the common copy and no footer source', () => {
    const html = screen(null, undefined, {}, 'error');
    expect(html).toContain('Não foi possível consultar agora');
    expect(html).toContain('Tente de novo em instantes.');
    expect(html).toContain('Tentar de novo');
    expect(html).not.toContain('class="source"');
  });
  it('shows the loading state without a footer', () => {
    const html = screen(null, undefined, {}, 'loading');
    expect(html).toContain('Consultando os dados abertos do TSE…');
    expect(html).not.toContain('when-foot');
  });
  it('marks a round without a date as to be confirmed and ignores it in the phase', () => {
    const html = screen({...data, rounds: [data.rounds[0], {number: 2, date: null as unknown as string, note: null}]}, at('2026-10-10T12:00:00-03:00'));
    expect(html).toContain('aria-label="2º turno, data a confirmar"');
    expect(html).toContain('>Data a confirmar</span>');
    expect(html).not.toContain('Só onde houver');
    expect(html).toContain('As votações de 2026 terminaram');
    expect(html).toContain('aria-label="1º turno, 4 de outubro, domingo, já aconteceu"');
  });
  it('has no hero and no highlight without the first round date', () => {
    const html = screen({...data, rounds: [{number: 1, date: null as unknown as string, note: null}, data.rounds[1]]});
    expect(html).not.toContain('cv-countdown');
    expect(html).not.toContain('cv-roundtile-next');
    expect(html).toContain('aria-label="1º turno, data a confirmar"');
    expect(html).toContain('aria-label="2º turno, 25 de outubro, domingo, só onde houver"');
  });
  it('drops the hours strip and the hero hours without voting hours', () => {
    const html = screen({...data, voting_hours: null as unknown as ElectionData['voting_hours']});
    expect(html).not.toContain('cv-infostrip');
    expect(html).toContain('aria-hidden="true">Domingo, 4 de outubro</span>');
    expect(html).not.toContain(' · 8h');
    expect(screen({...data, voting_hours: null as unknown as ElectionData['voting_hours']}, at('2026-10-04T23:00:00-03:00'))).toContain('Hoje é dia de votar');
  });
  it('joins the state and district deputies into one chip in the service order (criterion 8)', () => {
    const html = screen(data);
    expect(html).toMatch(/<li class="cv-chip">Presidente<\/li><li class="cv-chip">Governador<\/li><li class="cv-chip">Senador<\/li><li class="cv-chip">Deputado federal<\/li><li class="cv-chip">Deputado estadual ou distrital<\/li><\/ul>/);
    expect(html).not.toContain('>Deputado estadual</li>');
    expect(html).not.toContain('>Deputado distrital</li>');
    const single = screen({...data, offices: ['deputado_distrital', 'governador']});
    expect(single).toContain('<li class="cv-chip">Deputado distrital</li><li class="cv-chip">Governador</li>');
  });
  it('hides the offices, the notes and the source when they are empty', () => {
    const html = screen({...data, offices: [], notes: [], calendar_source: {title: '', url: '', verified_at: ''}});
    expect(html).not.toContain('Cargos em disputa');
    expect(html).not.toContain('when-notes');
    expect(html).not.toContain('Fonte:');
    expect(html).toContain('Antes de sair de casa');
  });
  it('formats the source line and drops only the date when it is missing', () => {
    expect(screen(data)).toContain('Fonte: <a href="https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-760-de-2-de-marco-de-2026" target="_blank" rel="noopener">Resolução TSE nº 23.760, de 2 de março de 2026 (Calendário Eleitoral)</a>, verificada em 17/09/2026.');
    expect(screen({...data, calendar_source: {...data.calendar_source, verified_at: ''}})).toMatch(/\(Calendário Eleitoral\)<\/a>\.<\/p>/);
  });
  it('shows one full-width tile for a single round and the service warnings', () => {
    const html = screen({...data, rounds: [data.rounds[0]]}, undefined, {warnings: ['Aviso do serviço.']});
    expect(html).toContain('cv-roundtiles cv-roundtiles-single');
    expect(html).toContain('Aviso do serviço.');
    expect(html).toContain('cv-notice-wait');
  });
  it('never renders the service note of the second round or its technical codes (criterion 9)', () => {
    const html = screen(data);
    expect(html).not.toContain('Somente onde houver segundo turno');
    expect(html).not.toContain('deputado_');
    expect(html).not.toContain('general-2026');
    expect(html).not.toContain('America/Sao_Paulo');
  });
});

describe('the Tela 6 pieces', () => {
  it('reads the countdown as one sentence and hides the three texts', () => {
    const html = renderToStaticMarkup(<CountdownHero variant="count" days={1} roundLabel="2º turno" dateLabel="Domingo, 25 de outubro" hours="8h às 17h" />);
    expect(html).toContain('aria-label="1 dia para o 2º turno, Domingo, 25 de outubro"');
    expect((html.match(/aria-hidden="true"/g) ?? []).length).toBe(3);
    expect(html).toContain('Domingo, 25 de outubro · 8h às 17h');
  });
  it('renders a tile without a date as to be confirmed, with no weekday and no tag', () => {
    const html = renderToStaticMarkup(<RoundTile roundNumber={2} date={null} tag="Só onde houver" highlighted />);
    expect(html).toContain('Data a confirmar');
    expect(html).not.toContain('Só onde houver');
    expect(html).not.toContain('cv-roundtile-weekday');
    expect(html).toContain('cv-roundtile-next');
  });
  it('renders the strip and the chip as plain, non-interactive pieces', () => {
    expect(renderToStaticMarkup(<InfoStrip icon={<i />} title="8h às 17h" subtitle="Horário de Brasília" />)).toContain('<span class="cv-infostrip-icon" aria-hidden="true"><i></i></span>');
    expect(renderToStaticMarkup(<ul><CvChip>Senador</CvChip></ul>)).toBe('<ul><li class="cv-chip">Senador</li></ul>');
  });
});
