import {useEffect, useState, type CSSProperties} from 'react';
import {ArrowRight, AtSign, ChevronLeft, ChevronRight, ExternalLink, Link2, Share} from 'lucide-react';
import {api, type CandidateData, type CandidateProfile, type Envelope} from '../api';
import {normalizeSocialUrl, sentenceCase, socialNetwork} from '../format';
import {NOMINATION, OFFICE, ufName, type Office} from '../labels';
import {parseSqList} from '../lib/marking';
import {profileNavigation, profileShare, VOTE_DESTINATION_NOTES} from '../lib/profile';
import {toTitleCase} from '../lib/titleCase';
import {useMedia} from '../lib/useMedia';
import {href} from '../router';
import {cvTokens} from '../themes/cde';
import {Facebook, Instagram, Tiktok, XBrand, Youtube} from '../components/brandIcons';
import {SourceFooter, Warnings} from '../components/common';
import {useTopNavOffset} from '../components/Comparison';
import {DetailRow} from '../components/cv/DetailRow';
import {FloatingBar} from '../components/cv/FloatingBar';
import {IconButton} from '../components/cv/IconButton';
import {LinkCard} from '../components/cv/LinkCard';
import {PrivateDataPanel} from '../components/cv/PrivateDataPanel';
import {ProfileHero} from '../components/cv/ProfileHero';

const NET_ICON = {instagram: Instagram, facebook: Facebook, x: XBrand, youtube: Youtube, tiktok: Tiktok, kwai: Tiktok, threads: AtSign, site: Link2} as const;

function ProfileNetworks({links}: {links: string[]}) {
  const wide = useMedia('(min-width: 1024px)');
  const [open, setOpen] = useState(false);
  const limit = wide ? 8 : 4;
  const seen = new Set<string>();
  const items = links.flatMap(raw => {
    const item = normalizeSocialUrl(raw);
    const key = item.href ?? item.label;
    if (!key || seen.has(key)) return [];
    seen.add(key);
    return [{...item, key}];
  });
  const shown = open ? items : items.slice(0, limit);
  return <section className="profile-networks" aria-labelledby="profile-networks-title">
    <h2 id="profile-networks-title">Redes declaradas</h2>
    {items.length ? <div className="profile-socials">
      {shown.map(item => {
        if (!item.href) return <span key={item.key} className="profile-social-text">{item.label}</span>;
        const Icon = NET_ICON[socialNetwork(item.href)];
        return <a className="profile-social" key={item.key} href={item.href} target="_blank" rel="noopener"><Icon size={16} aria-hidden /><span>{item.label}</span></a>;
      })}
      {items.length > limit ? <button className="profile-social profile-social-more" type="button" aria-expanded={open} onClick={() => setOpen(v => !v)}>{open ? 'Mostrar menos' : `+${items.length - limit} redes`}</button> : null}
    </div> : <p className="profile-secondary">Nenhuma rede declarada</p>}
  </section>;
}

/** Both alliance types can be declared at once; preserve both and their compositions. */
function NominationDetails({c}: {c: CandidateProfile}) {
  const alliances = [
    ...(c.coalition ? [{kind: 'Coligação', ...c.coalition}] : []),
    ...(c.federation ? [{kind: 'Federação', ...c.federation}] : []),
  ];
  if (!alliances.length) return <><span className="profile-neutral-badge">{NOMINATION[c.nomination_kind]}</span><span>{c.party.name}</span></>;
  return <>{alliances.map(a => <div className="profile-alliance" key={a.kind}><span className="profile-neutral-badge">{a.kind}</span><span>{a.name}</span>{a.composition ? <span className="profile-secondary">{a.composition}</span> : null}</div>)}</>;
}

function ProfileDetails({c}: {c: CandidateProfile}) {
  const note = c.vote_destination ? VOTE_DESTINATION_NOTES[c.vote_destination] : null;
  const ticketLabel = c.running_mates.some(m => m.office.includes('suplente')) ? 'Chapa · suplentes, com o mesmo número' : c.running_mates.length ? 'Chapa · vice, com o mesmo número' : 'Chapa';
  return <section className="profile-details" aria-labelledby="profile-details-title">
    <h2 id="profile-details-title">Sobre a candidatura</h2>
    <DetailRow label="Nome civil" secondary={c.social_name ? `Nome social: ${c.social_name}` : undefined}>{c.name}</DetailRow>
    <DetailRow label="Partido" secondary={c.party.name}>{c.party.acronym} · {c.party.number}</DetailRow>
    <DetailRow label="Concorre por"><NominationDetails c={c} /></DetailRow>
    <DetailRow label={ticketLabel}>{c.running_mates.length ? c.running_mates.map(m => <div className="profile-mate" key={m.sq_candidato}><span>{toTitleCase(m.ballot_name)}</span><span className="profile-secondary">{m.party.acronym} · {(OFFICE[m.office as Office] ?? m.office).toLocaleLowerCase('pt-BR')}</span></div>) : 'Não se aplica'}</DetailRow>
    <DetailRow label="Ocupação declarada">{c.occupation ? sentenceCase(c.occupation) : 'Não informado pelo TSE'}</DetailRow>
    <DetailRow label="Destino dos votos">
      {c.vote_destination ? <span className="profile-neutral-badge">{c.vote_destination}</span> : <span>Não informado pelo TSE</span>}
      {note ? <p className="profile-destination-note">{note}</p> : null}
      <a className="profile-destination-link" href={href('/duvidas', {abrir: 'destino'})}>O que isso significa<ChevronRight size={16} strokeWidth={2.2} aria-hidden /></a>
    </DetailRow>
  </section>;
}

function ProfileSkeleton() {
  return <div className="profile-skeleton" role="status"><span className="sr-only">Carregando a ficha…</span>
    <div className="profile-skeleton-hero" aria-hidden><span className="profile-skeleton-avatar" />{[0, 1, 2].map(i => <span className="profile-skeleton-line" key={i} />)}</div>
    <div className="profile-skeleton-details" aria-hidden>{[0, 1, 2, 3].map(i => <span className="profile-skeleton-row" key={i} />)}</div>
  </div>;
}

export function CandidatePage({sq, backHref}: {sq: number; backHref: string}) {
  const [env, setEnv] = useState<Envelope<CandidateData> | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const topNav = useTopNavOffset();
  // From 1024 px the action lives in the hero (styles.css hides `.profile-floating`); the bar is
  // not mounted there, so it does not ask the shell footer for clearance it does not need.
  const wide = useMedia('(min-width: 1024px)');
  // The shell and router stay unchanged; the existing prop already carries the hash query.
  const params = new URLSearchParams(backHref.split('?')[1] ?? '');
  const cmp = parseSqList(params.get('cmp'));
  useEffect(() => {
    let alive = true;
    setEnv(null); setError(false);
    api.candidate(sq).then(e => { if (alive) setEnv(e); }).catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, [sq, attempt]);
  const c = env?.data?.candidate;
  useEffect(() => {
    if (!c) return;
    const previous = document.title;
    document.title = `${toTitleCase(c.ballot_name)} (${c.number}) · Compare o voto`;
    return () => { document.title = previous; };
  }, [c]);
  const nav = c ? profileNavigation(c, params) : null;
  const returnHref = nav?.backHref ?? (cmp.length ? href('/', {uf: params.get('uf'), office: params.get('office'), sq: cmp.join(','), pair: params.get('pair'), tab: params.get('tab')}) : href('/'));
  const name = c ? toTitleCase(c.ballot_name) : '';
  const office = c ? OFFICE[c.office as Office] ?? c.office : '';
  const share = c ? profileShare(c, name, office, nav?.uf, location.href) : null;
  const nativeShare = typeof navigator.share === 'function';
  const compareAction = nav ? <a className="profile-cta" href={nav.chooseHref}>Comparar com outras<ArrowRight size={18} strokeWidth={2.2} aria-hidden /></a> : null;
  return <div className="page cv-page profile" style={{...cvTokens, '--cv-topnav': `${topNav}px`} as CSSProperties}>
    <div className="comp-bar">
      <a className="comp-back" href={returnHref}><ChevronLeft size={18} strokeWidth={2.2} aria-hidden />{cmp.length ? 'Voltar à comparação' : 'Escolher candidaturas'}</a>
      {share ? nativeShare ? <IconButton label="Compartilhar ficha" icon={<Share size={19} aria-hidden />} onClick={() => { navigator.share(share).catch(() => { /* cancelled or refused */ }); }} /> : <IconButton label="Compartilhar ficha" icon={<Share size={19} aria-hidden />} href={`https://wa.me/?text=${encodeURIComponent(share.text)}`} /> : null}
    </div>
    {env?.warnings.length ? <div className="profile-warnings"><Warnings warnings={env.warnings} /></div> : null}
    {error ? <div className="profile-problem" role="alert"><h1>Não foi possível abrir esta ficha agora.</h1><p>Tente de novo em instantes.</p><button type="button" onClick={() => setAttempt(n => n + 1)}>Tentar de novo</button></div>
      : !env ? <ProfileSkeleton />
      : !c || !nav ? <div className="profile-problem" role="alert"><h1>Não encontramos esta candidatura</h1><p>O link pode estar incompleto ou a candidatura não está nos dados do TSE.</p><a href={href('/')}>Escolher candidaturas</a></div>
      : <>
        <div className="profile-layout">
          <ProfileHero candidate={c} slot={nav.slot} office={office} place={nav.uf === 'BR' ? 'Brasil' : nav.uf ? ufName(nav.uf) : ''} action={compareAction} />
          <div className="profile-body" key={c.sq_candidato}>
            <ProfileDetails c={c} />
            <ProfileNetworks links={c.social_links} />
            {c.divulgacandcontas_url ? <LinkCard href={c.divulgacandcontas_url} icon={<ExternalLink size={20} aria-hidden />} title="Ficha oficial no DivulgaCandContas" caption="Site do TSE, abre em nova aba" /> : null}
            <PrivateDataPanel candidate={c} />
            <footer className="profile-foot"><SourceFooter source={env.source} election={env.election} /></footer>
          </div>
        </div>
        {!wide ? <FloatingBar className="profile-floating" role="region" aria-label="Comparar esta candidatura">
          <span className="cv-tray-text"><span className="cv-tray-title">{name} · {c.number}</span><span className="cv-tray-sub">{[office, nav.uf].filter(Boolean).join(' · ')}</span></span>
          {compareAction}
        </FloatingBar> : null}
      </>}
  </div>;
}
