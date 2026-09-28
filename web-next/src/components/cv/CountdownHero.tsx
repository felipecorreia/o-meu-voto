import {ArrowRight, CalendarDays, Check, Clock, ExternalLink} from 'lucide-react';
import {TSE_SITE_URL} from '../../lib/links';
import {href} from '../../router';
import {LinkCard} from './LinkCard';

export type CountdownVariant = 'count' | 'today' | 'closed' | 'after';

/** The hero of the Quando screen (Tela 6 spec, 5.2), one variant per phase: the countdown to a
 *  round, the voting day, the day's voting closed, and the election over. `hours` is the short
 *  voting hours ("8h às 17h") for `count` and `today`, the closing hour ("17h") for `closed`.
 *  The countdown is read as one sentence through the container's label; its three texts are
 *  hidden from the accessibility tree and nothing announces a recount (spec 6). */
export function CountdownHero({variant, days, roundLabel, dateLabel, hours, year}: {
  variant: CountdownVariant; days?: number; roundLabel: string; dateLabel: string; hours?: string | null; year?: string;
}) {
  if (variant === 'count') {
    const unit = days === 1 ? 'dia' : 'dias';
    return <section className="cv-countdown cv-countdown-count cv-voting-enter" aria-label={`${days} ${unit} para o ${roundLabel}, ${dateLabel}`}>
      <span className="cv-countdown-num" aria-hidden>{days}</span>
      <span className="cv-countdown-title" aria-hidden>{unit} para o {roundLabel}</span>
      <span className="cv-countdown-sub" aria-hidden>{hours ? `${dateLabel} · ${hours}` : dateLabel}</span>
    </section>;
  }
  if (variant === 'today') {
    return <section className="cv-countdown cv-countdown-today cv-voting-enter">
      <span className="cv-countdown-icon" aria-hidden><Check size={32} strokeWidth={2.4} /></span>
      <h2>Hoje é dia de votar</h2>
      <p>{hours ? `${roundLabel} · ${hours} (horário de Brasília)` : roundLabel}</p>
      <a className="cv-countdown-cta" href={href('/onde-voto')}>Ver onde eu voto<ArrowRight size={18} strokeWidth={2.2} aria-hidden /></a>
    </section>;
  }
  if (variant === 'closed') {
    return <section className="cv-countdown cv-countdown-closed cv-voting-enter">
      <span className="cv-countdown-icon" aria-hidden><Clock size={30} /></span>
      <h2>A votação de hoje terminou</h2>
      <p>As seções fecharam às {hours} (horário de Brasília).</p>
    </section>;
  }
  return <section className="cv-countdown cv-countdown-closed cv-voting-enter">
    <span className="cv-countdown-icon" aria-hidden><CalendarDays size={30} /></span>
    <h2>As votações de {year} terminaram</h2>
    <p>Os resultados oficiais são divulgados pelo TSE.</p>
    <LinkCard href={TSE_SITE_URL} icon={<ExternalLink size={20} />} title="Resultados no site do TSE" caption="Site oficial, abre em nova aba" />
  </section>;
}
