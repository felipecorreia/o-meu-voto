/**
 * The shell's view of the router (casca spec, 5.3 and 5.4): the five destinations of the menu,
 * which of them a path belongs to, and the tab title of a route. The router itself
 * (`router.ts`) is untouched: hrefs stay hash links.
 */
import type {LucideIcon} from 'lucide-react';
import {Calendar, CircleHelp, Columns2, Map as MapIcon, MapPin} from 'lucide-react';
import type {Route} from '../router';

export const SITE_NAME = 'Compare o voto';

export type NavItemId = 'comparar' | 'onde-voto' | 'locais' | 'quando' | 'duvidas';

export interface NavItem {
  id: NavItemId;
  href: string;
  label: string;
  sub: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: readonly NavItem[] = [
  {id: 'comparar', href: '#/', label: 'Comparar', sub: 'Candidaturas lado a lado', icon: Columns2},
  {id: 'onde-voto', href: '#/onde-voto', label: 'Onde voto', sub: 'Seu local pela zona e seção', icon: MapPin},
  {id: 'locais', href: '#/locais', label: 'Locais da cidade', sub: 'Todos os locais de votação', icon: MapIcon},
  {id: 'quando', href: '#/quando', label: 'Quando', sub: 'Datas, horário e cargos', icon: Calendar},
  {id: 'duvidas', href: '#/duvidas', label: 'Dúvidas', sub: 'Perguntas frequentes', icon: CircleHelp},
];

/** The menu item a path belongs to. `candidato/*` counts as Comparar, and so does any path the
 *  router does not know, since it falls back to the Comparar page. */
export function currentNavId(path: string): NavItemId {
  switch (path) {
    case '/onde-voto': case '/locais': case '/quando': case '/duvidas':
      return path.slice(1) as NavItemId;
    default:
      return 'comparar';
  }
}

/** The tab title of a route, "{título} · Compare o voto" (spec 5.4). The profile page replaces
 *  "Ficha da candidatura" by the name once it loads. */
export function routeTitle(route: Route): string {
  const title = route.path.startsWith('/candidato/') ? 'Ficha da candidatura'
    : route.path === '/onde-voto' ? 'Onde voto'
    : route.path === '/locais' ? 'Locais de votação'
    : route.path === '/quando' ? 'Quando é a eleição'
    : route.path === '/duvidas' ? 'Dúvidas frequentes'
    : route.params.get('sq') ? 'Comparação'
    : 'Comparar candidaturas';
  return `${title} · ${SITE_NAME}`;
}
