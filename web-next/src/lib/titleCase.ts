// Title case for the ballot names the TSE ships in upper case (Tela 1 spec, section 5.6).

const LOWER_PARTICLES = new Set(['de', 'da', 'do', 'das', 'dos', 'e']);

/** "FERNANDO HADDAD" -> "Fernando Haddad": every word capitalised (after a hyphen or an
 *  apostrophe too), the particles de/da/do/das/dos/e lower-cased unless they open the name,
 *  accents kept. The upper-case original stays the value for aria-labels and for the
 *  comparison screen. */
export function toTitleCase(name: string): string {
  return name.trim().split(/\s+/).map((word, i) => {
    const lower = word.toLocaleLowerCase('pt-BR');
    if (i > 0 && LOWER_PARTICLES.has(lower)) return lower;
    return lower.replace(/(^|[-'’])(\p{L})/gu, (_, sep: string, ch: string) => sep + ch.toLocaleUpperCase('pt-BR'));
  }).join(' ');
}
