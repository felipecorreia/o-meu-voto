import {useEffect, type RefObject} from 'react';

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusable(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(el => !el.hasAttribute('aria-hidden') && !el.closest('[inert]'));
}

/**
 * Keeps `Tab` and `Shift+Tab` inside `ref` while `active` (the WAI-ARIA modal dialog pattern,
 * casca spec 5.2). The listener sits on the document, so focus that left the panel (a tap on
 * the scrim, which is focusable by pointer) is pulled back on the next Tab.
 */
export function useFocusTrap(ref: RefObject<HTMLElement | null>, active: boolean): void {
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      const root = ref.current;
      if (e.key !== 'Tab' || !root) return;
      const items = focusable(root);
      if (!items.length) { e.preventDefault(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      const current = document.activeElement;
      const inside = current instanceof HTMLElement && root.contains(current);
      if (e.shiftKey ? current === first || !inside : current === last || !inside) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [ref, active]);
}
