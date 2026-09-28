export type Term = {t: string; d: string};

/** Terms with their explanation, a `<dl>` drawn as blocks on `--cv-surface-2` (Tela 7 spec, 5.4). */
export function TermList({terms}: {terms: Term[]}) {
  return <dl className="cv-termlist">
    {terms.map(term => <div key={term.t}><dt>{term.t}</dt><dd>{term.d}</dd></div>)}
  </dl>;
}
