import {useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode} from 'react';
import {Theme} from '@astryxdesign/core/theme';
import {InternationalizationProvider} from '@astryxdesign/core/i18n';
import ptBR from '@astryxdesign/core/locales/pt-BR.json';
import {cdeButterTheme, cvTokens} from './themes/cde';
import {useRoute} from './router';
import {useMedia} from './lib/useMedia';
import {currentNavId, routeTitle} from './lib/routes';
import {NavMenu} from './components/cv/NavMenu';
import {SiteFooter} from './components/cv/SiteFooter';
import {SiteHeader} from './components/cv/SiteHeader';
import {SkipLink} from './components/cv/SkipLink';
import {ComparePage} from './pages/Compare';
import {CandidatePage} from './pages/Candidate';
import {WhereToVotePage} from './pages/WhereToVote';
import {PlacesPage} from './pages/Places';
import {WhenPage} from './pages/When';
import {FaqPage} from './pages/Faq';

/**
 * The shell (casca spec): skip link, sticky header, the screen inside `<main id="conteudo">`,
 * the global footer and the side menu. The router is the hash router of `router.ts`, unchanged:
 * it re-parses the hash and scrolls to the top on every change, and the shell reacts here.
 */
export function App() {
  const route = useRoute();
  const wide = useMedia('(min-width: 1024px)');
  const [menuOpen, setMenuOpen] = useState(false);
  const [announced, setAnnounced] = useState('');
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const lastPath = useRef(route.path);
  const current = currentNavId(route.path);
  const title = routeTitle(route);

  useEffect(() => { document.title = title; }, [title]);
  // Any route change closes the menu. A change of path (not of the query alone) moves focus to
  // the content, unless the screen moves it afterwards, and announces the new title (spec 5.4).
  useEffect(() => {
    setMenuOpen(false);
    if (lastPath.current === route.path) return;
    lastPath.current = route.path;
    mainRef.current?.focus({preventScroll: true});
    setAnnounced(title);
  }, [route, title]);
  useEffect(() => { if (wide) setMenuOpen(false); }, [wide]);
  const openMenu = useCallback(() => setMenuOpen(true), []);
  const closeMenu = useCallback(() => setMenuOpen(false), []);

  const isCandidate = route.path.startsWith('/candidato/');
  let page: ReactNode;
  if (isCandidate) page = <CandidatePage sq={Number(route.path.split('/')[2])} backHref={`#/${route.params.toString() ? `?${route.params}` : ''}`} />;
  else if (route.path === '/onde-voto') page = <WhereToVotePage />;
  else if (route.path === '/locais') page = <PlacesPage />;
  else if (route.path === '/quando') page = <WhenPage />;
  else if (route.path === '/duvidas') page = <FaqPage open={route.params.get('abrir')} />;
  else page = <ComparePage key={route.params.toString()} params={route.params} />;

  return (
    <InternationalizationProvider locale="pt-BR" messages={{'pt-BR': ptBR}}>
      <Theme theme={cdeButterTheme} mode="light">
        <div className="cv-shell" style={cvTokens as CSSProperties}>
          <SkipLink />
          <SiteHeader current={current} wide={wide} menuOpen={menuOpen} onMenuOpen={openMenu} menuButtonRef={menuButtonRef} />
          <main id="conteudo" tabIndex={-1} ref={mainRef}>{page}</main>
          <SiteFooter />
          <span className="cv-sr-only" aria-live="polite">{announced}</span>
          <NavMenu open={menuOpen && !wide} wide={wide} current={current} onClose={closeMenu} returnFocusTo={menuButtonRef} />
        </div>
      </Theme>
    </InternationalizationProvider>
  );
}
