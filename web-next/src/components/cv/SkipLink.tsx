import type {MouseEvent} from 'react';

/**
 * "Pular para o conteúdo" (casca spec 6): the first focusable element of the page, off screen
 * until focused. The click is handled here because the router is hash-based: left to the
 * browser, `#conteudo` would be read as a route.
 */
export function SkipLink({targetId = 'conteudo'}: {targetId?: string}) {
  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    document.getElementById(targetId)?.focus();
  };
  return <a className="cv-skiplink" href={`#${targetId}`} onClick={onClick}>Pular para o conteúdo</a>;
}
