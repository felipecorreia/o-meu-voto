import type {ReactNode} from 'react';
import {Badge} from '@astryxdesign/core/Badge';
import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {Link} from '@astryxdesign/core/Link';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';
import {Spinner} from '@astryxdesign/core/Spinner';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {SearchX} from 'lucide-react';
import type {ElectionInfo, NotFound, Source} from '../api';
import {fmtStamp} from '../format';

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

/** `onRetry` adds a "Tentar de novo" button (the choice mode of the Comparar page, spec 5.11). */
export function ErrorState({message, title = 'Não foi possível consultar', onRetry}: {message: string; title?: string; onRetry?: () => void}) {
  return (
    <Banner status="error" title={title} description={message} container="card" elevation="none" collapsible={false}
      endContent={onRetry ? <Button size="sm" variant="secondary" label="Tentar de novo" onClick={onRetry} /> : undefined} />
  );
}

export function Loading({label = 'Consultando os dados abertos do TSE…'}: {label?: string}) {
  return <div className="loading"><Spinner size="md" label={label} /></div>;
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
