import {Info, TriangleAlert} from 'lucide-react';

export function NoticeBanner({tone, title, text}: {tone: 'wait' | 'info'; title?: string; text: string}) {
  const Icon = tone === 'wait' ? TriangleAlert : Info;
  return <div className={`cv-notice cv-notice-${tone}`} role="note">
    <Icon size={20} aria-hidden />
    <div>{title ? <span className="cv-notice-title">{title}</span> : null}<p>{text}</p></div>
  </div>;
}
