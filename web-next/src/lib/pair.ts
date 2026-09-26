// The pair on screen in the comparison mode of the Comparar page on phones (Tela 2 spec,
// sections 2 and 5.3 to 5.4): with three or four candidacies, exactly two columns are shown,
// chosen from the compared set. The candidacies are always in ballot-number order, as the
// service answers them; `pair` names the two on screen by sq_candidato, left column first.
// The replacement rules follow the reference prototype (`Tela2-depois-par.dc.html`): a candidacy
// brought in replaces the column changed least recently, and a column's swap button goes to
// the next candidacy off screen in ballot order, wrapping to the first. The spec takes
// precedence over the prototype: after a replacement the columns keep ballot-number order.

export type Pair = [number, number];
/** Left column (0) or right column (1). */
export type Column = 0 | 1;

export interface PairState {
  pair: Pair;
  /** The column changed least recently: the one the next "Trazer" replaces. */
  older: Column;
}

export interface Ordered { sq_candidato: number; number: number }

function orderedPair(pair: Pair, candidates: readonly Ordered[]): Pair {
  const position = (sq: number) => candidates.findIndex(c => c.sq_candidato === sq);
  return position(pair[0]) < position(pair[1]) ? pair : [pair[1], pair[0]];
}

/** Replace the older candidacy, then restore ballot order. The untouched candidacy remains
 *  the older one even when sorting moves it to the other column. */
function replaceColumn(state: PairState, sq: number, column: Column, candidates: readonly Ordered[]): PairState {
  const untouched = state.pair[column === 0 ? 1 : 0];
  const next: Pair = [...state.pair];
  next[column] = sq;
  const pair = orderedPair(next, candidates);
  return {pair, older: pair.indexOf(untouched) as Column};
}

/** The pair to show: the URL's when both are distinct members of `candidates`, else the two
 *  lowest ballot numbers. `candidates` must already be in ballot-number order. */
export function resolvePair(candidates: readonly Ordered[], wanted: readonly number[] | null | undefined): Pair {
  if (wanted && wanted.length === 2 && wanted[0] !== wanted[1] && wanted.every(sq => candidates.some(c => c.sq_candidato === sq))) {
    return orderedPair([wanted[0], wanted[1]], candidates);
  }
  return [candidates[0].sq_candidato, candidates[1].sq_candidato];
}

export function pairAfterRemoval(candidates: readonly Ordered[], wanted: Pair | null, removed: number): Pair | null {
  if (!wanted) return null;
  const remaining = candidates.filter(c => c.sq_candidato !== removed);
  return resolvePair(remaining, wanted.includes(removed) ? null : wanted);
}

/** "Trazer": `sq` replaces the least recently changed candidacy; the untouched one becomes older.
 *  A candidacy already on screen changes nothing. */
export function bringIn(state: PairState, sq: number, candidates: readonly Ordered[]): PairState {
  if (state.pair.includes(sq) || !candidates.some(c => c.sq_candidato === sq)) return state;
  return replaceColumn(state, sq, state.older, candidates);
}

/** The column's swap button: the next candidacy off screen in ballot order after the one in
 *  that column, wrapping to the first off screen; the other column becomes the older one.
 *  With nobody off screen (two candidacies) nothing changes. */
export function swapNext(state: PairState, candidates: readonly Ordered[], column: Column): PairState {
  const current = state.pair[column];
  const off = candidates.filter(c => !state.pair.includes(c.sq_candidato));
  if (!off.length) return state;
  const here = candidates.findIndex(c => c.sq_candidato === current);
  const next = off.find(c => candidates.indexOf(c) > here) ?? off[0];
  return replaceColumn(state, next.sq_candidato, column, candidates);
}
