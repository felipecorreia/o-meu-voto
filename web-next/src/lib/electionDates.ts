// The election calendar as the Quando screen reads it (Tela 6 spec, section 5.1) and the
// "Quando votar" card of Onde voto (exception 1 of that spec). Every day comparison and every
// formatted date uses the civil day in America/Sao_Paulo, never the device time zone: a voter
// in Manaus, Fernando de Noronha or abroad sees the same phase and countdown as Brasília.
import type {ElectionData} from '../api';

export const BRASILIA_TZ = 'America/Sao_Paulo';

export type ElectionPhase = 'before-1' | 'today-1' | 'closed-today-1' | 'before-2' | 'today-2' | 'closed-today-2' | 'after' | 'unknown';
export interface RoundDate { number: number; date: string | null }
export type VotingHours = Partial<Pick<ElectionData['voting_hours'], 'start' | 'end'>> | null | undefined;
export interface RoundTag { tag: string; highlighted: boolean }

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const HHMM = /^(\d{1,2}):(\d{2})/;
const DAY_MS = 86_400_000;

const dayFormat = new Intl.DateTimeFormat('en-CA', {timeZone: BRASILIA_TZ, year: 'numeric', month: '2-digit', day: '2-digit'});
const timeFormat = new Intl.DateTimeFormat('en-GB', {timeZone: BRASILIA_TZ, hour: '2-digit', minute: '2-digit', hourCycle: 'h23'});
const roundDateFormat = new Intl.DateTimeFormat('pt-BR', {timeZone: BRASILIA_TZ, day: 'numeric', month: 'long'});
const weekdayFormat = new Intl.DateTimeFormat('pt-BR', {timeZone: BRASILIA_TZ, weekday: 'long'});
const shortDateFormat = new Intl.DateTimeFormat('pt-BR', {timeZone: BRASILIA_TZ, day: '2-digit', month: '2-digit', year: 'numeric'});

/** A date-only calendar value anchored at Brasília noon, so formatting in that zone can never
 *  slide to the previous or next day (Brasília has had no daylight saving since 2019). */
const atBrasiliaNoon = (iso: string) => new Date(`${iso}T12:00:00-03:00`);
const utcMidnight = (day: string) => { const [y, m, d] = day.split('-').map(Number); return Date.UTC(y, m - 1, d); };

/** The value when it is a real "YYYY-MM-DD" day, else null: a null or malformed round date is
 *  "Data a confirmar" on the page and is ignored by the phase. */
export function calendarDay(value: string | null | undefined): string | null {
  return value && ISO_DAY.test(value) && !Number.isNaN(atBrasiliaNoon(value).getTime()) ? value : null;
}

/** The civil day of `now` in Brasília as "YYYY-MM-DD", which compares as text. */
export function brasiliaDay(now: Date): string { return dayFormat.format(now); }

function brasiliaMinutes(now: Date): number {
  const parts = timeFormat.formatToParts(now);
  const part = (type: string) => Number(parts.find(p => p.type === type)?.value ?? 0);
  return part('hour') * 60 + part('minute');
}

const minutesOf = (hhmm: string | null | undefined): number | null => {
  const m = hhmm ? HHMM.exec(hhmm) : null;
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
};

/** Which hero the page shows (spec 5.1), from the Brasília civil day of `now`. `closesAt` is the
 *  end of the service's voting hours ("17:00"); without it a voting day never reaches its
 *  closed variant. A round without a valid date is ignored; without the first round's date the
 *  phase is unknown. */
export function electionPhase(rounds: RoundDate[], now: Date = new Date(), closesAt?: string | null): ElectionPhase {
  const d1 = calendarDay(rounds.find(r => r.number === 1)?.date);
  const d2 = calendarDay(rounds.find(r => r.number === 2)?.date);
  if (!d1) return 'unknown';
  const today = brasiliaDay(now);
  const closing = minutesOf(closesAt);
  const closed = closing != null && brasiliaMinutes(now) >= closing;
  if (today < d1) return 'before-1';
  if (today === d1) return closed ? 'closed-today-1' : 'today-1';
  if (d2) {
    if (today < d2) return 'before-2';
    if (today === d2) return closed ? 'closed-today-2' : 'today-2';
  }
  return 'after';
}

/** Whole Brasília civil days from `now` to the round day, never below 1: the eve reads "1 dia".
 *  Recomputed by the page on `visibilitychange`, never on a timer. */
export function daysUntil(iso: string, now: Date = new Date()): number {
  const target = calendarDay(iso);
  if (!target) throw new RangeError(`daysUntil needs a YYYY-MM-DD day, got ${JSON.stringify(iso)}`);
  return Math.max(1, Math.round((utcMidnight(target) - utcMidnight(brasiliaDay(now))) / DAY_MS));
}

/** The tag under each round tile per phase (spec 5.4); the highlighted one is the next or the
 *  current round. In the unknown phase nothing is highlighted. */
export function roundTags(phase: ElectionPhase): {first: RoundTag; second: RoundTag} {
  switch (phase) {
    case 'before-1': return {first: {tag: 'Próximo', highlighted: true}, second: {tag: 'Só onde houver', highlighted: false}};
    case 'today-1': case 'closed-today-1': return {first: {tag: 'Hoje', highlighted: true}, second: {tag: 'Só onde houver', highlighted: false}};
    case 'before-2': return {first: {tag: 'Já aconteceu', highlighted: false}, second: {tag: 'Próximo · onde houver', highlighted: true}};
    case 'today-2': case 'closed-today-2': return {first: {tag: 'Já aconteceu', highlighted: false}, second: {tag: 'Hoje · onde houver', highlighted: true}};
    case 'after': return {first: {tag: 'Já aconteceu', highlighted: false}, second: {tag: 'Já aconteceu', highlighted: false}};
    case 'unknown': return {first: {tag: '', highlighted: false}, second: {tag: 'Só onde houver', highlighted: false}};
  }
}

/** "4 de outubro": day and month in pt-BR, without the year (the page's lead carries it). */
export function formatRoundDate(iso: string): string { return roundDateFormat.format(atBrasiliaNoon(iso)); }

/** "Domingo": the weekday in pt-BR with its first letter upper-cased, since everywhere the page
 *  shows it the weekday opens the line or the sentence. */
export function formatWeekday(iso: string): string {
  const weekday = weekdayFormat.format(atBrasiliaNoon(iso));
  return weekday.charAt(0).toLocaleUpperCase('pt-BR') + weekday.slice(1);
}

/** "17/09/2026" for the calendar source's verification day. */
export function formatShortDate(iso: string): string { return shortDateFormat.format(atBrasiliaNoon(iso)); }

/** "8h", "17h", "17h30" from a service time such as "08:00"; null when unusable. */
export function formatHour(hhmm: string | null | undefined): string | null {
  const m = hhmm ? HHMM.exec(hhmm) : null;
  return m ? `${Number(m[1])}h${m[2] === '00' ? '' : m[2]}` : null;
}

/** "8h às 17h" from the service's start and end; null without a usable pair, when the page
 *  drops the hours strip and the "· horário" of the hero (spec 5.6). */
export function formatVotingHours(hours: VotingHours): string | null {
  const start = formatHour(hours?.start);
  const end = formatHour(hours?.end);
  return start && end ? `${start} às ${end}` : null;
}
