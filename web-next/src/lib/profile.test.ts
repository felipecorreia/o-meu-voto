import {describe, expect, it} from 'vitest';
import type {CandidateProfile} from '../api';
import {profileNavigation, profileShare, profileUf} from './profile';

const c: CandidateProfile = {
  sq_candidato: 2, number: 11, ballot_name: 'MARIA SILVA', name: 'Civil name',
  office: 'governador', party: {number: 11, acronym: 'PP', name: 'Party name'},
  federation: null, coalition: null, adjudication_status: 'DEFERIDO', on_ballot: true,
  occupation: null, photo_url: null, vote_destination: null, round: 1,
  social_name: null, nomination_kind: 'partido_isolado', gender: null, race_color: null,
  marital_status: null, education: null, running_mates: [], social_links: [],
  divulgacandcontas_url: 'https://divulgacandcontas.tse.jus.br/divulga/#/candidato/NORTE/AC/20322002026/2/2026/AC',
};
const query = (link: string) => Object.fromEntries(new URLSearchParams(link.split('?')[1]));

describe('profile navigation', () => {
  it('returns the marking order, current pair and tab to the comparison', () => {
    const nav = profileNavigation(c, new URLSearchParams('uf=AC&office=governador&cmp=3,2,1&pair=1,2&tab=ocupacao'));
    expect(query(nav.backHref)).toEqual({uf: 'AC', office: 'governador', sq: '3,2,1', pair: '1,2', tab: 'ocupacao'});
    expect(nav.slot).toBe(2);
    expect(query(nav.chooseHref)).toEqual({uf: 'AC', office: 'governador', marcar: '3,2,1'});
  });
  it('opens a direct state profile neutrally and preselects this candidacy', () => {
    const nav = profileNavigation(c, new URLSearchParams());
    expect(nav.fromComparison).toBe(false);
    expect(nav.slot).toBeUndefined();
    expect(query(nav.backHref)).toEqual({uf: 'AC', office: 'governador'});
    expect(query(nav.chooseHref)).toEqual({uf: 'AC', office: 'governador', marcar: '2'});
  });
  it('uses the official electoral unit rather than a mismatched route UF', () => {
    expect(profileUf(c, 'SP')).toBe('AC');
    expect(profileUf({...c, divulgacandcontas_url: null}, 'RJ')).toBe('RJ');
    expect(profileUf({...c, divulgacandcontas_url: null})).toBeUndefined();
    expect(profileUf({...c, divulgacandcontas_url: 'https://example.com/#/AC'}, 'SP')).toBe('SP');
    expect(profileUf({...c, divulgacandcontas_url: 'not a url'}, 'ZZ')).toBeUndefined();
  });
  it('opens a presidential profile in BR', () => {
    const nav = profileNavigation({...c, office: 'presidente'}, new URLSearchParams('uf=SP'));
    expect(query(nav.backHref)).toEqual({uf: 'BR', office: 'presidente'});
    expect(query(nav.chooseHref)).toEqual({uf: 'BR', office: 'presidente', marcar: '2'});
  });
  it('does not paint unrelated or out-of-range slots', () => {
    expect(profileNavigation(c, new URLSearchParams('cmp=3,4')).slot).toBeUndefined();
    expect(profileNavigation(c, new URLSearchParams('cmp=3,4,5,6,2')).slot).toBeUndefined();
  });
});
describe('profile sharing', () => {
  it('shares exact text with a direct link, without comparison or review parameters', () => {
    const shared = profileShare(c, 'Maria Silva', 'Governador', 'AC', 'https://example.com/?theme=butter#/candidato/2?cmp=3,2&tab=ocupacao');
    expect(shared.url).toBe('https://example.com/#/candidato/2');
    expect(shared.title).toBe('Maria Silva (11) · O meu voto');
    expect(shared.text).toBe('Ficha de Maria Silva (11), candidatura a Governador (AC), com os dados abertos do TSE: https://example.com/#/candidato/2');
  });
});
