import {useEffect, type ComponentPropsWithoutRef} from 'react';
import {markFloatingBar} from '../../lib/floatingBar';

/** Shared fixed container, including the safe area, from Tela 1's CompareTray. While mounted it
 *  marks `<html>` with `cv-has-floating-bar`, the shell footer's cue for bottom clearance. */
export function FloatingBar({className = '', ...props}: ComponentPropsWithoutRef<'div'>) {
  useEffect(() => markFloatingBar(document.documentElement), []);
  return <div className={`cv-floatingbar ${className}`.trim()} {...props} />;
}
