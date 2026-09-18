# 0003. Download dos dados do TSE com `curl_cffi`, e o risco do Akamai

Status: aceito, 2026-09-17.

## Contexto

Toda a infraestrutura web do TSE, incluindo o portal de dados abertos, a API CKAN e o CDN dos
ZIPs, devolve 403 (Akamai, "Access Denied") a `curl`, `requests` e Chrome headless, mesmo com
User-Agent e cabeçalhos de navegador. O bloqueio é por impressão digital TLS/HTTP2, não por
cookie ou desafio JavaScript: `curl_cffi` com `impersonate="chrome"` e um Chrome com janela
recebem 200 (relatório do scout, §1.0). Os dados são licenciados CC-BY e o portal oferece uma
API CKAN, o que indica configuração de WAF, não política de acesso. Os testes foram feitos de
um IP residencial brasileiro; se o Akamai também bloqueia IPs de datacenter (runners do GitHub
Actions nos EUA, Cloud Run) não foi verificado (Apêndice C).

## Decisão

O pipeline baixa os ZIPs com `curl_cffi` e impersonação de navegador, atrás de uma porta
`Downloader` com dois adaptadores (produção e arquivos locais para testes). Em paralelo,
abre-se contato com o TSE (`estatistica@tse.jus.br`, indicado no `leiame`, e a ouvidoria)
pedindo orientação ou liberação para reuso automatizado; a decisão é usar já e perguntar ao
mesmo tempo. O serviço nunca chama o TSE em tempo de requisição: só o pipeline baixa, uma vez
por refresh. O primeiro teste do pipeline é o acesso a partir de datacenter; se for bloqueado,
o plano B é um runner self-hosted ou um Cloud Run Job em southamerica-east1 fazendo o
download, e o pipeline para até isso ser decidido.

## Consequências

- Risco de manutenção: quando o Akamai mudar o que aceita, o refresh falha até `curl_cffi`
  acompanhar. Uma falha de download só envelhece o dado, que continua servido com aviso; não
  derruba o serviço.
- Risco reputacional: a impersonação é documentada abertamente no README e no pipeline, com
  volume mínimo (um download por arquivo por refresh) e o contato com o TSE registrado.
- `curl_cffi` é dependência só do grupo `pipeline` do `pyproject.toml`; a imagem do serviço
  não a carrega.
- A única superfície do TSE sem bloqueio, `resultados.tse.jus.br`, não é usada: apuração está
  fora do escopo por decisão.
