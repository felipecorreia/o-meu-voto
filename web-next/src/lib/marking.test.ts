import {describe, expect, it} from 'vitest';
import {compareParams, loadPreloaded, MAX_MARKED, mergePreloaded, MIN_MARKED, parseSqList, slotOf} from './marking';

describe('preloaded markings', () => {
  const candidates = [1, 2, 3, 4, 5, 6].map(sq_candidato => ({sq_candidato}));
  const ids = (marked: Map<number, {sq_candidato: number}>) => Array.from(marked.keys());

  it('keeps link order, user additions and explicit removals', () => {
    const current = new Map([[5, candidates[4]], [1, candidates[0]]]);
    expect(ids(mergePreloaded([1, 2, 3], candidates.slice(0, 3), current, new Set([1, 5])))).toEqual([1, 2, 3, 5]);
    expect(ids(mergePreloaded([1, 2, 3], candidates.slice(0, 3), new Map([[5, candidates[4]]]), new Set([2, 5])))).toEqual([1, 3, 5]);
  });

  it('reserves capacity for user additions and keeps successful partial preloads', () => {
    const current = new Map([[5, candidates[4]], [6, candidates[5]]]);
    expect(ids(mergePreloaded([1, 2, 3, 4], candidates.slice(0, 4), current, new Set([5, 6])))).toEqual([1, 2, 5, 6]);
    expect(ids(mergePreloaded([1, 2, 3, 4], [candidates[0], candidates[2]], current, new Set([5, 6])))).toEqual([1, 3, 5, 6]);
  });

  it('retains successful profiles after a failed request and a selection during loading', async () => {
    let finish!: (value: {sq_candidato: number}) => void;
    const pending = new Promise<{sq_candidato: number}>(resolve => { finish = resolve; });
    const loading = loadPreloaded([1, 2, 3], id => id === 2 ? Promise.reject(new Error('service unavailable')) : id === 3 ? pending : Promise.resolve(candidates[0]));
    const current = new Map([[5, candidates[4]]]);
    finish(candidates[2]);
    expect(ids(mergePreloaded([1, 2, 3], await loading, current, new Set([5])))).toEqual([1, 3, 5]);
  });

  it('keeps a list-loaded candidacy at its marcar position when its profile fails', async () => {
    const order = parseSqList('1,2,3');
    const profiles = await loadPreloaded(order, id => id === 2 ? Promise.reject(new Error('service unavailable')) : Promise.resolve(candidates[id - 1]));
    const current = new Map([[2, candidates[1]]]);
    expect(ids(mergePreloaded(order, profiles, current, new Set([2])))).toEqual([1, 2, 3]);
  });
});

describe('compareParams', () => {
  it('carries sq in the order of marking, not in ballot-number or sq order', () => {
    const marked = [{sq_candidato: 250002549705, number: 22}, {sq_candidato: 250002541303, number: 13}, {sq_candidato: 250001234567, number: 40}];
    expect(compareParams('SP', 'governador', marked)).toEqual({uf: 'SP', office: 'governador', sq: '250002549705,250002541303,250001234567'});
  });
  it('follows a re-marking: unmarking the first shifts the rest up', () => {
    const marked = [{sq_candidato: 1}, {sq_candidato: 2}, {sq_candidato: 3}];
    const after = marked.filter(c => c.sq_candidato !== 1).concat([{sq_candidato: 4}]);
    expect(compareParams('BR', 'presidente', after).sq).toBe('2,3,4');
  });
  it('keeps the 2..4 rule as constants', () => {
    expect(MIN_MARKED).toBe(2);
    expect(MAX_MARKED).toBe(4);
  });
});

describe('parseSqList', () => {
  it('keeps the written order and drops blanks, junk and repeats', () => {
    expect(parseSqList('250002549705,250002541303,250002536915')).toEqual([250002549705, 250002541303, 250002536915]);
    expect(parseSqList('3,,x, 1 ,3,-2,0')).toEqual([3, 1]);
    expect(parseSqList(null)).toEqual([]);
    expect(parseSqList('')).toEqual([]);
  });
});

describe('slotOf', () => {
  it('is the position in the URL sq, not the ballot order', () => {
    const order = [250002549705, 250002541303, 250002536915];
    expect(slotOf(order, 250002541303, 1)).toBe(2);
    expect(slotOf(order, 250002549705, 2)).toBe(1);
    expect(slotOf(order, 250002536915, 3)).toBe(3);
  });
  it('keeps the position of a missing candidacy, so the others keep their tray colours', () => {
    expect(slotOf([1, 999, 2], 2, 2)).toBe(3);
  });
  it('falls back to the position among the compared ones and never leaves 1..4', () => {
    expect(slotOf([1, 2], 3, 3)).toBe(3);
    expect(slotOf([1, 2, 3, 4, 5], 5, 5)).toBe(4);
    expect(slotOf([], 7, 0)).toBe(1);
  });
});
