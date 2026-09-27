import {LoaderCircle} from 'lucide-react';

export function LoadingState({text = 'Consultando os dados abertos do TSE…'}: {text?: string}) {
  return <div className="cv-loading" role="status" aria-live="polite">
    <div className="cv-loading-skeleton" aria-hidden />
    <div className="cv-loading-caption"><LoaderCircle size={18} aria-hidden />{text}</div>
  </div>;
}
