import {Check, Clock, X} from 'lucide-react';
import {sentenceCase} from '../../format';

export type StatusKind = 'ok' | 'bad' | 'wait' | 'neutral';

/** Exact DEFERIDO is accepted; appeals and unrecognised situations remain pending. */
export function statusKind(status: string): StatusKind {
  const s = status.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().trim();
  if (s === 'DEFERIDO') return 'ok';
  if (/INDEFERID|CASSAD|RENUNC|CANCELAD/.test(s)) return 'bad';
  return 'wait';
}

/** Only choice and profile use these status colours; comparison badges stay neutral. */
export function StatusBadge({status, kind = statusKind(status)}: {status: string; kind?: StatusKind}) {
  const Icon = kind === 'ok' ? Check : kind === 'bad' ? X : kind === 'wait' ? Clock : null;
  return <span className={`cv-status cv-status-${kind}`}>
    {Icon ? <Icon size={12} strokeWidth={3} aria-hidden /> : null}{sentenceCase(status)}
  </span>;
}
