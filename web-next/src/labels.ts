// Labels the page owns (PT-BR for the voter); everything else comes from the API envelope.
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
export const ACCESS: Record<string, string> = {com_acessibilidade: 'Seção com acessibilidade', sem_acessibilidade: 'Seção sem acessibilidade'};
export const PLACE_STATUS: Record<string, string> = {ativo: 'Local ativo', bloqueado: 'Local bloqueado pelo TSE'};

export const INDEPENDENT_NOTICE = 'Projeto independente, não oficial, com dados abertos do TSE.';
