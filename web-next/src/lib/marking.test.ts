import {describe, expect, it} from 'vitest';
import {compareParams, MAX_MARKED, MIN_MARKED} from './marking';

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
