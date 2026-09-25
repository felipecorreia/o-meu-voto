/**
 * MOCK DATA, LABELLED AS SUCH IN THE UI. Two comparison fields the comparator research
 * (data/bre-comparador-pesquisa/report.md, 2026-09-25) adds to v1/v1.1 are not in the API yet:
 *
 * - vote destination (`NM_TIPO_DESTINACAO_VOTOS`, v1): here derived from the adjudication
 *   status only so the card can be judged; the service will read the TSE column verbatim.
 * - declared assets 2026 and the growth line (v1/v1.1): the presidential figures of report
 *   section 3.3 (TSE file of 2026-09-25), keyed by ballot number; every other race shows
 *   "not in the index yet". The baseline office is printed only where the report states it
 *   (Flávio Bolsonaro, senador 2018); the other baselines carry the year alone.
 */

export type VoteDestination = 'Válido' | 'Anulado sub judice' | 'Nulo técnico';

export const VOTE_DESTINATION_EXPLANATION: Record<VoteDestination, string> = {
  'Válido': 'Os votos contam para a candidatura e para a legenda.',
  'Anulado sub judice': 'Registro indeferido com recurso pendente: os votos ficam anulados até a decisão final e só valem se o registro for deferido.',
  'Nulo técnico': 'Registro negado sem recurso pendente, ou candidatura fora da disputa: os votos não contam.',
};

/** Prototype-only derivation. The service will carry the TSE's own value. */
export function mockVoteDestination(adjudicationStatus: string, onBallot: boolean): VoteDestination {
  const s = adjudicationStatus.toUpperCase();
  if (s === 'DEFERIDO') return 'Válido';
  if (s.includes('INDEFERIDO') && (s.includes('RECURSO') || s.includes('PRAZO'))) return 'Anulado sub judice';
  if (!onBallot) return 'Nulo técnico';
  if (s.includes('PENDENTE')) return 'Anulado sub judice';
  return 'Nulo técnico';
}

export interface AssetsMock {
  state: 'declarados' | 'declarou_nao_possuir' | 'sem_informacao';
  total: number | null;
  generated_at: string;
  previous: null | {year: number; office: string | null; total: number; total_in_2026_brl: number; change_nominal_brl: number; change_real_brl: number};
}

const GEN = '2026-09-25T08:30:51-03:00';
const P = (year: number, office: string | null, total: number, in2026: number, nominal: number, real: number) =>
  ({year, office, total, total_in_2026_brl: in2026, change_nominal_brl: nominal, change_real_brl: real});

/** Report section 3.3, presidential candidates (BR / presidente), by ballot number. */
const PRESIDENT_ASSETS: Record<number, AssetsMock> = {
  13: {state: 'declarados', total: 4_775_651, generated_at: GEN, previous: P(2022, null, 7_423_726, 8_869_645, -2_648_075, -4_093_994)},
  14: {state: 'declarados', total: 795_089, generated_at: GEN, previous: null},
  16: {state: 'declarados', total: 170_000, generated_at: GEN, previous: P(2018, null, 100_000, 150_957, 70_000, 19_043)},
  21: {state: 'declarados', total: 454_486, generated_at: GEN, previous: null},
  22: {state: 'declarados', total: 8_186_556, generated_at: GEN, previous: P(2018, 'senador', 1_741_758, 2_629_305, 6_444_798, 5_557_251)},
  27: {state: 'declarados', total: 1_820_760, generated_at: GEN, previous: null},
  28: {state: 'declarados', total: 495_030_000, generated_at: GEN, previous: P(2018, null, 379_800, 573_335, 494_650_200, 494_456_665)},
  29: {state: 'sem_informacao', total: null, generated_at: GEN, previous: null},
  30: {state: 'declarados', total: 178_707_610, generated_at: GEN, previous: P(2022, null, 129_795_314, 155_075_543, 48_912_296, 23_632_067)},
  35: {state: 'declarados', total: 50_000_000, generated_at: GEN, previous: P(2024, null, 24_620_000, 26_976_261, 25_380_000, 23_023_739)},
  55: {state: 'declarados', total: 52_557_931, generated_at: GEN, previous: P(2022, null, 24_874_436, 29_719_229, 27_683_495, 22_838_702)},
  70: {state: 'declarados', total: 242_593_012, generated_at: GEN, previous: null},
  80: {state: 'declarados', total: 33_000, generated_at: GEN, previous: P(2022, null, 3_365, 4_020, 29_635, 28_980)},
};

export function mockAssets(office: string, number: number): AssetsMock | null {
  if (office !== 'presidente') return null;
  return PRESIDENT_ASSETS[number] ?? null;
}

/** "R$ 8,2 mi", "R$ 33 mil", "R$ 3.365": money in reais, compact, pt-BR. */
export function brl(n: number): string {
  const abs = Math.abs(n);
  const sign = n < 0 ? '−' : '';
  if (abs >= 1_000_000_000) return `${sign}R$ ${(abs / 1_000_000_000).toLocaleString('pt-BR', {maximumFractionDigits: 2})} bi`;
  if (abs >= 1_000_000) return `${sign}R$ ${(abs / 1_000_000).toLocaleString('pt-BR', {minimumFractionDigits: 1, maximumFractionDigits: 1})} mi`;
  if (abs >= 10_000) return `${sign}R$ ${Math.round(abs / 1_000).toLocaleString('pt-BR')} mil`;
  if (abs >= 1_000) return `${sign}R$ ${(abs / 1_000).toLocaleString('pt-BR', {minimumFractionDigits: 1, maximumFractionDigits: 1})} mil`;
  return `${sign}R$ ${abs.toLocaleString('pt-BR')}`;
}
export function brlDelta(n: number): string { return n >= 0 ? `+${brl(n)}` : brl(n); }
export function brlFull(n: number): string { return `R$ ${n.toLocaleString('pt-BR')}`; }
