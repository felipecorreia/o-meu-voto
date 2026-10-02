import type {RefObject} from 'react';
import {CodeXml, Menu} from 'lucide-react';
import {REPO_URL} from '../../lib/links';
import {SITE_NAME, type NavItemId} from '../../lib/routes';
import {BrandDots} from './BrandDots';
import {NavLinks} from './NavLinks';

export interface SiteHeaderProps {
  current: NavItemId;
  /** From 1024 px the links sit inline in the header and there is no menu button (spec 5.6). */
  wide: boolean;
  menuOpen: boolean;
  onMenuOpen: () => void;
  /** The menu button, so the menu can return focus to it when it closes. */
  menuButtonRef: RefObject<HTMLButtonElement | null>;
}

/** The sticky top of every screen (casca spec 5.1): dots, name, the "não oficial" pill and the
 *  menu button, or the inline links from 1024 px. */
export function SiteHeader({current, wide, menuOpen, onMenuOpen, menuButtonRef}: SiteHeaderProps) {
  return (
    <header className="cv-siteheader">
      <div className="cv-siteheader-in">
        <a className="cv-brand" href="#/" aria-label={`${SITE_NAME}, início`}>
          <BrandDots size={8} />
          <span className="cv-brand-name">{SITE_NAME}</span>
          <span className="cv-unofficial">não oficial</span>
        </a>
        {wide
          ? <div className="cv-siteheader-nav">
              <NavLinks variant="inline" current={current} />
              {REPO_URL ? (
                <a className="cv-siteheader-repo" href={REPO_URL} target="_blank" rel="noopener noreferrer" aria-label="Código no GitHub (repositório público, abre em nova aba)" title="Código no GitHub">
                  <CodeXml size={20} strokeWidth={2} aria-hidden />
                </a>
              ) : null}
            </div>
          : <button ref={menuButtonRef} type="button" className="cv-menubtn" aria-label="Abrir menu" aria-expanded={menuOpen} aria-controls="menu" onClick={onMenuOpen}>
              <Menu size={22} strokeWidth={1.8} aria-hidden />
            </button>}
      </div>
    </header>
  );
}
