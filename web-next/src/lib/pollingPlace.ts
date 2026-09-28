import type {ElectionInfo, PollingPlaceData} from '../api';
import {UFS} from '../labels';
import {calendarDay, formatRoundDate, formatVotingHours, formatWeekday} from './electionDates';

export interface PollingPlaceSearch {uf: string; zone: string; section: string; round: string}
export const POLLING_UF_OPTIONS = [...UFS.map(([value, name]) => ({value, label: `${value} · ${name}`})), {value: 'ZZ', label: 'ZZ · Exterior'}];
export const POLLING_ROUNDS = [{value: '', label: 'Próximo turno'}, {value: '1', label: '1º turno'}, {value: '2', label: '2º turno'}];
export const numericError = (value: string) => /\D/.test(value) ? 'Use só números.' : undefined;
export const validPollingSearch = (search: PollingPlaceSearch) => /^\d+$/.test(search.zone) && /^\d+$/.test(search.section);

export function pollingSearchFromUrl(params: URLSearchParams): PollingPlaceSearch {
  const uf = params.get('uf') ?? '';
  const round = params.get('round') ?? '';
  return {uf: POLLING_UF_OPTIONS.some(o => o.value === uf) ? uf : 'SP', zone: params.get('zone') ?? '', section: params.get('section') ?? '', round: round === '1' || round === '2' ? round : ''};
}

export function pollingMapsUrl(d: PollingPlaceData): string {
  const p = d.place;
  const query = p.latitude != null && p.longitude != null ? `${p.latitude},${p.longitude}`
    : [p.address, p.neighborhood, `${d.municipality.name} - ${d.municipality.uf}`].filter(Boolean).join(', ');
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

/** The "Quando votar" card from the existing envelope, formatted by the shared election-date
 *  helpers in Brasília (Tela 6 spec, exception 1): the visible text is unchanged. */
export function pollingVotingDate(election: ElectionInfo | null): {title: string; caption: string} | null {
  const date = calendarDay(election?.round.date);
  if (!election || !date) return null;
  const hours = formatVotingHours(election.voting_hours);
  return {title: `${formatWeekday(date)}, ${formatRoundDate(date)}`, caption: `${election.round.number}º turno${hours ? ` · ${hours} (horário de Brasília)` : ''}`};
}
