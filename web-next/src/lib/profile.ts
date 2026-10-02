import type {CandidateProfile} from '../api';
import {UFS} from '../labels';
import {href} from '../router';
import {parseSqList} from './marking';
import {isSlot, type Slot} from './slotColor';

const validUf = (value: string | null | undefined): value is string => UFS.some(([uf]) => uf === value);

/** The profile API omits UF. Its service-generated official URL carries the electoral unit
 * in its last fragment segment (core/divulgacandcontas.py). Never infer it from the sq.
 * Route context is a fallback when the calendar has no official election id. */
export function profileUf(c: Pick<CandidateProfile, 'office' | 'divulgacandcontas_url'>, contextUf?: string | null): string | undefined {
  if (c.office === 'presidente' || c.office === 'vice_presidente') return 'BR';
  if (c.divulgacandcontas_url) {
    try {
      const url = new URL(c.divulgacandcontas_url);
      const unit = url.hash.split('?')[0].split('/').filter(Boolean).at(-1);
      if (url.hostname === 'divulgacandcontas.tse.jus.br' && validUf(unit)) return unit;
    } catch { /* no trustworthy unit in this URL */ }
  }
  return validUf(contextUf) ? contextUf : undefined;
}

/** App supplies its existing backHref; only this screen interprets the comparison context. */
export function profileNavigation(c: CandidateProfile, params: URLSearchParams) {
  const cmp = parseSqList(params.get('cmp'));
  const uf = profileUf(c, params.get('uf'));
  const index = cmp.indexOf(c.sq_candidato) + 1;
  const slot: Slot | undefined = isSlot(index) ? index : undefined;
  const backHref = cmp.length ? href('/', {
    uf: params.get('uf') || uf, office: params.get('office') || c.office,
    sq: cmp.join(','), pair: params.get('pair'), tab: params.get('tab'),
  }) : href('/', {uf, office: c.office});
  return {uf, slot, fromComparison: cmp.length > 0, backHref,
    chooseHref: href('/', {uf, office: c.office, marcar: cmp.length ? cmp.join(',') : c.sq_candidato})};
}

export function profileShare(c: CandidateProfile, name: string, office: string, uf: string | undefined, pageUrl: string) {
  const url = new URL(pageUrl);
  url.search = '';
  url.hash = `/candidato/${c.sq_candidato}`;
  return {title: `${name} (${c.number}) · O meu voto`, url: url.toString(),
    text: `Ficha de ${name} (${c.number}), candidatura a ${office}${uf ? ` (${uf})` : ''}, com os dados abertos do TSE: ${url}`};
}

/** The profile endpoint has no note field. These are the exact current service explanations
 * from core/core.py VOTE_DESTINATION_NOTES; unknown terms deliberately get no explanation. */
export const VOTE_DESTINATION_NOTES: Record<string, string> = {
  'Válido': 'Pela situação atual no TSE, os votos neste número contam para a candidatura.',
  'Anulado sub judice': 'O registro depende de decisão judicial ainda pendente: pela situação atual no TSE, os votos neste número ficam anulados e só passam a contar se a decisão final for favorável à candidatura.',
  'Nulo técnico': 'Pela situação atual no TSE, os votos neste número são nulos e não contam para a candidatura.',
};
