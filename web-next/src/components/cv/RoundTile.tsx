import {formatRoundDate, formatWeekday} from '../../lib/electionDates';
import {NumberPill} from './NumberPill';

/** One round of the "Turnos" list (Tela 6 spec, 5.4): the round pill, the date, the weekday and
 *  the phase tag; the highlighted tile is the next or the current round. It renders the `<li>`
 *  itself so its accessible name carries the tag ("1º turno, 4 de outubro, domingo, próximo",
 *  spec 6). Without a date it reads "Data a confirmar", with no weekday and no tag. */
export function RoundTile({roundNumber, date, tag, highlighted = false}: {roundNumber: number; date: string | null; tag: string; highlighted?: boolean}) {
  const round = `${roundNumber}º turno`;
  const dateLabel = date ? formatRoundDate(date) : null;
  const weekday = date ? formatWeekday(date) : null;
  const name = date && weekday
    ? [round, dateLabel, weekday.toLocaleLowerCase('pt-BR'), tag.toLocaleLowerCase('pt-BR')].filter(Boolean).join(', ')
    : `${round}, data a confirmar`;
  return <li className={`cv-roundtile${highlighted ? ' cv-roundtile-next' : ''}`} aria-label={name}>
    <NumberPill n={round} />
    {date ? <>
      <span className="cv-roundtile-date">{dateLabel}</span>
      <span className="cv-roundtile-weekday">{weekday}</span>
      {tag ? <span className="cv-roundtile-tag">{tag}</span> : null}
    </> : <span className="cv-roundtile-date cv-roundtile-tbc">Data a confirmar</span>}
  </li>;
}
