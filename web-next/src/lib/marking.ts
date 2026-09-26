// The marked set of the Comparar page in choice mode (Tela 1 spec, sections 2 and 4.1): between
// two and four candidacies, kept in the order of marking. That order is what the tray's slot
// colours follow (`slotColor`) and what the exit URL carries, so the comparison screen (Tela 2
// spec, section 4.1) paints the same candidacy with the same colour: its slot is its position
// in the URL's `sq`, whatever the column order (always the ballot number).

import type {Slot} from './slotColor';

export const MIN_MARKED = 2;
export const MAX_MARKED = 4;

export interface Marked { sq_candidato: number }

export async function loadPreloaded<T extends Marked>(sq: readonly number[], load: (id: number) => Promise<T | null>): Promise<T[]> {
  const results = await Promise.allSettled(sq.map(load));
  return results.flatMap((result, i) => result.status === 'fulfilled' && result.value?.sq_candidato === sq[i] ? [result.value] : []);
}

export function mergePreloaded<T extends Marked>(order: readonly number[], preloaded: readonly T[], current: Map<number, T>, touched: ReadonlySet<number>): Map<number, T> {
  const preloadById = new Map(preloaded.map(c => [c.sq_candidato, c]));
  const orderIds = new Set(order);
  const additions = Array.from(current.values()).filter(c => !orderIds.has(c.sq_candidato));
  const available = MAX_MARKED - additions.length;
  const merged = new Map<number, T>();
  for (const id of order) {
    if (merged.size >= available) break;
    const c = preloadById.get(id) ?? current.get(id);
    if (c && (!touched.has(id) || current.has(id))) merged.set(id, c);
  }
  for (const c of additions) {
    if (merged.size >= MAX_MARKED) break;
    merged.set(c.sq_candidato, c);
  }
  return merged;
}

/** The query of the exit link, `#/?uf=&office=&sq=a,b,c`: `sq` in the order of marking, never
 *  re-sorted (the service answers the comparison in ballot-number order anyway). */
export function compareParams(uf: string, office: string, marked: readonly Marked[]): {uf: string; office: string; sq: string} {
  return {uf, office, sq: marked.map(c => c.sq_candidato).join(',')};
}

/** The `sq` (or `marcar`) list of a URL, "a,b,c", in the order it was written: the order of
 *  marking. Blanks and non-numbers are dropped, duplicates keep their first position. */
export function parseSqList(value: string | null | undefined): number[] {
  const out: number[] = [];
  for (const part of (value ?? '').split(',')) {
    const n = Number(part.trim());
    if (part.trim() && Number.isInteger(n) && n > 0 && !out.includes(n)) out.push(n);
  }
  return out;
}

/** The slot of a candidacy in the comparison: its position in the URL's `sq` (1 to 4). A
 *  candidacy the URL does not name (it cannot happen: the service answers only what was
 *  asked) takes `fallback`, its position among the compared ones; both are capped at four. */
export function slotOf(sqOrder: readonly number[], sq: number, fallback: number): Slot {
  const i = sqOrder.indexOf(sq);
  const position = i >= 0 ? i + 1 : fallback;
  return Math.min(Math.max(position, 1), MAX_MARKED) as Slot;
}
