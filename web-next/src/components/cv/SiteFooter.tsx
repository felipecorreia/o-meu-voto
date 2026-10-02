import {CircleHelp, CodeXml, Shield} from 'lucide-react';
import {AUTHOR_URL, REPO_URL} from '../../lib/links';
import {SITE_NAME} from '../../lib/routes';
import {BrandDots} from './BrandDots';

/**
 * The global footer (casca spec 5.5), after `<main>` on every screen: the one place that says
 * "projeto independente e não oficial", the licences line and the signature. "Código aberto"
 * appears only with a real `REPO_URL`. `html.cv-has-floating-bar` (lib/floatingBar.ts) adds the
 * clearance that keeps the last lines above a floating bar. The credit line links the author and,
 * with a `repoUrl`, the public repository.
 */
export function SiteFooter({repoUrl = REPO_URL}: {repoUrl?: string | null}) {
  return (
    <footer className="cv-sitefooter">
      <div className="cv-sitefooter-in">
        <div className="cv-sitefooter-card">
          <div className="cv-sitefooter-card-head">
            <span className="cv-sitefooter-shield" aria-hidden><Shield size={20} strokeWidth={2} /></span>
            <div>
              <span className="cv-sitefooter-title">Projeto independente e não oficial</span>
              <p>Feito com os dados abertos do TSE. Sem cadastro, sem CPF, sem título: nada é guardado.</p>
            </div>
          </div>
          <div className="cv-sitefooter-actions">
            <a className="cv-sitefooter-btn" href="#/duvidas"><CircleHelp size={16} strokeWidth={2} aria-hidden />Dúvidas</a>
            {repoUrl ? <a className="cv-sitefooter-btn" href={repoUrl} target="_blank" rel="noopener noreferrer"><CodeXml size={16} strokeWidth={2} aria-hidden />Código aberto</a> : null}
          </div>
        </div>
        <div className="cv-sitefooter-side">
          <p className="cv-sitefooter-licenses">Dados do TSE sob licença CC-BY. Este serviço não acessa o cadastro eleitoral. Código sob licença MIT.</p>
          <p className="cv-sitefooter-credit">
            Feito por <a href={AUTHOR_URL} target="_blank" rel="noopener noreferrer">Felipe Correia</a>
            {repoUrl ? <> · <a href={repoUrl} target="_blank" rel="noopener noreferrer">Código aberto no GitHub</a></> : null}
          </p>
          <div className="cv-sitefooter-sign"><BrandDots size={6} />{SITE_NAME} · Eleições 2026</div>
        </div>
      </div>
    </footer>
  );
}
