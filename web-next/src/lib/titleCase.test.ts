import {describe, expect, it} from 'vitest';
import {toTitleCase} from './titleCase';

describe('toTitleCase', () => {
  it('capitalises every word of an upper-case ballot name', () => {
    expect(toTitleCase('FERNANDO HADDAD')).toBe('Fernando Haddad');
  });
  it('lower-cases the particles de/da/do/das/dos/e except as the first word', () => {
    expect(toTitleCase('MARIA DA SILVA E SOUZA DOS SANTOS')).toBe('Maria da Silva e Souza dos Santos');
    expect(toTitleCase('DE OLHO NA CIDADE')).toBe('De Olho Na Cidade');
  });
  it('keeps accents and capitalises after a hyphen or an apostrophe', () => {
    expect(toTitleCase('JOSÉ ANTÔNIO')).toBe('José Antônio');
    expect(toTitleCase('ANA-LÚCIA D’ÁVILA')).toBe('Ana-Lúcia D’Ávila');
  });
  it('collapses stray whitespace and accepts a name already in mixed case', () => {
    expect(toTitleCase('  fernando   haddad ')).toBe('Fernando Haddad');
  });
});
