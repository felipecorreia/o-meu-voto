import {Info, TriangleAlert} from 'lucide-react';
import type {ReactNode} from 'react';

export function NoticeBanner({tone, title, text, icon, role = 'note'}: {tone: 'wait' | 'info'; title?: string; text: string; icon?: ReactNode; role?: 'note' | 'status'}) {
  const Icon = tone === 'wait' ? TriangleAlert : Info;
  return <div className={`cv-notice cv-notice-${tone}`} role={role}>
    {icon ? <span className="cv-notice-icon" aria-hidden>{icon}</span> : <Icon size={20} aria-hidden />}
    <div>{title ? <span className="cv-notice-title">{title}</span> : null}<p>{text}</p></div>
  </div>;
}
