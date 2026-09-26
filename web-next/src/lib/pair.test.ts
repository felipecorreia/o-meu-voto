import {describe, expect, it} from 'vitest';
import {bringIn, pairAfterRemoval, resolvePair, swapNext, type PairState} from './pair';

// Three candidacies in ballot-number order, as the service answers them.
const T = {sq_candidato: 250002541303, number: 10};
const H = {sq_candidato: 250002549705, number: 13};
const V = {sq_candidato: 250002536915, number: 16};
const C = {sq_candidato: 250002550913, number: 21};
const three = [T, H, V];

describe('resolvePair', () => {
  it('keeps the URL membership but orders the columns by ballot number', () => {
    expect(resolvePair(three, [V.sq_candidato, T.sq_candidato])).toEqual([T.sq_candidato, V.sq_candidato]);
  });
  it('falls back to the two lowest ballot numbers otherwise', () => {
    expect(resolvePair(three, null)).toEqual([T.sq_candidato, H.sq_candidato]);
    expect(resolvePair(three, [T.sq_candidato, 1])).toEqual([T.sq_candidato, H.sq_candidato]);
    expect(resolvePair(three, [T.sq_candidato, T.sq_candidato])).toEqual([T.sq_candidato, H.sq_candidato]);
    expect(resolvePair(three, [T.sq_candidato])).toEqual([T.sq_candidato, H.sq_candidato]);
  });
});

describe('pairAfterRemoval', () => {
  const four = [T, H, V, C];

  it('replaces a removed pair member with the default visible pair', () => {
    expect(pairAfterRemoval(four, [T.sq_candidato, V.sq_candidato], T.sq_candidato)).toEqual([H.sq_candidato, V.sq_candidato]);
    expect(pairAfterRemoval(four, [T.sq_candidato, V.sq_candidato], V.sq_candidato)).toEqual([T.sq_candidato, H.sq_candidato]);
  });

  it('keeps a valid pair when another candidacy is removed', () => {
    expect(pairAfterRemoval(four, [T.sq_candidato, V.sq_candidato], H.sq_candidato)).toEqual([T.sq_candidato, V.sq_candidato]);
    expect(pairAfterRemoval(four, null, T.sq_candidato)).toBeNull();
  });

  it('falls back to the default when the remaining pair is invalid', () => {
    expect(pairAfterRemoval(four, [T.sq_candidato, 999], H.sq_candidato)).toEqual([T.sq_candidato, V.sq_candidato]);
  });
});

describe('bringIn', () => {
  const start: PairState = {pair: [T.sq_candidato, H.sq_candidato], older: 0};
  it('replaces the least recently changed candidacy and keeps ballot order after each change', () => {
    const one = bringIn(start, V.sq_candidato, three);
    expect(one).toEqual({pair: [H.sq_candidato, V.sq_candidato], older: 0});
    const two = bringIn(one, T.sq_candidato, three);
    expect(two).toEqual({pair: [T.sq_candidato, V.sq_candidato], older: 1});
  });
  it('changes nothing for a candidacy already on screen', () => {
    expect(bringIn(start, H.sq_candidato, three)).toBe(start);
    expect(bringIn(start, 999, three)).toBe(start);
  });
});

describe('swapNext', () => {
  it('goes to the next candidacy off screen in ballot order and marks the other column as older', () => {
    const start: PairState = {pair: [T.sq_candidato, H.sq_candidato], older: 0};
    expect(swapNext(start, three, 1)).toEqual({pair: [T.sq_candidato, V.sq_candidato], older: 0});
    expect(swapNext(start, three, 0)).toEqual({pair: [H.sq_candidato, V.sq_candidato], older: 0});
  });
  it('wraps to the first candidacy off screen when the column holds the last one', () => {
    const four = [T, H, V, C];
    const state: PairState = {pair: [H.sq_candidato, C.sq_candidato], older: 0};
    expect(swapNext(state, four, 1)).toEqual({pair: [T.sq_candidato, H.sq_candidato], older: 1});
    expect(swapNext(state, four, 0).pair).toEqual([V.sq_candidato, C.sq_candidato]);
  });
  it('changes nothing with only two candidacies', () => {
    const state: PairState = {pair: [T.sq_candidato, H.sq_candidato], older: 1};
    expect(swapNext(state, [T, H], 0)).toBe(state);
  });
});
