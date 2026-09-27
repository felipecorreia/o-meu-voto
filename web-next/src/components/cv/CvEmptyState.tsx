import type {ReactNode, Ref} from 'react';

export function CvEmptyState({icon, title, text, action, headingRef}: {
  icon: ReactNode; title: string; text: string; action?: ReactNode; headingRef?: Ref<HTMLHeadingElement>;
}) {
  return <section className="cv-empty" role="status">
    <span className="cv-empty-icon" aria-hidden>{icon}</span>
    <h1 ref={headingRef} tabIndex={-1}>{title}</h1>
    <p>{text}</p>
    {action ? <div className="cv-empty-action">{action}</div> : null}
  </section>;
}
