import {LoaderCircle, Plus} from 'lucide-react';

export function LoadMore({shown, total, loading, onMore, added = 0, hasMore = shown < total}: {
  shown: number; total: number; loading: boolean; onMore: () => void; added?: number; hasMore?: boolean;
}) {
  return <div className="cv-loadmore">
    <span>Mostrando {shown} de {total}</span>
    {hasMore ? <button type="button" disabled={loading} onClick={onMore}>
      {loading ? <LoaderCircle className="cv-loadmore-spin" size={18} aria-hidden /> : <Plus size={18} aria-hidden />}
      {loading ? 'Carregando…' : `Carregar mais ${Math.min(20, total - shown)}`}
    </button> : null}
    <span className="cv-sr-only" aria-live="polite">{added > 0 ? `Mais ${added} locais carregados.` : ''}</span>
  </div>;
}
