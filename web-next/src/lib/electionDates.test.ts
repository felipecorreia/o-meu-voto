import {afterEach, describe, expect, it, vi} from 'vitest';
import {brasiliaDay, calendarDay, daysUntil, electionPhase, formatHour, formatRoundDate, formatShortDate, formatVotingHours, formatWeekday, roundTags} from './electionDates';

const rounds = [{number: 1, date: '2026-10-04'}, {number: 2, date: '2026-10-25'}];
const CLOSES = '17:00';
// Brasília is UTC-3 the whole year, so "-03:00" instants are Brasília wall-clock times.
const at = (iso: string) => new Date(iso);
const originalTz = process.env.TZ;

afterEach(() => { vi.useRealTimers(); process.env.TZ = originalTz; });

describe('electionPhase and daysUntil on the Brasília civil day (criteria 1 to 5)', () => {
  it('counts 6 days to the first round on 28/09 with the default clock', () => {
    vi.useFakeTimers();
    vi.setSystemTime(at('2026-09-28T10:00:00-03:00'));
    expect(electionPhase(rounds, undefined, CLOSES)).toBe('before-1');
    expect(daysUntil('2026-10-04')).toBe(6);
    expect(roundTags('before-1')).toEqual({first: {tag: 'Próximo', highlighted: true}, second: {tag: 'Só onde houver', highlighted: false}});
  });
  it('reads 1 day on the eve, even minutes before midnight', () => {
    expect(daysUntil('2026-10-04', at('2026-10-03T08:00:00-03:00'))).toBe(1);
    expect(daysUntil('2026-10-04', at('2026-10-03T23:59:00-03:00'))).toBe(1);
    expect(electionPhase(rounds, at('2026-10-03T23:59:00-03:00'), CLOSES)).toBe('before-1');
  });
  it('is the voting day until the service closing time, closed from then on', () => {
    expect(electionPhase(rounds, at('2026-10-04T10:00:00-03:00'), CLOSES)).toBe('today-1');
    expect(electionPhase(rounds, at('2026-10-04T16:59:00-03:00'), CLOSES)).toBe('today-1');
    expect(electionPhase(rounds, at('2026-10-04T17:00:00-03:00'), CLOSES)).toBe('closed-today-1');
    expect(electionPhase(rounds, at('2026-10-04T17:30:00-03:00'), CLOSES)).toBe('closed-today-1');
    expect(roundTags('closed-today-1').first).toEqual({tag: 'Hoje', highlighted: true});
    // Without voting hours the day ends at midnight and the closed variant never shows.
    expect(electionPhase(rounds, at('2026-10-04T23:30:00-03:00'), null)).toBe('today-1');
    expect(electionPhase(rounds, at('2026-10-04T23:30:00-03:00'))).toBe('today-1');
  });
  it('counts down to the second round between the rounds', () => {
    const now = at('2026-10-10T12:00:00-03:00');
    expect(electionPhase(rounds, now, CLOSES)).toBe('before-2');
    expect(daysUntil('2026-10-25', now)).toBe(15);
    expect(roundTags('before-2')).toEqual({first: {tag: 'Já aconteceu', highlighted: false}, second: {tag: 'Próximo · onde houver', highlighted: true}});
  });
  it('handles the second round day and the day after', () => {
    expect(electionPhase(rounds, at('2026-10-25T09:00:00-03:00'), CLOSES)).toBe('today-2');
    expect(roundTags('today-2').second).toEqual({tag: 'Hoje · onde houver', highlighted: true});
    expect(electionPhase(rounds, at('2026-10-25T17:00:00-03:00'), CLOSES)).toBe('closed-today-2');
    expect(electionPhase(rounds, at('2026-10-26T00:10:00-03:00'), CLOSES)).toBe('after');
    expect(roundTags('after')).toEqual({first: {tag: 'Já aconteceu', highlighted: false}, second: {tag: 'Já aconteceu', highlighted: false}});
  });
  it('ignores a round without a date and is unknown without the first one', () => {
    const only1 = [{number: 1, date: '2026-10-04'}, {number: 2, date: null}];
    expect(electionPhase(only1, at('2026-09-28T10:00:00-03:00'), CLOSES)).toBe('before-1');
    expect(electionPhase(only1, at('2026-10-10T10:00:00-03:00'), CLOSES)).toBe('after');
    expect(electionPhase([{number: 1, date: '2026-10-04'}], at('2026-10-10T10:00:00-03:00'), CLOSES)).toBe('after');
    expect(electionPhase([{number: 1, date: null}, {number: 2, date: '2026-10-25'}], at('2026-09-28T10:00:00-03:00'), CLOSES)).toBe('unknown');
    expect(electionPhase([{number: 1, date: 'a confirmar'}], at('2026-09-28T10:00:00-03:00'), CLOSES)).toBe('unknown');
    expect(electionPhase([], at('2026-09-28T10:00:00-03:00'), CLOSES)).toBe('unknown');
    expect(roundTags('unknown')).toEqual({first: {tag: '', highlighted: false}, second: {tag: 'Só onde houver', highlighted: false}});
    expect(() => daysUntil('a confirmar')).toThrow(RangeError);
  });
});

describe('the device time zone never changes the phase or the countdown (criterion 6)', () => {
  // 01:00 UTC on 04/10 is 22:00 on 03/10 in Brasília: the eve, whatever the device says.
  const eveInBrasilia = at('2026-10-04T01:00:00Z');
  // 20:30 UTC on 04/10 is 17:30 in Brasília (closed) and 16:30 in Manaus (still open there).
  const closedInBrasilia = at('2026-10-04T20:30:00Z');
  it.each([
    ['UTC', 4],
    ['America/Manaus', 3],
    ['Europe/Lisbon', 4],
    ['Asia/Tokyo', 4],
  ])('with the device in %s', (tz, localDayOfEve) => {
    process.env.TZ = tz;
    expect(eveInBrasilia.getDate()).toBe(localDayOfEve);
    expect(brasiliaDay(eveInBrasilia)).toBe('2026-10-03');
    expect(electionPhase(rounds, eveInBrasilia, CLOSES)).toBe('before-1');
    expect(daysUntil('2026-10-04', eveInBrasilia)).toBe(1);
    expect(electionPhase(rounds, closedInBrasilia, CLOSES)).toBe('closed-today-1');
    expect(formatWeekday('2026-10-04')).toBe('Domingo');
    expect(formatRoundDate('2026-10-04')).toBe('4 de outubro');
    expect(formatShortDate('2026-09-17')).toBe('17/09/2026');
  });
  it('with a fake clock in another zone the defaults read Brasília', () => {
    process.env.TZ = 'America/Manaus';
    vi.useFakeTimers();
    vi.setSystemTime(closedInBrasilia);
    expect(new Date().getHours()).toBe(16);
    expect(electionPhase(rounds, undefined, CLOSES)).toBe('closed-today-1');
    vi.setSystemTime(eveInBrasilia);
    expect(daysUntil('2026-10-04')).toBe(1);
  });
});

describe('formatting', () => {
  it('formats the voting hours short and the closing hour alone', () => {
    expect(formatVotingHours({start: '08:00', end: '17:00'})).toBe('8h às 17h');
    expect(formatVotingHours({start: '08:30', end: '17:00'})).toBe('8h30 às 17h');
    expect(formatHour('17:00')).toBe('17h');
    expect(formatHour('09:15')).toBe('9h15');
    expect(formatVotingHours(null)).toBeNull();
    expect(formatVotingHours(undefined)).toBeNull();
    expect(formatVotingHours({start: '08:00'})).toBeNull();
    expect(formatVotingHours({start: 'manhã', end: '17:00'})).toBeNull();
    expect(formatHour(null)).toBeNull();
  });
  it('accepts only real calendar days', () => {
    expect(calendarDay('2026-10-04')).toBe('2026-10-04');
    expect(calendarDay('2026-10-4')).toBeNull();
    expect(calendarDay('2026-10-04T00:00:00')).toBeNull();
    expect(calendarDay('invalid')).toBeNull();
    expect(calendarDay(null)).toBeNull();
    expect(calendarDay(undefined)).toBeNull();
  });
});
