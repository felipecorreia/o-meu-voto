/**
 * A rail of options with a white highlight that slides to the chosen one (Tela 1 spec, section
 * 5.3). A choice of value, not of panel, so it is a radiogroup: ←/→ (and ↑/↓, Home, End) move
 * the choice. `left`/`width` of the highlight are measured from the checked button and
 * re-measured on resize, when the options change and when the font finishes loading. Below
 * 640 px the rail scrolls sideways when the labels do not fit and a tab picked while partly off
 * the rail scrolls into view; from 640 px the rail is as wide as its labels. With `fill` (the
 * comparison's Chapa / Patrimônio / Ocupação, Tela 2 spec 5.5 and 5.12) the rail is as wide as
 * its container with equal options up to 1023 px, and as wide as its labels from 1024 px.
 */
import {useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent} from 'react';

export interface SlidingTabOption<T extends string> { value: T; label: string }

export interface SlidingTabsProps<T extends string> {
  options: ReadonlyArray<SlidingTabOption<T>>;
  value: T;
  onChange: (value: T) => void;
  /** Accessible name of the group ("Cargo"). */
  ariaLabel: string;
  /** Full width with equal options below 1024 px. */
  fill?: boolean;
  /** Turn selectors use tabs; existing choice groups retain radio semantics. */
  role?: 'radiogroup' | 'tablist';
  ariaLabelledby?: string;
}

const CHECKED = '[aria-checked="true"], [role="tab"][aria-selected="true"]';

export function SlidingTabs<T extends string>({options, value, onChange, ariaLabel, fill = false, role = 'radiogroup', ariaLabelledby}: SlidingTabsProps<T>) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [highlight, setHighlight] = useState<{left: number; width: number} | null>(null);
  const userPicked = useRef(false);

  const measure = useCallback(() => {
    const active = trackRef.current?.querySelector<HTMLButtonElement>(CHECKED);
    if (!active) { setHighlight(null); return; }
    setHighlight(prev => prev && prev.left === active.offsetLeft && prev.width === active.offsetWidth ? prev : {left: active.offsetLeft, width: active.offsetWidth});
  }, []);

  useLayoutEffect(measure, [measure, value, options]);
  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    const ro = new ResizeObserver(measure);
    ro.observe(track);
    for (const b of track.querySelectorAll('button')) ro.observe(b);
    window.addEventListener('resize', measure);
    void document.fonts?.ready.then(measure);
    return () => { ro.disconnect(); window.removeEventListener('resize', measure); };
  }, [measure, options]);

  // A tab activated while partly off the rail scrolls into view; not on mount, only after a pick.
  useEffect(() => {
    if (!userPicked.current) return;
    const active = trackRef.current?.querySelector<HTMLButtonElement>(CHECKED);
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    active?.scrollIntoView({inline: 'nearest', block: 'nearest', behavior: reduced ? 'auto' : 'smooth'});
  }, [value]);

  const pick = (i: number, focus = false) => {
    userPicked.current = true;
    const next = options[i].value;
    if (next !== value) onChange(next);
    if (focus) trackRef.current?.querySelectorAll<HTMLButtonElement>('[role="radio"], [role="tab"]')[i]?.focus();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = options.findIndex(o => o.value === value);
    let next: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (i + 1) % options.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (i - 1 + options.length) % options.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = options.length - 1;
    if (next === null) return;
    e.preventDefault();
    pick(next, true);
  };

  return (
    <div className={fill ? 'cv-tabs cv-tabs-fill' : 'cv-tabs'}>
      <div ref={trackRef} className="cv-tabs-track" role={role} aria-label={ariaLabelledby ? undefined : ariaLabel} aria-labelledby={ariaLabelledby} onKeyDown={onKeyDown}>
        {highlight ? <span className="cv-tabs-hl" aria-hidden style={{left: highlight.left, width: highlight.width}} /> : null}
        {options.map((o, i) => (
          <button key={o.value} type="button" role={role === 'tablist' ? 'tab' : 'radio'} aria-checked={role === 'radiogroup' ? o.value === value : undefined} aria-selected={role === 'tablist' ? o.value === value : undefined} tabIndex={o.value === value ? 0 : -1} data-value={o.value} className="cv-tab" onClick={() => pick(i)}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
