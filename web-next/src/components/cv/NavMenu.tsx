import {useEffect, useRef, useState, type CSSProperties, type RefObject} from 'react';
import {createPortal} from 'react-dom';
import {CodeXml, X} from 'lucide-react';
import {REPO_URL} from '../../lib/links';
import type {NavItemId} from '../../lib/routes';
import {prefersReducedMotion} from '../../lib/scroll';
import {useFocusTrap} from '../../lib/useFocusTrap';
import {cvTokens} from '../../themes/cde';
import {NavLinks} from './NavLinks';

/** The exit animation of spec 4.3 (.2 s); the markup leaves after it. */
const CLOSE_MS = 200;

export interface NavMenuProps {
  open: boolean;
  wide: boolean;
  current: NavItemId;
  onClose: () => void;
  /** Where focus returns when the menu closes: the header's menu button. */
  returnFocusTo: RefObject<HTMLElement | null>;
}

/**
 * The side menu (casca spec 5.2): a modal dialog in a portal on `body`, present only while
 * open (plus the .2 s exit). Opening focuses the current item and locks the page scroll;
 * the close button, the scrim, Esc, choosing an item, a route change and the window reaching
 * 1024 px close it (the last two through `open`, from the shell). Focus returns to the menu
 * button unless the page moved it meanwhile; at 1024 px it moves to the current inline link,
 * falling back to `<main>`. The open state never reaches the URL.
 */
export function NavMenu({open, wide, current, onClose, returnFocusTo}: NavMenuProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [closing, setClosing] = useState(false);
  const wasOpen = useRef(false);
  const wideRef = useRef(wide);
  wideRef.current = wide;
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  useFocusTrap(panelRef, open);

  useEffect(() => {
    if (wide) { wasOpen.current = false; setClosing(false); return; }
    if (open) { wasOpen.current = true; setClosing(false); return; }
    if (!wasOpen.current) return;
    wasOpen.current = false;
    if (prefersReducedMotion()) return;
    setClosing(true);
    const timer = setTimeout(() => setClosing(false), CLOSE_MS);
    return () => clearTimeout(timer);
  }, [open, wide]);

  useEffect(() => {
    if (!open) return;
    const html = document.documentElement;
    const previousOverflow = html.style.overflow;
    html.style.overflow = 'hidden';
    const panel = panelRef.current;
    (panel?.querySelector<HTMLElement>('[aria-current="page"]') ?? panel?.querySelector<HTMLElement>('a[href], button'))?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.preventDefault(); onCloseRef.current(); } };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      html.style.overflow = previousOverflow;
      const active = document.activeElement;
      if (!active || active === document.body || rootRef.current?.contains(active)) {
        if (wideRef.current) {
          (document.querySelector<HTMLElement>('header nav[aria-label="Principal"] a[aria-current="page"]')
            ?? document.querySelector<HTMLElement>('main#conteudo'))?.focus({preventScroll: true});
        } else returnFocusTo.current?.focus();
      }
    };
  }, [open, returnFocusTo]);

  if (wide || (!open && !closing)) return null;
  return createPortal(
    <div ref={rootRef} className={`cv-navmenu${open ? '' : ' cv-navmenu-closing'}`} style={cvTokens as CSSProperties} inert={!open}>
      <button type="button" tabIndex={-1} aria-hidden className="cv-navmenu-scrim" onClick={onClose} />
      <div ref={panelRef} id="menu" role="dialog" aria-modal="true" aria-labelledby="menu-title" className="cv-navmenu-panel">
        <div className="cv-navmenu-head">
          <h2 id="menu-title">Menu</h2>
          <button type="button" className="cv-navmenu-close" aria-label="Fechar menu" onClick={onClose}><X size={18} strokeWidth={2.2} aria-hidden /></button>
        </div>
        <NavLinks variant="drawer" current={current} onPick={onClose} />
        {REPO_URL ? (
          <a className="cv-navitem cv-navmenu-repo" href={REPO_URL} target="_blank" rel="noopener noreferrer">
            <span className="cv-navitem-icon" aria-hidden><CodeXml size={19} strokeWidth={2} /></span>
            <span className="cv-navitem-text">
              <span className="cv-navitem-label">Código no GitHub</span>
              <span className="cv-navitem-sub">Repositório público, abre em nova aba</span>
            </span>
          </a>
        ) : null}
        <div className="cv-navmenu-foot">
          <span className="cv-unofficial">não oficial</span>
          <span>Projeto independente, feito com os dados abertos do TSE. Eleições 2026.</span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
