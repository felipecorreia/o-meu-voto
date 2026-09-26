import {describe, expect, it} from 'vitest';
import {isSlot, slotColor} from './slotColor';

describe('slotColor', () => {
  it('paints the slots blue, strong green, yellow with navy text and navy, in that order', () => {
    expect(slotColor(1)).toEqual({bg: 'var(--cv-blue)', fg: '#FFFFFF', tint: 'var(--cv-slot-1-tint)'});
    expect(slotColor(2)).toEqual({bg: 'var(--cv-green-strong)', fg: '#FFFFFF', tint: 'var(--cv-slot-2-tint)'});
    expect(slotColor(3)).toEqual({bg: 'var(--cv-yellow)', fg: 'var(--cv-navy)', tint: 'var(--cv-slot-3-tint)'});
    expect(slotColor(4)).toEqual({bg: 'var(--cv-navy)', fg: '#FFFFFF', tint: 'var(--cv-slot-4-tint)'});
  });
  it('only reads --cv-* tokens, never a colour of its own', () => {
    for (const i of [1, 2, 3, 4]) {
      const {bg, fg, tint} = slotColor(i);
      for (const v of [bg, fg, tint]) expect(v === '#FFFFFF' || /^var\(--cv-[a-z0-9-]+\)$/.test(v)).toBe(true);
    }
  });
  it('rejects a slot outside 1..4', () => {
    expect(isSlot(0)).toBe(false);
    expect(isSlot(5)).toBe(false);
    expect(isSlot(1.5)).toBe(false);
    expect(() => slotColor(0)).toThrow(RangeError);
    expect(() => slotColor(5)).toThrow(RangeError);
  });
});
