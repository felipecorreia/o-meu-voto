/** The class scroll.ts puts on a highlighted element; styles.css animates it (Tela 7 spec, 4.3). */
export const HIGHLIGHT_CLASS = 'cv-highlight';
const HIGHLIGHT_MS = 2400;

export function prefersReducedMotion(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Scrolls the page to the element with `id`, leaving the sticky top clear through the element's
 * `scroll-margin-top`, and with `highlight` marks it with the yellow flash for 2.4 s. The mark
 * ends earlier when the person touches the element (pointer or keyboard). Reduced motion: the
 * scroll is instant and the mark stays until that interaction. Returns a function that ends the
 * mark, for a caller that unmounts or scrolls somewhere else first.
 */
export function scrollToId(id: string, {highlight = false}: {highlight?: boolean} = {}): () => void {
  const el = document.getElementById(id);
  if (!el) return () => {};
  const reduced = prefersReducedMotion();
  el.scrollIntoView({behavior: reduced ? 'auto' : 'smooth', block: 'start'});
  if (!highlight) return () => {};
  el.classList.remove(HIGHLIGHT_CLASS);
  void el.offsetWidth; // a reflow, so a second mark on the same element restarts the animation
  el.classList.add(HIGHLIGHT_CLASS);
  let timer: ReturnType<typeof setTimeout> | undefined;
  const clear = () => {
    if (timer !== undefined) clearTimeout(timer);
    el.classList.remove(HIGHLIGHT_CLASS);
    el.removeEventListener('pointerdown', clear);
    el.removeEventListener('keydown', clear);
  };
  el.addEventListener('pointerdown', clear);
  el.addEventListener('keydown', clear);
  if (!reduced) timer = setTimeout(clear, HIGHLIGHT_MS);
  return clear;
}
