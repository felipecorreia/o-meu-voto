import type {ReactNode} from 'react';

/** A grey, non-interactive 36 px chip for item lists such as the offices in dispute (Tela 6
 *  spec, 5.5): one `<li>` inside a `<ul class="cv-chips">`. */
export function CvChip({children}: {children: ReactNode}) {
  return <li className="cv-chip">{children}</li>;
}
