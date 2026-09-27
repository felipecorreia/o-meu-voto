import type {ElectionInfo, PollingPlaceData} from '../api';
import {UFS} from '../labels';

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

/** A date-only calendar value is anchored at Brasília noon, independent of browser timezone. */
export function pollingVotingDate(election: ElectionInfo | null): {title: string; caption: string} | null {
  if (!election?.round.date) return null;
  const date = new Date(`${election.round.date}T12:00:00-03:00`);
  if (Number.isNaN(date.getTime())) return null;
  const options = {timeZone: 'America/Sao_Paulo'};
  const weekday = new Intl.DateTimeFormat('pt-BR', {...options, weekday: 'long'}).format(date);
  const day = new Intl.DateTimeFormat('pt-BR', {...options, day: 'numeric', month: 'long'}).format(date);
  return {title: `${weekday.charAt(0).toLocaleUpperCase('pt-BR')}${weekday.slice(1)}, ${day}`, caption: `${election.round.number}º turno · ${election.voting_hours.label}`};
}
