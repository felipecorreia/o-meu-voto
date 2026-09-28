import {useCallback, useEffect, useRef, useState, type CSSProperties} from 'react';
import {ChevronRight, Pencil} from 'lucide-react';
import {useTopNavOffset} from '../components/Comparison';
import {AccordionGroup, AccordionItem} from '../components/cv/Accordion';
import {ChipNav} from '../components/cv/ChipNav';
import {CopyLinkButton} from '../components/cv/CopyLinkButton';
import {NoticeBanner} from '../components/cv/NoticeBanner';
import {TermList} from '../components/cv/TermList';
import {FAQ, FAQ_DRAFT, type FaqGroup} from '../content/faq';
import {scrollToId} from '../lib/scroll';
import {useMedia} from '../lib/useMedia';
import {href} from '../router';
import {cvTokens} from '../themes/cde';

/** Dúvidas (Tela 7): fixed content from `content/faq.ts`, no API. `open` is the route's `?abrir=<id>`. */
export function FaqPage({open}: {open?: string | null}) {
  return <FaqScreen open={open} draft={FAQ_DRAFT} groups={FAQ} />;
}

/** A group the person chose (a chip, or the group of the `?abrir=` item) that keeps the desktop
 *  mark: `seen` once it entered the viewport, `whole` once it was entirely in it. */
type Pin = {id: string; seen: boolean; whole: boolean};

/** The screen for a given content and deep link, so every state renders without the route or the flag. */
export function FaqScreen({open, draft, groups}: {open?: string | null; draft: boolean; groups: FaqGroup[]}) {
  const topNav = useTopNavOffset();
  const desktop = useMedia('(min-width: 1024px)');
  const known = groups.some(g => g.items.some(item => item.id === open)) ? open! : null;
  const [openIds, setOpenIds] = useState<ReadonlySet<string>>(() => new Set(known ? [known] : []));
  const [active, setActive] = useState<string | undefined>(groups[0]?.id);
  const pin = useRef<Pin | null>(null);
  const ratios = useRef(new Map<string, number>()); // per group: -1 above the line or off screen, 1 whole in the viewport
  const hold = useCallback((id: string) => {
    const r = ratios.current.get(id) ?? -1;
    pin.current = {id, seen: r >= 0, whole: r >= 1};
    setActive(id);
  }, []);

  // ?abrir=<id> (spec 5.5): open the item, then scroll to it after the router's scroll to the top
  // (two frames later), flash it and put focus on its button. An unknown id changes nothing.
  useEffect(() => {
    if (!known) return;
    setOpenIds(prev => prev.has(known) ? prev : new Set(prev).add(known));
    hold(groups.find(g => g.items.some(item => item.id === known))!.id);
    let second = 0;
    let endHighlight = () => {};
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => {
        endHighlight = scrollToId(`q-${known}`, {highlight: true});
        document.getElementById(`b-${known}`)?.focus({preventScroll: true});
      });
    });
    return () => { cancelAnimationFrame(first); cancelAnimationFrame(second); endHighlight(); };
  }, [known, groups, hold]);

  // Desktop (spec 5.8): an IntersectionObserver whose root starts 2 px above the reading line
  // (the sticky top plus 12 px, where scrollToId puts a group) marks the chip of the group under
  // that line: the first group in order still crossing it. A pinned group (a chip, or the group
  // of the ?abrir= item) keeps the mark on a page too short to scroll it up to the line, until it
  // scrolls out of the viewport, or out of full view once it was whole in it. Below a pin, the last
  // group takes the mark once it is whole in the viewport or the page is scrolled to its end.
  useEffect(() => {
    if (!desktop || !groups.length) return;
    const byGroup = ratios.current;
    byGroup.clear();
    const observer = new IntersectionObserver(entries => {
      for (const e of entries) byGroup.set(e.target.id, e.isIntersecting ? e.intersectionRatio : -1);
      const p = pin.current;
      const r = p ? byGroup.get(p.id) : undefined;
      if (p && r !== undefined) {
        if (r >= 0) p.seen = true;
        if (r >= 1) p.whole = true;
        if (p.seen && (r < 0 || (p.whole && r < 1))) pin.current = null;
      }
      const last = groups[groups.length - 1].id;
      const page = document.scrollingElement;
      const scrolled = !!page && page.scrollTop > 0;
      const atEnd = scrolled && page.scrollTop + page.clientHeight >= page.scrollHeight - 1;
      const lastWins = atEnd || (scrolled && (byGroup.get(last) ?? -1) >= 1);
      setActive(pin.current?.id ?? (lastWins ? last : undefined) ?? groups.find(g => (byGroup.get(g.id) ?? -1) >= 0)?.id ?? groups[0].id);
    }, {rootMargin: `-${topNav + 10}px 0px 0px 0px`, threshold: [0, 1]});
    for (const g of groups) { const el = document.getElementById(g.id); if (el) observer.observe(el); }
    return () => observer.disconnect();
  }, [desktop, topNav, groups]);

  const selectGroup = useCallback((id: string) => {
    scrollToId(id);
    document.getElementById(`${id}-title`)?.focus({preventScroll: true});
    hold(id);
  }, [hold]);
  const toggle = (id: string) => setOpenIds(prev => { const next = new Set(prev); if (!next.delete(id)) next.add(id); return next; });

  return <div className="page cv-page faq" style={{...cvTokens, '--cv-topnav': `${topNav}px`} as CSSProperties}>
    <header className="faq-head"><h1>Dúvidas <span>frequentes</span></h1><p>Respostas curtas sobre a comparação, os dados e o dia da votação.</p></header>
    <div className="faq-layout">
      {draft ? <NoticeBanner tone="wait" title="Texto em rascunho" text="Redação provisória, ainda em revisão." icon={<Pencil size={20} />} /> : null}
      <ChipNav items={groups.map(g => ({id: g.id, label: g.short}))} activeId={desktop ? active : null} onSelect={selectGroup} />
      <div className="faq-groups">
        {groups.map(g => <AccordionGroup key={g.id} id={g.id} title={g.title}>
          {g.items.map(item => <AccordionItem key={item.id} id={item.id} question={item.q} open={openIds.has(item.id)} onToggle={() => toggle(item.id)}>
            {item.a.map((text, i) => <p key={i}>{text}</p>)}
            {item.terms ? <TermList terms={item.terms} /> : null}
            <div className="cv-accordion-actions">
              {item.link ? <a href={item.link.href}>{item.link.label}<ChevronRight size={16} strokeWidth={2.2} aria-hidden /></a> : null}
              <CopyLinkButton hash={href('/duvidas', {abrir: item.id})} />
            </div>
          </AccordionItem>)}
        </AccordionGroup>)}
      </div>
    </div>
  </div>;
}
