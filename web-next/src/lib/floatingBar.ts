/**
 * The mark a floating bar leaves on the document (casca spec, exception 2): while any
 * `FloatingBar` (the CompareTray included) is mounted, `<html>` carries this class and the
 * shell footer adds bottom clearance, so the end of the page is never hidden under the bar.
 * Counted, so two bars that overlap for a moment do not drop the class early.
 */
export const FLOATING_BAR_CLASS = 'cv-has-floating-bar';

let mounted = 0;

/** Marks `root` (the `<html>` element) and returns the function that unmarks it. */
export function markFloatingBar(root: {classList: Pick<DOMTokenList, 'add' | 'remove'>}): () => void {
  mounted += 1;
  root.classList.add(FLOATING_BAR_CLASS);
  let done = false;
  return () => {
    if (done) return;
    done = true;
    mounted -= 1;
    if (mounted === 0) root.classList.remove(FLOATING_BAR_CLASS);
  };
}
