/** The yellow pill with the ballot number (Tela 1 spec, section 5.6): `--cv-yellow-tint` behind
 *  navy tabular digits. Decorative inside the candidacy card, whose accessible name says the number. */
export function NumberPill({n}: {n: number | string}) {
  return <span className="cv-numpill">{n}</span>;
}
