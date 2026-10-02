// @vitest-environment happy-dom
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {renderToStaticMarkup} from 'react-dom/server';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {App} from '../../App';
import {FLOATING_BAR_CLASS, markFloatingBar} from '../../lib/floatingBar';
import {NAV_ITEMS, currentNavId, routeTitle} from '../../lib/routes';
import {FloatingBar} from './FloatingBar';
import {NavLinks} from './NavLinks';
import {SiteFooter} from './SiteFooter';

// The screens stay in their loading state: no request ever answers.
vi.mock('../../api', () => ({api: new Proxy({}, {get: () => () => new Promise(() => {})}), ApiError: class extends Error {}}));

(globalThis as {IS_REACT_ACT_ENVIRONMENT?: boolean}).IS_REACT_ACT_ENVIRONMENT = true;
const NOTICE = 'Projeto independente';
const route = (path: string, query = '') => ({path, params: new URLSearchParams(query)});
const flush = () => act(async () => { await Promise.resolve(); });
const wait = (ms: number) => act(() => new Promise(resolve => setTimeout(resolve, ms)));
const key = (target: Element | Document, key: string, init: KeyboardEventInit = {}) => act(() => { target.dispatchEvent(new KeyboardEvent('keydown', {key, bubbles: true, cancelable: true, ...init})); });
const go = (hash: string) => act(async () => { location.hash = hash; window.dispatchEvent(new HashChangeEvent('hashchange')); await Promise.resolve(); });
const viewport = (width: number, height: number) => (window as unknown as {happyDOM: {setViewport: (v: {width: number; height: number}) => void}}).happyDOM.setViewport({width, height});

describe('routes.ts', () => {
  it('titles every route "{título} · O meu voto" (spec 5.4)', () => {
    expect(routeTitle(route('/'))).toBe('Comparar candidaturas · O meu voto');
    expect(routeTitle(route('/', 'uf=SP&office=governador&sq=1,2'))).toBe('Comparação · O meu voto');
    expect(routeTitle(route('/candidato/250002541303', 'uf=SP'))).toBe('Ficha da candidatura · O meu voto');
    expect(routeTitle(route('/onde-voto'))).toBe('Onde voto · O meu voto');
    expect(routeTitle(route('/locais'))).toBe('Locais de votação · O meu voto');
    expect(routeTitle(route('/quando'))).toBe('Quando é a eleição · O meu voto');
    expect(routeTitle(route('/duvidas', 'abrir=cpf'))).toBe('Dúvidas frequentes · O meu voto');
    expect(routeTitle(route('/nada'))).toBe('Comparar candidaturas · O meu voto');
  });
  it('maps the profile and unknown paths to Comparar (spec 5.3)', () => {
    expect(currentNavId('/candidato/250002541303')).toBe('comparar');
    expect(currentNavId('/')).toBe('comparar');
    expect(currentNavId('/xyz')).toBe('comparar');
    expect(currentNavId('/onde-voto')).toBe('onde-voto');
    expect(currentNavId('/duvidas')).toBe('duvidas');
    expect(NAV_ITEMS.map(i => [i.id, i.href, i.label, i.sub])).toEqual([
      ['comparar', '#/', 'Comparar', 'Candidaturas lado a lado'],
      ['onde-voto', '#/onde-voto', 'Onde voto', 'Seu local pela zona e seção'],
      ['locais', '#/locais', 'Locais da cidade', 'Todos os locais de votação'],
      ['quando', '#/quando', 'Quando', 'Datas, horário e cargos'],
      ['duvidas', '#/duvidas', 'Dúvidas', 'Perguntas frequentes'],
    ]);
  });
});

describe('the floating-bar mark (exception 2; the footer under the bar at scroll end)', () => {
  it('keeps the class on the root while any bar is mounted', () => {
    const classes = new Set<string>();
    const root = {classList: {add: (c: string) => classes.add(c), remove: (c: string) => classes.delete(c)}};
    const a = markFloatingBar(root);
    const b = markFloatingBar(root);
    expect(classes.has(FLOATING_BAR_CLASS)).toBe(true);
    a(); a();
    expect(classes.has(FLOATING_BAR_CLASS)).toBe(true);
    b();
    expect(classes.has(FLOATING_BAR_CLASS)).toBe(false);
  });
  it('keeps the footer marked while FloatingBar is mounted and unmarks it on unmount', async () => {
    const host = document.body.appendChild(document.createElement('div'));
    const root = createRoot(host);
    await act(() => root.render(<><FloatingBar>bar</FloatingBar><SiteFooter repoUrl={null} /></>));
    expect(host.querySelector('footer.cv-sitefooter')).not.toBeNull();
    expect(document.documentElement.classList.contains(FLOATING_BAR_CLASS)).toBe(true);
    await act(() => root.render(<SiteFooter repoUrl={null} />));
    expect(host.querySelector('footer.cv-sitefooter')).not.toBeNull();
    expect(document.documentElement.classList.contains(FLOATING_BAR_CLASS)).toBe(false);
    await act(() => root.unmount());
    host.remove();
  });
});

describe('SiteFooter and NavLinks markup', () => {
  it('says the independent-project notice once, with the licences and the signature (5.5, 5.7)', () => {
    const html = renderToStaticMarkup(<SiteFooter repoUrl={null} />);
    expect(html.split(NOTICE)).toHaveLength(2);
    expect(html).toContain('Projeto independente e não oficial');
    expect(html).toContain('Feito com os dados abertos do TSE. Sem cadastro, sem CPF, sem título: nada é guardado.');
    expect(html).toContain('Dados do TSE sob licença CC-BY. Este serviço não acessa o cadastro eleitoral. Código sob licença MIT.');
    expect(html).toContain('O meu voto · Eleições 2026');
    expect(html).toContain('href="#/duvidas"');
    expect(html).not.toContain('Código aberto');
    expect(html).toContain('Feito por <a href="https://github.com/felipecorreia" target="_blank" rel="noopener noreferrer">Felipe Correia</a>');
  });
  it('shows "Código aberto" in a new tab only with a real REPO_URL (criterion 8)', () => {
    const html = renderToStaticMarkup(<SiteFooter repoUrl="https://example.org/repo" />);
    expect(html).toContain('href="https://example.org/repo" target="_blank" rel="noopener noreferrer"');
    expect(html).toContain('Código aberto');
    expect(html).toContain('<a href="https://example.org/repo" target="_blank" rel="noopener noreferrer">Código aberto no GitHub</a>');
  });
  it('marks the current item with aria-current in both variants; only the drawer has subtitles', () => {
    const drawer = renderToStaticMarkup(<NavLinks variant="drawer" current="onde-voto" />);
    expect(drawer).toContain('<nav aria-label="Principal" class="cv-navlinks cv-navlinks-drawer">');
    expect(drawer.match(/aria-current="page"/g)).toHaveLength(1);
    expect(drawer).toContain('href="#/onde-voto" class="cv-navitem" aria-current="page"');
    expect(drawer).toContain('Seu local pela zona e seção');
    const inline = renderToStaticMarkup(<NavLinks variant="inline" current="comparar" />);
    expect(inline).toContain('href="#/" class="cv-navitem" aria-current="page"');
    expect(inline).not.toContain('Seu local pela zona e seção');
    expect(inline).not.toContain('cv-navitem-icon');
  });
});

describe('the shell in a document', () => {
  let host: HTMLDivElement;
  let root: Root;
  const text = () => document.body.textContent ?? '';
  const menuButton = () => document.querySelector<HTMLButtonElement>('button[aria-controls="menu"]');
  const dialog = () => document.getElementById('menu');
  const mount = async () => { root = createRoot(host); await act(() => root.render(<App />)); await flush(); };

  beforeEach(async () => {
    viewport(390, 844);
    document.documentElement.style.overflow = '';
    location.hash = '#/onde-voto';
    host = document.body.appendChild(document.createElement('div'));
  });
  afterEach(async () => { await act(() => root.unmount()); host.remove(); });

  it('puts the skip link first, sends it to <main id="conteudo"> and titles the tab (criteria 9, 10)', async () => {
    await mount();
    const first = document.querySelector('a[href], button');
    expect(first?.textContent).toBe('Pular para o conteúdo');
    expect(first?.getAttribute('href')).toBe('#conteudo');
    await act(() => { (first as HTMLAnchorElement).click(); });
    expect(document.activeElement?.id).toBe('conteudo');
    expect(document.activeElement?.tagName).toBe('MAIN');
    expect(location.hash).toBe('#/onde-voto');
    expect(document.title).toBe('Onde voto · O meu voto');
  });

  it('opens the menu on the current item, traps Tab, closes on Esc and gives focus back (criteria 2, 4)', async () => {
    await mount();
    expect(text().split(NOTICE)).toHaveLength(2);
    expect(dialog()).toBeNull();
    await act(() => { menuButton()!.click(); });
    const menu = dialog()!;
    expect(menu.getAttribute('role')).toBe('dialog');
    expect(menu.getAttribute('aria-modal')).toBe('true');
    expect(menuButton()!.getAttribute('aria-expanded')).toBe('true');
    expect(document.documentElement.style.overflow).toBe('hidden');
    const current = menu.querySelector<HTMLAnchorElement>('a[aria-current="page"]')!;
    expect(current.getAttribute('href')).toBe('#/onde-voto');
    expect(current.textContent).toContain('Onde voto');
    expect(document.activeElement).toBe(current);
    expect(document.querySelectorAll('nav[aria-label="Principal"]')).toHaveLength(1);
    const repo = [...menu.querySelectorAll<HTMLAnchorElement>('a')].find(a => a.textContent?.includes('Código no GitHub'))!;
    expect(repo.getAttribute('href')).toBe('https://github.com/felipecorreia/o-meu-voto');
    expect(repo.getAttribute('target')).toBe('_blank');
    expect(repo.getAttribute('rel')).toBe('noopener noreferrer');
    // Tab from the last focusable element wraps to the first one; Shift+Tab the other way.
    const focusables = menu.querySelectorAll<HTMLElement>('a[href], button');
    focusables[focusables.length - 1].focus();
    key(document.activeElement!, 'Tab');
    expect(document.activeElement).toBe(focusables[0]);
    key(document.activeElement!, 'Tab', {shiftKey: true});
    expect(document.activeElement).toBe(focusables[focusables.length - 1]);
    key(document, 'Escape');
    expect(menuButton()!.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(menuButton());
    expect(document.documentElement.style.overflow).toBe('');
    await wait(250);
    expect(dialog()).toBeNull();
  });

  it('closes on the scrim, on a chosen item and on a route change, which focuses the content (criteria 3, 4)', async () => {
    await mount();
    await act(() => { menuButton()!.click(); });
    await act(() => { document.querySelector<HTMLButtonElement>('.cv-navmenu-scrim')!.click(); });
    expect(menuButton()!.getAttribute('aria-expanded')).toBe('false');
    await wait(250);
    expect(dialog()).toBeNull();
    await act(() => { menuButton()!.click(); });
    const quando = dialog()!.querySelector<HTMLAnchorElement>('a[href="#/quando"]')!;
    await act(() => { quando.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true})); });
    expect(menuButton()!.getAttribute('aria-expanded')).toBe('false');
    await go('#/quando');
    expect(document.title).toBe('Quando é a eleição · O meu voto');
    expect(document.activeElement?.id).toBe('conteudo');
    expect(document.querySelector('.cv-shell > [aria-live="polite"]')?.textContent).toBe('Quando é a eleição · O meu voto');
    await wait(250);
    expect(dialog()).toBeNull();
    await go('#/candidato/250002541303?uf=SP');
    expect(document.title).toBe('Ficha da candidatura · O meu voto');
    await act(() => { menuButton()!.click(); });
    expect(dialog()!.querySelector('a[aria-current="page"]')?.getAttribute('href')).toBe('#/');
  });

  it('shows the five links inline and no menu button from 1024 px (criterion 5)', async () => {
    viewport(1280, 800);
    await mount();
    expect(menuButton()).toBeNull();
    const nav = document.querySelectorAll('nav[aria-label="Principal"]');
    expect(nav).toHaveLength(1);
    expect(nav[0].closest('header')).not.toBeNull();
    expect(nav[0].querySelectorAll('a')).toHaveLength(5);
    expect(nav[0].querySelector('a[aria-current="page"]')?.getAttribute('href')).toBe('#/onde-voto');
    const repo = document.querySelector<HTMLAnchorElement>('header a[aria-label^="Código no GitHub"]')!;
    expect(repo.getAttribute('href')).toBe('https://github.com/felipecorreia/o-meu-voto');
    expect(repo.getAttribute('target')).toBe('_blank');
    expect(repo.getAttribute('rel')).toBe('noopener noreferrer');
    expect(nav[0].contains(repo)).toBe(false);
    expect(text().split(NOTICE)).toHaveLength(2);
  });

  it('removes the drawer immediately on desktop resize and focuses the current inline link', async () => {
    await mount();
    await act(() => { menuButton()!.click(); });
    expect(document.activeElement).toBe(dialog()!.querySelector('a[aria-current="page"]'));
    await act(async () => { viewport(1280, 800); await Promise.resolve(); });
    const nav = document.querySelectorAll('nav[aria-label="Principal"]');
    expect(nav).toHaveLength(1);
    expect(nav[0].closest('header')).not.toBeNull();
    expect(dialog()).toBeNull();
    expect(document.activeElement).toBe(nav[0].querySelector('a[aria-current="page"]'));
  });
});
