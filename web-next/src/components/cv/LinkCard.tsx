import type {ReactNode} from 'react';
import {ChevronRight} from 'lucide-react';

export function LinkCard({href, icon, title, caption, tone = 'default'}: {href: string; icon: ReactNode; title: string; caption: string; tone?: 'default' | 'accent'}) {
  return <a className={`cv-linkcard${tone === 'accent' ? ' cv-linkcard-accent' : ''}`} href={href} target={href.startsWith('#') ? undefined : '_blank'} rel={href.startsWith('#') ? undefined : 'noopener'}>
    <span className="cv-linkcard-icon" aria-hidden>{icon}</span>
    <span className="cv-linkcard-body"><span className="cv-linkcard-title">{title}</span><span className="cv-linkcard-caption">{caption}</span></span>
    <ChevronRight size={18} strokeWidth={2.2} aria-hidden />
  </a>;
}
