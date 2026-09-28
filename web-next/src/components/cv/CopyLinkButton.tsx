import {Link2} from 'lucide-react';
import {useEffect, useRef, useState} from 'react';

const COPIED_MS = 1800;

/** The URL `CopyLinkButton` copies for `hash`: this page's origin and path, without any query. */
export function deepLink(hash: string): string {
  return `${location.origin}${location.pathname}${hash}`;
}

/**
 * Copies a deep link of this page (`hash`, e.g. "#/duvidas?abrir=cpf") and reads "Link copiado"
 * for 1.8 s, announced through a polite live region. When the clipboard is not available the
 * address bar is pointed at the link instead (replaceState, which the hash router does not
 * react to) and a line below the button says so (Tela 7 spec, 5.6). Renders a fragment: the
 * parent's action row lays out the button and that line.
 */
export function CopyLinkButton({hash}: {hash: string}) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  const copy = async () => {
    clearTimeout(timer.current);
    try {
      await navigator.clipboard.writeText(deepLink(hash));
      setState('copied');
      timer.current = setTimeout(() => setState('idle'), COPIED_MS);
    } catch {
      history.replaceState(null, '', hash);
      setState('failed');
    }
  };

  return <>
    <button type="button" className="cv-copylink" onClick={() => void copy()}>
      <Link2 size={16} aria-hidden />
      {state === 'copied' ? 'Link copiado' : 'Copiar link'}
    </button>
    <span className="cv-sr-only" aria-live="polite">{state === 'copied' ? 'Link copiado.' : ''}</span>
    {state === 'failed' ? <p className="cv-copylink-failed">Não deu para copiar. O endereço da página já aponta para esta resposta.</p> : null}
  </>;
}
