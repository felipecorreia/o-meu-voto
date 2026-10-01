// Build the plain-text and HTML copies of the assistant setup instructions (issue #115).
// Both keep the authored Markdown text unchanged. The HTML copy also turns every URL of the
// text into a link and lists ready GET links per UF and office, because some chat tools
// (ChatGPT) only open URLs that appear as links on a page they read, not URLs they build.
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const [source = 'public/prompt-llm.md', output = 'dist'] = process.argv.slice(2);
// Absolute, like the URLs of the text, so a copy served from another host (a Pages preview
// has no edge secrets) still sends assistants to the public API.
const SITE = 'https://omeuvoto.pages.dev';
const instructions = await readFile(source, 'utf8');

// Mirrors `UF` in src/br_elections_mcp/domain.py minus ZZ and BR (tests/test_assistant_resources.py).
const STATES = [
  'AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA',
  'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO',
];
const officesOf = (uf) => [
  ['governador', 'governador'],
  ['senador', 'senador'],
  ['deputado_federal', 'deputado federal'],
  uf === 'DF' ? ['deputado_distrital', 'deputado distrital'] : ['deputado_estadual', 'deputado estadual'],
];

const escapeHtml = (text) => text.replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[char]);
// Runs on escaped text: a URL stops at an escaped quote or bracket and drops trailing
// punctuation, so it never carries markup into the href.
const linkify = (escaped) => escaped.replace(
  /https?:\/\/(?:(?!&(?:quot|#39|lt|gt);)[^\s<>"'`()[\]])+/g,
  (match) => {
    // A template such as `/candidates/{sq_candidato}` stays text: a link to it would be a
    // URL some readers substitute for the one they were asked to build.
    if (match.includes('{')) return match;
    const url = match.replace(/[.,;:]+$/, '');
    return `<a href="${url}">${url}</a>${match.slice(url.length)}`;
  },
);
const listLink = (uf, office, label) =>
  `<a href="${SITE}/api/v1/candidates?uf=${uf}&amp;office=${office}">${label}</a>`;

const html = `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>O meu voto - instruções para assistentes</title>
<style>body{max-width:80ch;margin:2rem auto;padding:0 1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}</style>
</head>
<body>
<nav aria-label="Formatos e API">
<a href="${SITE}/prompt-llm.txt">Texto simples</a> ·
<a href="${SITE}/api/v1/openapi.json">Contrato da API REST</a>
</nav>
<main><pre>${linkify(escapeHtml(instructions))}</pre></main>
<section aria-labelledby="consultas">
<h2 id="consultas">Consultas prontas</h2>
<p>Links GET da API REST pública. Abra o da UF e do cargo que o eleitor pediu; sem
<code>round</code>, o servidor responde o turno vigente e informa qual é.</p>
<ul>
<li><a href="${SITE}/api/v1/election">Data, horário e turnos da eleição</a></li>
<li>Presidente: ${listLink('BR', 'presidente', 'candidaturas')}</li>
${STATES.map((uf) => `<li>${uf}: ${officesOf(uf).map(([office, label]) => listLink(uf, office, label)).join(' · ')}</li>`).join('\n')}
</ul>
</section>
</body>
</html>
`;
await mkdir(output, { recursive: true });
await Promise.all([
  writeFile(join(output, 'prompt-llm.txt'), instructions),
  writeFile(join(output, 'prompt-llm.html'), html),
]);
