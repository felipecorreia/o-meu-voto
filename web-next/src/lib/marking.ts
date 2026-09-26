// The marked set of the Comparar page in choice mode (Tela 1 spec, sections 2 and 4.1): between
// two and four candidacies, kept in the order of marking. That order is what the tray's slot
// colours follow (`slotColor`) and what the exit URL carries, so the comparison screen can
// paint the same candidacy with the same colour.

export const MIN_MARKED = 2;
export const MAX_MARKED = 4;

export interface Marked { sq_candidato: number }

/** The query of the exit link, `#/?uf=&office=&sq=a,b,c`: `sq` in the order of marking, never
 *  re-sorted (the service answers the comparison in ballot-number order anyway). */
export function compareParams(uf: string, office: string, marked: readonly Marked[]): {uf: string; office: string; sq: string} {
  return {uf, office, sq: marked.map(c => c.sq_candidato).join(',')};
}
