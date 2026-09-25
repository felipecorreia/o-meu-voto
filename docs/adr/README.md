# Registros de decisão de arquitetura

Um arquivo por decisão que é difícil de reverter, surpreenderia um leitor sem contexto e
resultou de um trade-off real. Formato: contexto, decisão, consequências. Os números citados
vêm do relatório do scout de 2026-09-17 (investigação dos dados abertos do TSE, mantido fora
do repositório), com a seção indicada.

| ADR | Decisão |
|---|---|
| [0001](0001-embedded-duckdb-index.md) | Índice DuckDB embutido, somente leitura, em vez de Postgres ou Supabase |
| [0002](0002-mcp-streamable-http-official-sdk.md) | MCP por Streamable HTTP com o SDK oficial `mcp`, mais REST sobre o mesmo core |
| [0003](0003-curl-cffi-for-tse-downloads.md) | Download dos dados do TSE com `curl_cffi`, e o risco do Akamai |
| [0004](0004-lgpd-candidate-data-minimization.md) | Tratamento LGPD dos dados de candidato: minimização na ingestão |
| [0005](0005-cloud-run-behind-cloudflare.md) | Cloud Run em southamerica-east1 atrás da Cloudflare, página no Pages, fotos no R2 |
| [0006](0006-jev-restricted-to-static-page.md) | Jev restrito à caixa de linguagem natural da página estática |
| [0007](0007-product-recorte-mvp-then-comparator.md) | Product recorte: finish the MVP before round 1, candidate comparator as the first new scope |
| [0008](0008-candidate-comparator-v1-scope.md) | Candidate comparator v1: scope, content and neutrality rules (amends 0007) |
| [0009](0009-titulo-transient-join-key-and-asset-free-text.md) | The título as a transient join key for asset growth; asset free text dropped (amends 0004) |
