import type {ReactNode} from 'react';
import {ChevronRight} from 'lucide-react';

export function LinkCard({href, icon, title, caption}: {href: string; icon: ReactNode; title: string; caption: string}) {
  return <a className="cv-linkcard" href={href} target="_blank" rel="noopener">
    <span className="cv-linkcard-icon">{icon}</span>
    <span className="cv-linkcard-body"><span className="cv-linkcard-title">{title}</span><span className="cv-linkcard-caption">{caption}</span></span>
    <ChevronRight size={18} strokeWidth={2.2} aria-hidden />
  </a>;
}
