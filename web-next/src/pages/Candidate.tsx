import {useEffect, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {Link} from '@astryxdesign/core/Link';
import {MetadataList, MetadataListItem} from '@astryxdesign/core/MetadataList';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';
import {ArrowLeft, Columns3, ExternalLink as ExternalIcon} from 'lucide-react';
import {api, type CandidateData, type Envelope} from '../api';
import {NOMINATION, OFFICE, type Office} from '../labels';
import {href} from '../router';
import {CandidateAvatar, ErrorState, Loading, NotFoundState, NumberBadge, OnBallotBadge, SocialLinks, SourceFooter, StatusBadge, Warnings} from '../components/common';

export function CandidatePage({sq, backHref}: {sq: number; backHref: string}) {
  const [env, setEnv] = useState<Envelope<CandidateData> | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setEnv(null); setError(null);
    api.candidate(sq).then(e => { if (alive) setEnv(e); }).catch(e => { if (alive) setError(String(e.message ?? e)); });
    return () => { alive = false; };
  }, [sq]);

  if (error) return <div className="page"><ErrorState message={error} /></div>;
  if (!env) return <div className="page"><Loading /></div>;
  if (!env.data) return <div className="page">{env.not_found ? <NotFoundState nf={env.not_found} /> : null}<Warnings warnings={env.warnings} /></div>;
  const c = env.data.candidate;
  const office = OFFICE[c.office as Office] ?? c.office;
  return (
    <div className="page">
      <div className="bar"><Button variant="ghost" size="sm" label="Voltar" icon={<ArrowLeft size={16} aria-hidden />} href={backHref} /></div>
      <Warnings warnings={env.warnings} />
      <Card padding={4} elevation="none">
        <div className="profile-head">
          <CandidateAvatar c={c} size="xl" />
          <div className="profile-title">
            <div className="cmp-head-name"><h1 className="h1 h1-tight">{c.ballot_name}</h1><NumberBadge n={c.number} /></div>
            <Text as="p" color="secondary">{office}, {c.round}º turno · {c.party.acronym}</Text>
            <div className="chips chips-compact"><StatusBadge status={c.adjudication_status} /><OnBallotBadge onBallot={c.on_ballot} /></div>
          </div>
        </div>
        <MetadataList columns="multi" label={{position: 'top'}}>
          <MetadataListItem label="Nome civil">{c.name}{c.social_name ? ` (nome social: ${c.social_name})` : ''}</MetadataListItem>
          <MetadataListItem label="Partido">{c.party.number} · {c.party.acronym} · {c.party.name}</MetadataListItem>
          <MetadataListItem label="Concorre por">{NOMINATION[c.nomination_kind] ?? c.nomination_kind}{c.federation ? ` · ${c.federation.acronym}: ${c.federation.name}` : ''}{c.coalition ? ` · ${c.coalition.name}` : ''}</MetadataListItem>
          {(c.coalition?.composition || c.federation?.composition) ? <MetadataListItem label="Composição">{c.coalition?.composition || c.federation?.composition}</MetadataListItem> : null}
          <MetadataListItem label="Ocupação declarada"><span className="sentence">{c.occupation ?? '—'}</span></MetadataListItem>
          <MetadataListItem label="Destino dos votos">{c.vote_destination ?? 'Não informado pelo TSE'} · <Link href={href('/duvidas', {abrir: 'destino'})}>o que significa</Link></MetadataListItem>
          <MetadataListItem label="Chapa">{c.running_mates.length ? c.running_mates.map(m => `${m.ballot_name} (${m.party.acronym}, ${OFFICE[m.office as Office] ?? m.office})`).join('; ') : 'Não se aplica'}</MetadataListItem>
        </MetadataList>
        <div className="profile-section">
          <VStack gap={2}>
            <Text type="label" weight="semibold">Redes declaradas ao TSE</Text>
            <SocialLinks links={c.social_links} />
          </VStack>
        </div>
        <div className="actions">
          {c.divulgacandcontas_url ? <Button variant="secondary" label="Ficha oficial no DivulgaCandContas" icon={<ExternalIcon size={16} aria-hidden />} href={c.divulgacandcontas_url} target="_blank" rel="noopener noreferrer" /> : null}
          <Button variant="primary" label="Comparar com outras" icon={<Columns3 size={16} aria-hidden />} href={href('/', {uf: c.office === 'presidente' ? 'BR' : undefined, office: c.office, sq: c.sq_candidato})} />
        </div>
        <div className="profile-section">
        <Collapsible defaultIsOpen={false} trigger={<Text weight="medium">Dados declarados ao TSE (só nesta ficha)</Text>}>
          <Text as="p" size="sm" color="secondary">Como o TSE publica, sem inferência. Nunca entram em listas nem na comparação (ADR 0004).</Text>
          <MetadataList columns="multi" label={{position: 'top'}}>
            <MetadataListItem label="Gênero">{c.gender ?? '—'}</MetadataListItem>
            <MetadataListItem label="Cor/raça">{c.race_color ?? '—'}</MetadataListItem>
            <MetadataListItem label="Estado civil">{c.marital_status ?? '—'}</MetadataListItem>
            <MetadataListItem label="Escolaridade">{c.education ?? '—'}</MetadataListItem>
          </MetadataList>
        </Collapsible>
        </div>
      </Card>
      <SourceFooter source={env.source} election={env.election} />
    </div>
  );
}
