import {useState, type ReactNode} from 'react';
import {Avatar} from '@astryxdesign/core/Avatar';
import {Badge} from '@astryxdesign/core/Badge';
import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {Link} from '@astryxdesign/core/Link';
import {Text} from '@astryxdesign/core/Text';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import {Spinner} from '@astryxdesign/core/Spinner';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Link2, AtSign, SearchX, ShieldCheck, UserRound} from 'lucide-react';
import {Facebook, Instagram, Tiktok, XBrand, Youtube} from './brandIcons';
import type {CandidateListItem, ElectionInfo, NotFound, Source} from '../api';
import {fmtStamp, normalizeSocialUrl, socialNetwork} from '../format';
import {INDEPENDENT_NOTICE} from '../labels';
import {usePresentation, type StatusTone} from '../presentation';

export function CandidateAvatar({c, size = 'lg'}: {c: Pick<CandidateListItem, 'ballot_name' | 'photo_url'>; size?: 'sm' | 'md' | 'lg' | 'xl'}) {
  return <Avatar src={c.photo_url ?? undefined} name={c.ballot_name} size={size} shape="rounded" tooltip={false} />;
}

/** Candidate photo slot of the comparison header (captain, 2026-09-25 evening): the TSE 3:4
 *  portrait from `photo_url` when the index has it, otherwise a neutral placeholder of the same
 *  size, so every column keeps the same geometry. `photo_url` is null for every candidacy until
 *  the R2 mirror lands; the `photos=demo` review switch shows a sample labelled as such. */
export function CandidatePhoto({c}: {c: Pick<CandidateListItem, 'ballot_name' | 'photo_url'>}) {
  const {photoDemo} = usePresentation();
  // A photo_url that fails to load (mirror gap, network) falls back to the same placeholder.
  const [failed, setFailed] = useState(false);
  const demo = !c.photo_url && photoDemo;
  const src = failed ? null : c.photo_url ?? (demo ? `${import.meta.env.BASE_URL}photo-sample.svg` : null);
  if (!src) return <span className="pair-photo pair-photo-empty" aria-hidden="true"><UserRound size={22} aria-hidden /></span>;
  return <span className="pair-photo"><img src={src} alt={demo ? 'Exemplo de foto, não é a candidatura' : `Foto de ${c.ballot_name}`} loading="lazy" width={60} height={80} onError={() => setFailed(true)} /></span>;
}

/** Registration status verbatim from the TSE. `tone="neutral"` (review switch, `?status=neutral`)
 *  drops the green/red reading so the badge states a fact instead of a verdict. */
export function StatusBadge({status, tone}: {status: string; tone?: StatusTone}) {
  const presentation = usePresentation();
  const t = tone ?? presentation.statusTone;
  const s = status.toUpperCase();
  const colored = s === 'DEFERIDO' ? 'success' : s.includes('INDEFERIDO') || s.includes('CASSADO') || s.includes('RENÚNCIA') ? 'error' : s.includes('PENDENTE') ? 'warning' : 'neutral';
  const variant = t === 'neutral' ? 'neutral' : colored;
  return <span className="status-badge"><Badge variant={variant} label={<span className="sentence">{status}</span>} /></span>;
}

export function OnBallotBadge({onBallot, tone}: {onBallot: boolean; tone?: StatusTone}) {
  const presentation = usePresentation();
  const t = tone ?? presentation.statusTone;
  if (t === 'neutral') return <Badge variant="neutral" label={onBallot ? 'Na urna' : 'Fora da urna'} />;
  return onBallot ? <Badge variant="info" label="Na urna" /> : <Badge variant="error" label="Fora da urna" />;
}

export function NumberBadge({n}: {n: number}) {
  return <span className="num-badge" aria-label={`número ${n}`}>{n}</span>;
}

const NET_ICON = {instagram: Instagram, facebook: Facebook, x: XBrand, youtube: Youtube, tiktok: Tiktok, kwai: Tiktok, threads: AtSign, site: Link2} as const;

const SOCIAL_PREVIEW = 6;

export function SocialLinks({links, compact = false}: {links: string[]; compact?: boolean}) {
  const [open, setOpen] = useState(false);
  if (!links.length) return <Text color="secondary">Nenhuma rede declarada</Text>;
  // Normalise once, drop exact duplicates the TSE file carries, keep the TSE order.
  const items: Array<{key: string; href: string | null; label: string}> = [];
  const seen = new Set<string>();
  for (const raw of links) {
    const n = normalizeSocialUrl(raw);
    const key = n.href ?? n.label;
    if (!key || seen.has(key)) continue;
    seen.add(key); items.push({key, ...n});
  }
  const shown = open ? items : items.slice(0, SOCIAL_PREVIEW);
  const hidden = items.length - shown.length;
  return (
    <div className={compact ? 'chips chips-compact' : 'chips'}>
      {shown.map(it => {
        if (!it.href) return <Text key={it.key} color="secondary" size="sm">{it.label}</Text>;
        const Ic = NET_ICON[socialNetwork(it.href)];
        return <Button key={it.key} size="sm" variant="secondary" label={it.label} icon={<Ic size={14} aria-hidden />} href={it.href} target="_blank" rel="noopener noreferrer" />;
      })}
      {hidden > 0 ? <Button size="sm" variant="ghost" label={`+${hidden} ${hidden === 1 ? 'rede' : 'redes'}`} onClick={() => setOpen(true)} /> : null}
      {open && items.length > SOCIAL_PREVIEW ? <Button size="sm" variant="ghost" label="Mostrar menos" onClick={() => setOpen(false)} /> : null}
    </div>
  );
}

export function SourceFooter({source, election}: {source: Source; election?: ElectionInfo | null}) {
  return (
    <div className="source">
      <Text size="sm" color="secondary" as="p">
        {source.attribution} ({source.license}){source.dataset ? `, ${source.dataset}` : ''}
        {source.generated_at ? ` · gerado pelo TSE em ${fmtStamp(source.generated_at)}` : ''}
        {source.verified_at ? ` · calendário verificado em ${source.verified_at}` : ''}
        {election ? ` · ${election.name}, ${election.round.number}º turno` : ''}
      </Text>
      {source.stale ? <Badge variant="warning" label="Dados com mais de 48 h" /> : null}
    </div>
  );
}

export function Warnings({warnings}: {warnings: string[]}) {
  if (!warnings.length) return null;
  return (
    <VStack gap={2}>
      {warnings.map((w, i) => <Banner key={i} status="warning" title={w} container="card" elevation="none" collapsible={false} />)}
    </VStack>
  );
}

export function NotFoundState({nf}: {nf: NotFound}) {
  return <EmptyState isCompact icon={<SearchX size={40} aria-hidden />} title={nf.reason} description={nf.guidance} />;
}

export function ErrorState({message}: {message: string}) {
  return <Banner status="error" title="Não foi possível consultar" description={message} container="card" elevation="none" collapsible={false} />;
}

export function Loading({label = 'Consultando os dados abertos do TSE…'}: {label?: string}) {
  return <div className="loading"><Spinner size="md" label={label} /></div>;
}

export function IndependentNotice() {
  return (
    <HStack gap={1} align="center" className="notice">
      <ShieldCheck size={16} aria-hidden />
      <Text size="sm" color="secondary">{INDEPENDENT_NOTICE} Sem cadastro, sem CPF, sem título: nada é guardado.</Text>
    </HStack>
  );
}

export function PageHeader({title, lead, children}: {title: string; lead?: ReactNode; children?: ReactNode}) {
  return (
    <header className="page-head">
      <h1 className="h1">{title}</h1>
      {lead ? <p className="lead">{lead}</p> : null}
      {children}
    </header>
  );
}

export function ExternalLink({href, children}: {href: string; children: ReactNode}) {
  return <Link href={href} isExternalLink target="_blank" rel="noopener noreferrer">{children}</Link>;
}
