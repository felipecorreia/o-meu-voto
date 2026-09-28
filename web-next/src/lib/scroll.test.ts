import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {HIGHLIGHT_CLASS, scrollToId} from './scroll';

// No DOM in the test runner: a stand-in element with the members scroll.ts touches.
function fakeElement() {
  const classes = new Set<string>();
  const listeners = new Map<string, Set<() => void>>();
  return {
    offsetWidth: 0,
    scrollIntoView: vi.fn(),
    classList: {add: (c: string) => classes.add(c), remove: (c: string) => classes.delete(c), contains: (c: string) => classes.has(c)},
    addEventListener: (type: string, fn: () => void) => { (listeners.get(type) ?? listeners.set(type, new Set()).get(type)!).add(fn); },
    removeEventListener: (type: string, fn: () => void) => { listeners.get(type)?.delete(fn); },
    fire: (type: string) => { for (const fn of [...(listeners.get(type) ?? [])]) fn(); },
    listening: (type: string) => (listeners.get(type)?.size ?? 0) > 0,
  };
}

let el: ReturnType<typeof fakeElement>;
let reduced = false;
beforeEach(() => {
  el = fakeElement();
  reduced = false;
  vi.useFakeTimers();
  vi.stubGlobal('document', {getElementById: (id: string) => id === 'q-zona' ? el : null});
  vi.stubGlobal('matchMedia', (query: string) => ({matches: query.includes('reduced-motion') && reduced}));
});
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('scrollToId', () => {
  it('ignores an unknown id', () => {
    expect(() => scrollToId('q-xyz', {highlight: true})()).not.toThrow();
    expect(el.scrollIntoView).not.toHaveBeenCalled();
  });
  it('scrolls smoothly to the element without marking it', () => {
    scrollToId('q-zona');
    expect(el.scrollIntoView).toHaveBeenCalledWith({behavior: 'smooth', block: 'start'});
    expect(el.classList.contains(HIGHLIGHT_CLASS)).toBe(false);
    expect(el.listening('pointerdown')).toBe(false);
  });
  it('marks the element for 2.4 s', () => {
    scrollToId('q-zona', {highlight: true});
    expect(el.classList.contains(HIGHLIGHT_CLASS)).toBe(true);
    vi.advanceTimersByTime(2399);
    expect(el.classList.contains(HIGHLIGHT_CLASS)).toBe(true);
    vi.advanceTimersByTime(1);
    expect(el.classList.contains(HIGHLIGHT_CLASS)).toBe(false);
    expect(el.listening('pointerdown')).toBe(false);
    expect(el.listening('keydown')).toBe(false);
  });
  it('ends the mark early when the person touches the element', () => {
    scrollToId('q-zona', {highlight: true});
    vi.advanceTimersByTime(500);
    el.fire('pointerdown');
    expect(el.classList.contains(HIGHLIGHT_CLASS)).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });
  it('ends the mark through the returned function', () => {
    const end = scrollToId('q-zona', {highlight: true});
    end();
    expect(el.classList.contains(HIGHLIGHT_CLASS)).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });
  it('with reduced motion scrolls at once and keeps the mark until an interaction', () => {
    reduced = true;
    scrollToId('q-zona', {highlight: true});
    expect(el.scrollIntoView).toHaveBeenCalledWith({behavior: 'auto', block: 'start'});
    vi.advanceTimersByTime(60_000);
    expect(el.classList.contains(HIGHLIGHT_CLASS)).toBe(true);
    el.fire('keydown');
    expect(el.classList.contains(HIGHLIGHT_CLASS)).toBe(false);
  });
});
