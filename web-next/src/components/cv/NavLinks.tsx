import {NAV_ITEMS, type NavItemId} from '../../lib/routes';

export interface NavLinksProps {
  /** `drawer`: the 64 px cards of the menu; `inline`: the pills of the desktop header. */
  variant: 'drawer' | 'inline';
  current: NavItemId;
  /** Called when an item is chosen (the menu closes on it); the link itself navigates. */
  onPick?: () => void;
}

/** The five destinations as the one `<nav aria-label="Principal">` of the page (casca spec 5.3):
 *  the current item carries `aria-current="page"`, so colour is never the only signal. */
export function NavLinks({variant, current, onPick}: NavLinksProps) {
  return (
    <nav aria-label="Principal" className={`cv-navlinks cv-navlinks-${variant}`}>
      {NAV_ITEMS.map(item => {
        const on = item.id === current;
        return (
          <a key={item.id} href={item.href} className="cv-navitem" aria-current={on ? 'page' : undefined} onClick={onPick}>
            {variant === 'drawer' ? <span className="cv-navitem-icon" aria-hidden><item.icon size={19} strokeWidth={2} /></span> : null}
            <span className="cv-navitem-text">
              <span className="cv-navitem-label">{item.label}</span>
              {variant === 'drawer' ? <span className="cv-navitem-sub">{item.sub}</span> : null}
            </span>
          </a>
        );
      })}
    </nav>
  );
}
