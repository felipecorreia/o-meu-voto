// The four marking slots of the comparison (Tela 1 spec, section 4.1). A slot colour follows
// the ORDER in which a candidacy was marked, never the candidacy or the party (ADR 0008): the
// first marked is blue, the second strong green, the third yellow with navy text, the fourth
// navy. Every value is a `--cv-*` token from `themes/cde.ts`, so the hexes live in one place.

export type Slot = 1 | 2 | 3 | 4;

export interface SlotColor {
  /** Avatar background. */
  bg: string;
  /** Text on that background (initials). */
  fg: string;
  /** The light background of the slot, for the comparison screen (Tela 2). */
  tint: string;
}

const WHITE = '#FFFFFF';

const SLOTS: Record<Slot, SlotColor> = {
  1: {bg: 'var(--cv-blue)', fg: WHITE, tint: 'var(--cv-slot-1-tint)'},
  2: {bg: 'var(--cv-green-strong)', fg: WHITE, tint: 'var(--cv-slot-2-tint)'},
  3: {bg: 'var(--cv-yellow)', fg: 'var(--cv-navy)', tint: 'var(--cv-slot-3-tint)'},
  4: {bg: 'var(--cv-navy)', fg: WHITE, tint: 'var(--cv-slot-4-tint)'},
};

export function isSlot(i: number): i is Slot {
  return Number.isInteger(i) && i >= 1 && i <= 4;
}

/** The colours of slot `i` (1 to 4). Anything else is a programming error: the marked set is
 *  capped at four before a slot is ever painted. */
export function slotColor(i: number): SlotColor {
  if (!isSlot(i)) throw new RangeError(`slot must be 1..4, got ${i}`);
  return SLOTS[i];
}
