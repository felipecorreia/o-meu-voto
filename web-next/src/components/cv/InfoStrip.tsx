import type {ReactNode} from 'react';

/** A strip with an icon in a white circle, a title and a subtitle, without a link (Tela 6 spec,
 *  5.5): the voting hours today, any loose piece of information tomorrow. */
export function InfoStrip({icon, title, subtitle}: {icon: ReactNode; title: string; subtitle: string}) {
  return <div className="cv-infostrip">
    <span className="cv-infostrip-icon" aria-hidden>{icon}</span>
    <span className="cv-infostrip-body"><span className="cv-infostrip-title">{title}</span><span className="cv-infostrip-sub">{subtitle}</span></span>
  </div>;
}
