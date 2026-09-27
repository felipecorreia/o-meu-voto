import {describe, expect, it} from 'vitest';
import type {ElectionInfo, PollingPlaceData} from '../api';
import {numericError, POLLING_UF_OPTIONS, pollingMapsUrl, pollingSearchFromUrl, pollingVotingDate, validPollingSearch} from './pollingPlace';

describe('polling place links and search input', () => {
  it('accepts leading zeros without changing the input, rejects letters and leaves empty fields without an error', () => {
    const search = pollingSearchFromUrl(new URLSearchParams('uf=ZZ&zone=009&section=0422&round=2'));
    expect(search).toEqual({uf: 'ZZ', zone: '009', section: '0422', round: '2'});
    expect(validPollingSearch(search)).toBe(true);
    expect(numericError('')).toBeUndefined();
    expect(numericError('abc')).toBe('Use só números.');
    expect(validPollingSearch({...search, section: ''})).toBe(false);
    expect(validPollingSearch({...search, zone: '1e2'})).toBe(false);
  });
  it('keeps invalid numbers for the field errors and defaults unknown UF and round', () => {
    expect(pollingSearchFromUrl(new URLSearchParams('uf=BR&zone=abc&section=1&round=3'))).toEqual({uf: 'SP', zone: 'abc', section: '1', round: ''});
    expect(POLLING_UF_OPTIONS).toHaveLength(28);
    expect(POLLING_UF_OPTIONS.some(o => o.value === 'BR')).toBe(false);
  });
  const data = {place: {address: 'Rua A, 1', neighborhood: 'Sé', latitude: -23.5, longitude: -46.6}, municipality: {name: 'São Paulo', uf: 'SP'}} as PollingPlaceData;
  it('prefers coordinates, including zero, and falls back to the full service address', () => {
    expect(new URL(pollingMapsUrl(data)).searchParams.get('query')).toBe('-23.5,-46.6');
    expect(new URL(pollingMapsUrl({...data, place: {...data.place, latitude: 0, longitude: 0}})).searchParams.get('query')).toBe('0,0');
    expect(new URL(pollingMapsUrl({...data, place: {...data.place, latitude: null}})).searchParams.get('query')).toBe('Rua A, 1, Sé, São Paulo - SP');
  });
});

describe('polling date from the existing envelope', () => {
  const election = {round: {number: 1, date: '2026-10-04'}, voting_hours: {label: '8h às 17h (horário de Brasília)'}} as ElectionInfo;
  it('formats the calendar day in Brasília with the existing voting hours', () => {
    expect(pollingVotingDate(election)).toEqual({title: 'Domingo, 4 de outubro', caption: '1º turno · 8h às 17h (horário de Brasília)'});
  });
  it('omits the card for absent or unusable dates', () => {
    expect(pollingVotingDate(null)).toBeNull();
    expect(pollingVotingDate({...election, round: {number: 1, date: null as unknown as string}})).toBeNull();
    expect(pollingVotingDate({...election, round: {number: 1, date: 'invalid'}})).toBeNull();
  });
});
