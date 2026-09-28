import {useEffect, useState} from 'react';

export interface Route { path: string; params: URLSearchParams }

function parse(): Route {
  const raw = location.hash.replace(/^#/, '') || '/';
  const [path, query = ''] = raw.split('?');
  return {path: path || '/', params: new URLSearchParams(query)};
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(parse);
  useEffect(() => {
    const on = () => { setRoute(parse()); window.scrollTo({top: 0}); document.querySelector('main')?.scrollTo({top: 0}); };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return route;
}

export function href(path: string, params?: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
  const s = q.toString();
  return `#${path}${s ? `?${s}` : ''}`;
}

export function navigate(path: string, params?: Record<string, string | number | undefined | null>) {
  location.hash = href(path, params).slice(1);
}
