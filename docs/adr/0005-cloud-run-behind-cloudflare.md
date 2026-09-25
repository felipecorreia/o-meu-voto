# 0005. Cloud Run em southamerica-east1 atrás da Cloudflare, página no Pages, fotos no R2

Status: aceito, 2026-09-17. Emendado pelo ADR 0010 (2026-09-25): origem restrita por segredo
de borda, não por faixas de IP, e custo da instância mínima corrigido.

## Contexto

O serviço é um contêiner de leitura pura com picos previsíveis na véspera e no dia da
eleição. O free tier do Cloud Run cobre 2 milhões de requisições e 180.000 vCPU-segundos por
mês; 100 mil consultas de 50 ms cabem folgadamente (relatório do scout, §5.2). A região
southamerica-east1 dá latência menor ao eleitor no Brasil e mantém o download do TSE, se
precisar rodar como job, em IP brasileiro (§6, decisão 11). A página estática é o canal para
quem não tem MCP (§3.2). As fotos de candidato vêm em ZIPs por UF, de 2,3 MB (AC) a 15,6 MB
(SP), e a decisão de produto é espelhá-las e embuti-las nas respostas e na página, em vez de
linkar o DivulgaCandContas, que bloqueia clientes HTTP comuns (§1.2 b, §1.4).

## Decisão

O serviço roda no Cloud Run em southamerica-east1, com instância mínima zero, e só é
alcançável pela Cloudflare: o domínio público aponta para a Cloudflare, que faz cache curto
das respostas `GET` da REST, aplica o primeiro nível de limite por IP e proteção contra
abuso, e encaminha ao Cloud Run com a origem restrita a ela. A página estática vive no
Cloudflare Pages, no mesmo domínio, e consome `/api/v1`. As fotos são espelhadas pelo
pipeline num bucket R2 servido por domínio público, e a URL de cada foto vai no campo
`photo_url` da resposta. O índice DuckDB e o `manifest.json` ficam num bucket GCS na mesma
região do Cloud Run.

## Consequências

- Dois provedores para operar: GCP para o serviço e o índice, Cloudflare para borda, página e
  fotos. Infraestrutura como código em dois lugares.
- O IP do cliente é lido de `CF-Connecting-IP` apenas quando a requisição traz o segredo de
  borda válido (ADR 0010, que substituiu a checagem das faixas da Cloudflare); sem ele o
  cabeçalho é ignorado, porque é falsificável.
- Verificar antes do primeiro deploy que o proxy da Cloudflare não bufferiza as respostas em
  fluxo do transporte Streamable HTTP em `/mcp`; se bufferizar, `/mcp` sai do cache e do
  buffer explicitamente.
- Cold start de 1 a 3 segundos com instância mínima zero; se incomodar na semana da eleição,
  uma instância mínima de 1 vCPU e 1 GiB custa cerca de US$ 18,40 por mês, ou US$ 4,23 só na
  semana da eleição (preço de 2026-09-24, corrigido pelo ADR 0010; a estimativa original de
  US$ 6 a 7 estava desatualizada).
- Fotos sob custódia do projeto exigem o job de sincronização e remoção do ADR 0004.
