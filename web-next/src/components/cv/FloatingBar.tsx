import type {ComponentPropsWithoutRef} from 'react';

/** Shared fixed container, including the safe area, from Tela 1's CompareTray. */
export function FloatingBar({className = '', ...props}: ComponentPropsWithoutRef<'div'>) {
  return <div className={`cv-floatingbar ${className}`.trim()} {...props} />;
}
