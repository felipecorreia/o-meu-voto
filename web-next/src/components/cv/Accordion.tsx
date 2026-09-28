import {ChevronDown} from 'lucide-react';
import type {ReactNode} from 'react';

/**
 * A card of collapsible questions under a heading (Tela 7 spec, 5.4). The `<section id>` is the
 * anchor a ChipNav scrolls to, and the H2 (`<id>-title`) takes script focus (tabIndex -1) so the
 * chip can hand focus over. The items are `AccordionItem`s; several may be open at once.
 */
export function AccordionGroup({id, title, children}: {id: string; title: string; children: ReactNode}) {
  const titleId = `${id}-title`;
  return <section id={id} className="cv-accordion-group" aria-labelledby={titleId}>
    <h2 id={titleId} tabIndex={-1}>{title}</h2>
    <div className="cv-accordion">{children}</div>
  </section>;
}

/**
 * One question of the card, the WAI-ARIA accordion pattern: a button inside a heading with
 * `aria-expanded` and `aria-controls`, and a region labelled by that button. The button is
 * `b-<id>`, the wrapper `q-<id>` (the scroll and highlight target) and the answer `r-<id>`. Open
 * state is the parent's, so opening one item never closes another. Enter and Space toggle
 * through the native button.
 */
export function AccordionItem({id, question, open, onToggle, children}: {id: string; question: string; open: boolean; onToggle: () => void; children: ReactNode}) {
  const buttonId = `b-${id}`;
  const panelId = `r-${id}`;
  return <div id={`q-${id}`} className="cv-accordion-item">
    <h3>
      <button id={buttonId} type="button" aria-expanded={open} aria-controls={panelId} onClick={onToggle}>
        <span className="cv-accordion-q">{question}</span>
        <span className="cv-accordion-chevron" aria-hidden><ChevronDown size={16} strokeWidth={2.4} /></span>
      </button>
    </h3>
    {open ? <div id={panelId} role="region" aria-labelledby={buttonId} className="cv-accordion-panel">{children}</div> : null}
  </div>;
}
