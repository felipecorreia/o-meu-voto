# 0001. Índice DuckDB embutido, somente leitura, em vez de Postgres ou Supabase

Status: aceito, 2026-09-17.

## Contexto

O serviço é leitura pura sobre um conjunto pequeno e estável: 517.179 seções e 20.984
candidatos, que sanitizados cabem num arquivo DuckDB de 44,3 MB com índices, respondendo a
consulta por (UF, zona, seção) em 0,6 ms e busca por nome com `ILIKE` em 0,3 ms (relatório do
scout, §5.2 e TL;DR 7). O dado muda por refresh do pipeline, nunca por escrita do usuário. A
stack preferida inclui Supabase, mas o plano Free pausa após uma semana sem uso e limita a
500 MB, e o Pro custa US$ 25 por mês sem ganho para leitura (§5.2). SQLite também serviria;
DuckDB lê CSV e Parquet nativamente no pipeline e agrega mais rápido.

## Decisão

O índice é um único arquivo DuckDB, construído pelo pipeline, publicado num bucket com
`manifest.json` e aberto pelo serviço em modo somente leitura. O serviço não tem banco de
dados servidor, conexão remota nem credencial de banco. O arquivo é o artefato versionado do
refresh: o bucket guarda as versões anteriores e o rollback é trocar o manifesto.

## Consequências

- Não existe porta de repositório no `core`: DuckDB é o único adaptador em produção e nos
  testes (em arquivo temporário, mesmo esquema), e um seam com um só adaptador seria só
  indireção.
- Quem baixa o arquivo é um adaptador da porta `IndexSource` (`GcsIndexSource`, em
  `index_store.py`), injetado no `core` por `app.py`; o `core` só conhece a porta e continua
  sem rede. Um segundo adaptador, `LocalDirectoryIndexSource`, serve os testes e o
  desenvolvimento local, o que justifica o seam.
- A checagem de versão nova fica fora do caminho da requisição: a única chamada síncrona ao
  `IndexSource` é a abertura inicial em `Core.start()`, chamado pelo lifespan de `app.py`;
  depois, uma tarefa de fundo de `index.py`, criada em `start()` e encerrada em `close()`,
  acorda com o sinal de cada consulta, ignora sinais até 60 segundos após a última
  verificação e, fora disso, consulta o `IndexSource` e troca o índice quando a verificação
  termina. Não há timer próprio: sem consultas, não há verificação, coerente com o Cloud Run
  alocar CPU só durante requisições. A consulta que sinaliza serve a versão aberta; nenhuma
  consulta espera por rede. Bucket fora ou
  manifesto inválido não derrubam o serviço: a versão aberta continua respondendo, o erro vai
  para o log, e `/healthz` expõe a versão aberta, a última verificação bem-sucedida e a última
  falha, além de alertar quando o índice passa de 24 horas sem build.
- Cold start de 1 a 3 segundos para o `GcsIndexSource` baixar o arquivo e o `core` abrir o
  banco; mitigações possíveis são empacotar o índice na imagem ou manter uma instância mínima
  (§5.2).
- Se o produto passar a precisar de escrita (favoritos, contas) ou de busca textual com
  acentos, Postgres ou Supabase entra como adição, não como substituição.
- Se o índice crescer com várias eleições ou resultados por seção, o arquivo passa de
  centenas de MB e o cold start piora: particionar por eleição antes disso.
