// Labels the page owns (PT-BR for the voter); everything else comes from the API envelope.
import {sentenceCase} from './format';

export const UFS: Array<[string, string]> = [
  ['AC', 'Acre'], ['AL', 'Alagoas'], ['AP', 'Amapá'], ['AM', 'Amazonas'], ['BA', 'Bahia'], ['CE', 'Ceará'],
  ['DF', 'Distrito Federal'], ['ES', 'Espírito Santo'], ['GO', 'Goiás'], ['MA', 'Maranhão'], ['MT', 'Mato Grosso'],
  ['MS', 'Mato Grosso do Sul'], ['MG', 'Minas Gerais'], ['PA', 'Pará'], ['PB', 'Paraíba'], ['PR', 'Paraná'],
  ['PE', 'Pernambuco'], ['PI', 'Piauí'], ['RJ', 'Rio de Janeiro'], ['RN', 'Rio Grande do Norte'], ['RS', 'Rio Grande do Sul'],
  ['RO', 'Rondônia'], ['RR', 'Roraima'], ['SC', 'Santa Catarina'], ['SP', 'São Paulo'], ['SE', 'Sergipe'], ['TO', 'Tocantins'],
];

export type Office =
  | 'presidente' | 'vice_presidente' | 'governador' | 'vice_governador' | 'senador'
  | 'primeiro_suplente' | 'segundo_suplente' | 'deputado_federal' | 'deputado_estadual' | 'deputado_distrital';

export const OFFICE: Record<Office, string> = {
  presidente: 'Presidente', vice_presidente: 'Vice-presidente', governador: 'Governador', vice_governador: 'Vice-governador',
  senador: 'Senador', primeiro_suplente: '1º suplente', segundo_suplente: '2º suplente', deputado_federal: 'Deputado federal',
  deputado_estadual: 'Deputado estadual', deputado_distrital: 'Deputado distrital',
};

/** Short office labels of the choice screen (tabs and list header of the Comparar page). */
export const OFFICE_SHORT: Record<Office, string> = {
  presidente: 'Presidente', vice_presidente: 'Vice-presidente', governador: 'Governador', vice_governador: 'Vice-governador',
  senador: 'Senador', primeiro_suplente: '1º suplente', segundo_suplente: '2º suplente', deputado_federal: 'Dep. federal',
  deputado_estadual: 'Dep. estadual', deputado_distrital: 'Dep. distrital',
};

/** The UF spelled out for the state pill; "BR" is the national race. */
export function ufName(uf: string): string {
  if (uf === 'BR') return 'Brasil (presidente)';
  return UFS.find(([code]) => code === uf)?.[1] ?? uf;
}

/** The office chips of the Quando screen (Tela 6 spec, 5.5), in the service's order: "Deputado
 *  estadual" and "Deputado distrital" become one chip at the position of the first, and an office
 *  the labels do not know is spelled out from its code, never shown as the code itself. */
export function officeChips(offices: string[]): string[] {
  const merged = offices.includes('deputado_estadual') && offices.includes('deputado_distrital');
  const chips: string[] = [];
  for (const office of offices) {
    const label = merged && (office === 'deputado_estadual' || office === 'deputado_distrital')
      ? 'Deputado estadual ou distrital'
      : OFFICE[office as Office] ?? sentenceCase(office.replace(/_/g, ' '));
    if (!chips.includes(label)) chips.push(label);
  }
  return chips;
}

export const BALLOT_OFFICES: Office[] = ['presidente', 'governador', 'senador', 'deputado_federal', 'deputado_estadual', 'deputado_distrital'];

/**
 * The offices that exist for a UF. Fixes the local-review finding: the old page defaulted to
 * "presidente" for every UF, and the API answers 400 ("presidente só existe com uf = BR").
 */
export function officesFor(uf: string): Office[] {
  if (uf === 'BR') return ['presidente'];
  if (uf === 'DF') return ['governador', 'senador', 'deputado_federal', 'deputado_distrital'];
  return ['governador', 'senador', 'deputado_federal', 'deputado_estadual'];
}

export const NOMINATION: Record<string, string> = {coligacao: 'Coligação', federacao: 'Federação', partido_isolado: 'Partido isolado'};
