import {Theme} from '@astryxdesign/core/theme';
import {InternationalizationProvider} from '@astryxdesign/core/i18n';
import ptBR from '@astryxdesign/core/locales/pt-BR.json';
import {AppShell} from '@astryxdesign/core/AppShell';
import {TopNav, TopNavHeading, TopNavItem} from '@astryxdesign/core/TopNav';
import {Text} from '@astryxdesign/core/Text';
import {Calendar, Columns3, MapPin, Map as MapIcon, CircleHelp} from 'lucide-react';
import {cdeButterTheme} from './themes/cde';
import {useRoute} from './router';
import {ComparePage} from './pages/Compare';
import {CandidatePage} from './pages/Candidate';
import {WhereToVotePage} from './pages/WhereToVote';
import {PlacesPage} from './pages/Places';
import {WhenPage} from './pages/When';
import {FaqPage} from './pages/Faq';
import {INDEPENDENT_NOTICE} from './labels';

const NAV = [
  {path: '/', label: 'Comparar', icon: Columns3},
  {path: '/onde-voto', label: 'Onde voto', icon: MapPin},
  {path: '/locais', label: 'Locais', icon: MapIcon},
  {path: '/quando', label: 'Quando', icon: Calendar},
  {path: '/duvidas', label: 'Dúvidas', icon: CircleHelp},
] as const;

export function App() {
  const route = useRoute();
  const theme = cdeButterTheme;
  const isCandidate = route.path.startsWith('/candidato/');
  const selectedPath = isCandidate ? '/' : route.path;

  let page: React.ReactNode;
  if (isCandidate) page = <CandidatePage sq={Number(route.path.split('/')[2])} backHref={`#/${route.params.toString() ? `?${route.params}` : ''}`} />;
  else if (route.path === '/onde-voto') page = <WhereToVotePage />;
  else if (route.path === '/locais') page = <PlacesPage />;
  else if (route.path === '/quando') page = <WhenPage />;
  else if (route.path === '/duvidas') page = <FaqPage open={route.params.get('abrir')} />;
  else page = <ComparePage key={route.params.toString()} params={route.params} />;

  return (
    <InternationalizationProvider locale="pt-BR" messages={{'pt-BR': ptBR}}>
    <Theme theme={theme} mode="light">
      <AppShell
        contentPadding={0}
        height="auto"
        topNav={
          <TopNav
            label="Navegação principal"
            heading={<TopNavHeading heading="Compare o voto" subheading="Eleições 2026 · não oficial" headingHref="#/" logo={<span className="logo-dots" aria-hidden><i className="d d-blue" /><i className="d d-green" /><i className="d d-gold" /></span>} logoLabel="Compare o voto" />}
            startContent={NAV.map(n => <TopNavItem key={n.path} label={n.label} href={`#${n.path}`} isSelected={selectedPath === n.path} icon={<n.icon size={16} aria-hidden />} />)}
          />
        }>
        <div className="shell">
          {page}
          <footer className="site-footer">
            <Text as="p" size="sm" color="secondary">{INDEPENDENT_NOTICE} Dados sob licença CC-BY do Tribunal Superior Eleitoral (Portal de Dados Abertos). Este serviço não acessa o cadastro eleitoral: para saber a sua zona e seção, use o e-Título.</Text>
          </footer>
        </div>
      </AppShell>
    </Theme>
    </InternationalizationProvider>
  );
}
