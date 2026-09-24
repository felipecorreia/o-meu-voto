# Desenho da base de código

Este documento fixa as fronteiras de módulo do br-elections-mcp antes de qualquer código de
serviço. Usa o vocabulário de módulos profundos: **módulo** (interface mais implementação),
**interface** (tudo que quem chama precisa saber: assinaturas, invariantes, erros, custo),
**implementação**, **seam** (o lugar onde a interface vive e onde o comportamento pode ser
trocado), **adaptador** (o que satisfaz uma interface num seam), **profundidade** (muito
comportamento atrás de pouca interface), **alavancagem** (o que quem chama ganha) e
**localidade** (o que quem mantém ganha). O modelo de domínio está em
[`domain-model.md`](domain-model.md); as decisões com trade-off real, em [`adr/`](adr/).

## 1. Princípio

Existe um único módulo profundo, o `core`: ele responde às seis perguntas sobre um índice
local, sem HTTP, sem rede e sem saber se quem pergunta é um LLM por MCP, um navegador pela
REST ou um teste. O índice chega ao `core` por uma porta, `IndexSource`, cujo adaptador de
rede vive fora dele. Tudo o mais é adaptador fino ou pipeline separado. O teste de deleção guia
cada fronteira: apagar um adaptador não pode fazer lógica de domínio reaparecer em outro
lugar; apagar o `core` faz toda a lógica reaparecer em cada adaptador, prova de que ele
merece existir.

## 2. Mapa de módulos

```
src/br_elections_mcp/
  domain.py            entidades e invariantes (já existe)
  elections.py         carregador e esquema de data/elections.yaml (já existe)
  index_schema.py      tabelas do índice e lista de colunas proibidas; compartilhado por core e pipeline
  core/                MÓDULO PROFUNDO: as seis consultas sobre o índice; sem HTTP, sem rede
    __init__.py        exporta Core, IndexSource e os tipos de resposta
    answers.py         modelos de resposta (pydantic): envelope, data, election, source
    index_source.py    porta IndexSource: "qual é a versão corrente do índice e onde está no disco"
    index.py           seam interno: abre o DuckDB somente leitura e troca o índice quando o IndexSource muda de versão
    calendar.py        seam interno: as eleições do YAML e "qual é a eleição corrente"
    normalize.py       acentos, zeros à esquerda, siglas de UF
    queries/           uma função por pergunta, SQL parametrizado
  index_store.py       adaptadores de IndexSource: LocalDirectoryIndexSource e GcsIndexSource (o único lugar do serviço que fala com o bucket)
  mcp_server.py        adaptador MCP (Streamable HTTP, SDK oficial mcp)
  api.py               adaptador REST (FastAPI sobre Starlette, que o SDK mcp já traz)
  telemetry.py         telemetria PostHog anônima (ticket #17): um evento por chamada, `Telemetry.call` envolve cada tool/rota
  app.py               raiz de composição: escolhe o IndexSource, monta /mcp, /api/v1, /healthz, limite por IP, telemetria
  pipeline/            SEPARADO DO SERVIÇO: fetch, build, validate, publish, mirror_photos
data/elections.yaml    calendário curado à mão
web/                   página estática (Cloudflare Pages) e a Pages Function que fala com o Jev
```

Dependências permitidas, e só estas:

```
mcp_server.py ──▶ core, telemetry ◀── api.py   (adaptadores só conhecem a interface do core e a de telemetry)
index_store.py ──▶ core (só a porta IndexSource)   (adaptadores do índice; GCS fica aqui)
app.py ──▶ mcp_server.py, api.py, index_store.py, telemetry.py   (composição; nunca lógica)
core ──▶ domain.py, elections.py, index_schema.py  (nunca index_store.py; nunca rede)
pipeline ──▶ domain.py, elections.py, index_schema.py     (nunca core; nunca os adaptadores)
web/ ──▶ REST (HTTP), Jev (HTTP, só a Pages Function)      (nunca importa Python)
```

O pipeline e o serviço se falam por um contrato de dados, não por importação: o arquivo do
índice mais `manifest.json`, entregues ao `core` por um `IndexSource`. O Jev nunca é
dependência do `core`, do serviço nem do `pyproject.toml` (ADR 0006).

## 3. `core`: o módulo profundo

### 3.1 Interface

Uma classe, `Core`, construída com um `IndexSource`, o caminho do `elections.yaml` e um
relógio (`Clock`, injetado para os testes de envelhecimento). O construtor não abre índice,
não chama o `IndexSource` e não inicia thread: `start()` faz a abertura inicial e cria a
tarefa de verificação, `close()` a encerra e fecha o índice, e os dois são chamados pelo
lifespan de `app.py`, nunca pelo construtor. Sete métodos de consulta, síncronos, puros em
relação a rede:

| Método | Pergunta | Retorno |
|---|---|---|
| `find_polling_place(uf, zone, section, round=None)` | onde voto | `PollingPlaceAnswer` |
| `search_polling_places(uf, municipality, neighborhood=None, query=None, near=None, limit=20, round=None)` | locais da cidade ou bairro | `PollingPlacesAnswer` |
| `list_candidates(uf, office, party=None, name=None, on_ballot_only=True, limit=50, offset=0, round=None)` | candidatos | `CandidatesAnswer` |
| `get_candidate(sq_candidato=None, *, uf=None, office=None, number=None, round=None)` | ficha do candidato | `CandidateAnswer` |
| `election_info(on=None)` | data e horário | `ElectionInfoAnswer` |
| `resolve_municipality(name, uf=None, limit=10)` | código do município | `MunicipalitiesAnswer` |
| `health()` | estado do índice | `IndexHealth` |
| `start()`, `close()` | ciclo de vida: abertura inicial e tarefa de verificação | nada |

Fatos que quem chama precisa saber, e que fazem parte da interface:

- **Todo `*Answer` tem `data`, `not_found`, `warnings`, `election` e `source`** (seção 8).
  "Não encontrado" é resultado, com orientação em PT-BR, não exceção.
- **Erros.** `InvalidQuery` (entrada fora do domínio: UF inexistente, `limit > 50`, cargo
  desconhecido) e `IndexUnavailable` (índice ausente ou corrompido). Nada mais escapa.
- **Normalização é do `core`.** "009" e 9 são a mesma zona; "Piracaia", "piracaia" e
  "PIRACAIA" são o mesmo município; `uf` aceita minúsculas. Os adaptadores não normalizam.
- **Limites.** `limit` máximo 50 em toda lista; `offset` só em `list_candidates`. Sem SQL
  livre em nenhuma entrada.
- **Custo.** Consulta por chave em menos de 1 ms e buscas por nome em menos de 10 ms sobre o
  índice de 44 MB (relatório do scout, §5.2); o `core` pode ser chamado por requisição sem
  cache.
- **Envelhecimento.** O `core` sempre responde com o índice que tem, carimba `source` e emite
  o aviso acima de 48 horas (seção 9). Nunca recusa por idade.
- **Turno.** `round` é opcional em toda consulta que depende do turno. Toda a resolução de
  turno (padrão, turno pedido ausente, avisos, `election`) está na tabela da seção 3.4, que é
  a única dona da regra; a identidade de Candidate é (`sq_candidato`, `round`). Uma consulta
  nunca devolve `not_found` nem lista vazia por causa do turno: `not_found` só quando a chave
  não existe em turno nenhum.
- **Recarga.** O `core` troca o índice sem reiniciar quando o `IndexSource` passa a ter uma
  versão nova, e a troca é atômica do ponto de vista de quem chama. A única chamada síncrona
  a `current()` é a abertura inicial, em `start()`. Depois disso há um único gatilho: cada
  consulta, ao terminar, sinaliza a tarefa de verificação de `index.py` (thread criada em
  `start()` e encerrada em `close()`), e a tarefa aplica o limite de 60 segundos: ignora o
  sinal se a última verificação terminou há menos de `INDEX_CHECK_INTERVAL_SECONDS = 60`,
  senão chama `refresh()`, que chama `current()`, compara a versão e troca o índice ao
  terminar. A tarefa não tem timer próprio: sem consultas, não há verificação, o que combina
  com o Cloud Run alocar CPU só durante requisições (ADR 0005). Nenhuma consulta espera por
  rede nem por download: a que sinaliza serve a versão aberta. Se `current()` falhar (bucket
  fora, manifesto inválido), a tarefa registra o erro, a versão aberta continua sendo
  servida, e `health()` expõe a versão aberta, o instante da última verificação bem-sucedida
  e a última falha (instante e mensagem), que `/healthz` repassa (seções 4 e 9). O `core`
  nunca sabe de onde o `IndexSource` trouxe o arquivo.

#### A porta `IndexSource`

`IndexSource` vive em `core/index_source.py` e tem um só método: `current()` devolve um
`IndexVersion` com o caminho local de `index.duckdb`, o conteúdo do `manifest.json` e o
identificador da versão (o SHA-256 do manifesto). O `core` compara o identificador com o que
tem aberto e só reabre quando ele muda. Contrato de `current()`, igual para todo adaptador:
pode ser lento e pode tocar a rede, por isso o `core` só o chama de forma síncrona em
`start()` e, depois, apenas de `refresh()` executado pela tarefa de fundo de `index.py`, no
máximo uma vez a cada 60 segundos, nunca dentro de uma consulta; levanta
`IndexSourceUnavailable` quando não consegue determinar a versão, e nunca devolve uma versão
pela metade. Dois adaptadores, em `index_store.py`, justificam o seam:

- `LocalDirectoryIndexSource(path)`: lê o índice e o manifesto de um diretório. Usado pelos
  testes, inclusive o de recarga (que substitui os arquivos no diretório e chama de novo), e
  por quem roda o serviço em desenvolvimento com um índice construído localmente.
- `GcsIndexSource(bucket, prefix, cache_dir)`: a cada chamada de `current()` baixa
  `manifest.json` do bucket, compara com o cache local e só baixa `index.duckdb` quando o
  manifesto mudou; grava com nome temporário e renomeia, para que o `core` nunca abra um
  arquivo pela metade. Bucket fora ou manifesto inválido viram `IndexSourceUnavailable`, e a
  versão em cache continua sendo a servida pelo `core`. É o único código do serviço que fala
  com o GCS, é ele quem paga o cold start do ADR 0001 (a única chamada síncrona), e depois
  disso só roda na tarefa de fundo, nunca no caminho de uma requisição.

`app.py` escolhe o adaptador por configuração e o injeta no `Core`. A porta é a garantia de
que "o `core` não tem rede" continua verificável por importação: `core/` não importa
`index_store.py` nem nenhum cliente HTTP.

### 3.2 Implementação e seams internos

- `index.py` pede ao `IndexSource` a versão corrente, abre o arquivo DuckDB em modo somente
  leitura e expõe uma conexão por thread. É dele a tarefa de fundo de verificação (criada em
  `Core.start()`, encerrada em `Core.close()`, acordada pelo sinal de cada consulta e limitada
  a uma execução por 60 segundos) e a função `refresh()` que ela executa (chamar `current()`,
  comparar a versão, abrir a nova e trocar atomicamente). `refresh()` é serializada por um
  lock: duas execuções nunca abrem o mesmo arquivo novo ao mesmo tempo. Os testes de consulta
  e o de recarga não chamam `start()`: constroem o `Core`, abrem o índice com `open_index()`
  (a mesma abertura inicial de `start()`, sem thread) e chamam `refresh()` diretamente; só o
  teste do ciclo de vida (3.3) chama `start()` e `close()`. Dependência de categoria
  "substituível localmente":
  os testes usam o mesmo DuckDB, construído a partir de fixtures CSV pequenas com os
  cabeçalhos reais do TSE, pela própria função de build do pipeline, e entregue por um
  `LocalDirectoryIndexSource`. Não há porta de repositório: um só motor de consulta significa
  um seam hipotético, e um seam hipotético é só indireção (ADR 0001). A porta que existe é a
  de origem do índice, não a de consulta.
- `calendar.py` encapsula "qual é a eleição corrente em uma data": a primeira do YAML cujo
  último turno ainda não passou. É a única lógica de calendário do sistema.
- `queries/` guarda o SQL parametrizado, uma função por pergunta, recebendo a conexão e
  devolvendo linhas tipadas. É seam interno, usado pelos testes do próprio `core`, não exposto.
- `answers.py` define os tipos de resposta em pydantic. Eles são a interface do `core` e, ao
  mesmo tempo, o esquema de saída dos dois adaptadores: o `outputSchema` das tools MCP e o
  OpenAPI da REST são gerados deles. Uma mudança de contrato acontece num único arquivo.

### 3.3 Testabilidade

A interface é a superfície de teste. Os testes do `core` constroem um índice mínimo num
diretório temporário (uma UF fictícia com seções principal e agregada, um local mudado, um
município no exterior, uma chapa de governador com vice, um candidato indeferido na urna,
seções nos turnos 1 e 2, um presidente com linhas nos dois turnos e um presidente eliminado
no 1º turno, com linha só no turno 1), o entregam por um `LocalDirectoryIndexSource` e
exercitam os sete métodos com asserções sobre o resultado, incluindo `source`, `election` e
`warnings`. Nenhum teste de consulta do `core` chama `start()`, então não há thread
verificando o diretório em paralelo; a única exceção é o teste do ciclo de vida, abaixo. O
teste de recarga troca os arquivos do diretório por um índice com
outro manifesto, verifica que a consulta seguinte ainda responde com a `source` antiga (a
troca só acontece em `refresh()`), chama `refresh()` de `index.py` e verifica que a próxima
consulta responde com a nova `source`, sem bucket, sem rede e sem thread. A tarefa de fundo
tem um teste próprio, de `start()` a `close()`, que sinaliza duas consultas seguidas com o
relógio injetado e afirma uma única execução de `refresh()` dentro de 60 segundos. Testes
de contrato garantem que nenhum campo da lista de colunas proibidas aparece em nenhuma
resposta nem no esquema do índice.

### 3.4 Resolução de turno

Esta seção é a única dona da regra de turno. Os contratos das tools (8.1 a 8.4) e a seção
3.1 apontam para cá e não a repetem. Vocabulário: **eleição corrente** é a definida por
`calendar.py` (a primeira do YAML cujo último turno ainda não passou); **próximo turno** é o
primeiro turno da eleição corrente cuja data ainda não passou; **turno publicado** é um turno
com ao menos uma linha no índice, de qualquer seção ou cargo; **eleição do índice** é a
gravada pelo pipeline no `manifest.json` (`election_year` e `election_dates` por turno), a
única entrada desta regra: o estágio publish (seção 5) a grava só quando todos os datasets do
índice são arquivos de eleição do mesmo ano, e nula sempre que qualquer dataset vier do
arquivo mensal `ATUAL`; **eleição corrente coincidente** é a eleição corrente quando a
eleição do índice não é nula e coincide com ela: mesmo ano (o YAML tem no máximo uma
eleição por ano, validação de carga de `elections.py`) e, para cada turno presente no
manifesto, data igual à do turno de mesmo número no YAML; um turno ainda não publicado não
conta contra (em 2026-09, com só o turno 1 no índice, `general-2026` coincide); **turno da
candidatura** é um turno em que a
própria candidatura tem linha, e o conjunto desses turnos é conhecido antes de aplicar a
tabela: por `sq_candidato`, são os turnos em que ele aparece; pelo trio (`uf`, `office`,
`number`), o `core` reúne primeiro as candidaturas `on_ballot` com esse trio em qualquer
turno (a unicidade do número entre `on_ballot` garante no máximo uma por turno), e o
conjunto de turnos delas é o turno da candidatura, vazio quando nenhuma está na urna; um
candidato só aparece nos turnos em que está na urna, e no 2º turno só quem o disputa;
**turno do cargo** é um turno em que (`uf`, `office`) tem alguma linha. O 1º e o 2º turno
são turnos distintos da mesma eleição, nunca outra eleição.

Regras comuns a todas as linhas da tabela: `round` fora de 1..n dos turnos do calendário (ou
fora de 1..2 sem eleição corrente coincidente) é `InvalidQuery`; o turno respondido vai em
`data.round` de toda consulta e em `election.round`; `election` é a eleição corrente
coincidente, com o turno respondido, e nula em qualquer outro caso, inclusive quando o
índice vem do arquivo mensal `ATUAL` (manifesto com eleição nula) ou de uma eleição já
encerrada enquanto o YAML já traz a próxima; a coluna "Eleição corrente coincidente" da
tabela usa exatamente esse critério, o mesmo que preenche `election`; o turno nunca produz
`not_found` nem lista vazia, e `not_found` só ocorre quando a chave não existe em turno
nenhum. Pelo trio, `not_found` com `candidato_nao_encontrado` quando o conjunto de turnos da
candidatura é vazio, mesmo que exista uma candidatura fora da urna com o número.

| # | Consulta | Eleição corrente coincidente | `round` pedido | Turno respondido | Aviso |
|---|---|---|---|---|---|
| T1 | locais e seções | sim | ausente, próximo turno publicado | próximo turno | nenhum |
| T2 | locais e seções | sim | ausente, próximo turno ainda não publicado | maior turno publicado | "O TSE ainda não publicou os locais do 2º turno; este é o local do 1º turno. Confira de novo perto da data." |
| T3 | locais e seções | sim | explícito e publicado | o pedido | nenhum |
| T4 | locais e seções | sim | explícito e ainda não publicado | maior turno publicado | o mesmo de T2 |
| T5 | locais e seções | não | ausente | maior turno publicado | nenhum |
| T6 | locais e seções | não | explícito e publicado | o pedido | nenhum |
| T7 | locais e seções | não | explícito e não publicado | maior turno publicado | "Não há dados do 2º turno; este é o local do 1º turno." |
| C1 | lista de candidatos | qualquer | ausente | maior turno do cargo | nenhum |
| C2 | lista de candidatos | qualquer | explícito e turno do cargo | o pedido | nenhum |
| C3 | lista de candidatos | qualquer | explícito, publicado, mas não turno do cargo | maior turno do cargo | "Deputado federal não tem 2º turno; esta é a lista do 1º turno." ou "Não há 2º turno para governador no AC; esta é a lista do 1º turno." |
| C4 | lista de candidatos | qualquer | explícito e ainda não publicado | maior turno do cargo | "O TSE ainda não publicou os candidatos do 2º turno; esta é a lista do 1º turno." |
| F1 | ficha de candidato | qualquer | ausente | maior turno da candidatura | nenhum |
| F2 | ficha de candidato | qualquer | explícito e turno da candidatura | o pedido | nenhum |
| F3 | ficha de candidato | qualquer | explícito, turno do cargo, mas não da candidatura | maior turno da candidatura | "Este candidato não disputa o 2º turno; esta é a ficha do 1º turno." |
| F4 | ficha de candidato | qualquer | explícito, publicado, mas não turno do cargo | maior turno da candidatura | o mesmo de C3 |
| F5 | ficha de candidato | qualquer | explícito e ainda não publicado | maior turno da candidatura | o mesmo de C4 |

Como distinguir "ainda não publicado" de "não tem 2º turno": o turno pedido é "ainda não
publicado" quando não há linha nenhuma dele no índice, de qualquer seção ou cargo; havendo
linhas dele para outros cargos ou seções, o turno está publicado e a ausência é do cargo ou
da candidatura. Exemplos, com o 2º turno já publicado pelo TSE: `list_candidates("SP",
"deputado_federal")` responde o turno 1 sem aviso (C1); `list_candidates("BR",
"presidente")` responde o turno 2 (C1); `list_candidates("AC", "governador", round=2)` numa
UF decidida no 1º turno responde o turno 1 com aviso (C3); `get_candidate(sq_candidato=X)`
de um presidente que ficou em 3º lugar responde a ficha do turno 1 sem aviso (F1), e com
`round=2` responde a mesma ficha com o aviso de F3; `get_candidate("BR", "presidente", 13)`
com o 13 eliminado segue F1 e F3 do mesmo jeito, porque o conjunto de turnos do trio é {1};
se o 13 tiver sido indeferido e substituído por outro 13 na urna, o trio resolve para o
substituto, e se nenhum 13 estiver na urna, `not_found`. Entre 2026-10-26 e a próxima
eleição do YAML não há eleição corrente, logo não há eleição corrente coincidente:
`find_polling_place` sem `round` responde o turno 2 com `election` nulo (T5). Em 2027-06, com
o YAML já trazendo `municipal-2028` e os locais vindo do arquivo mensal `ATUAL` (candidatos
ainda de 2026), a eleição do índice é nula pela regra da seção 5, então a coluna vale "não"
e o caso é T5, com `election` nulo; o mesmo vale se o índice ainda for o de 2026 com os dois
turnos, porque 2026 não coincide com 2028: T5 responde o turno 2, nunca T1.

## 4. Adaptadores `mcp_server.py` e `api.py`

Ambos são finos por construção: recebem a chamada, delegam ao `core`, serializam o
`*Answer`. Nenhum dos dois normaliza entrada, formata avisos, calcula envelhecimento ou toca
no DuckDB.

**MCP.** SDK oficial `mcp` (ADR 0002), transporte Streamable HTTP em `/mcp`, sem estado por
sessão. Uma tool por método do `core` (seção 8), com `title` e `description` em PT-BR,
`inputSchema` e `outputSchema` gerados dos modelos pydantic, `structuredContent` igual ao
envelope e um `content` de texto curto em PT-BR para clientes que ignoram o conteúdo
estruturado. Anotações: `readOnlyHint: true`, `idempotentHint: true`, `openWorldHint: false`.
`InvalidQuery` vira resultado com `isError`; `IndexUnavailable` vira erro de servidor.

**REST.** FastAPI, prefixo `/api/v1`, só `GET`, mesmo envelope em JSON, OpenAPI em
`/api/v1/openapi.json` para a página e para desenvolvedores. `InvalidQuery` vira 400 com a
mensagem do `core`; `IndexUnavailable` vira 503.

| Tool MCP | Rota REST |
|---|---|
| `find_polling_place` | `GET /api/v1/polling-place?uf=&zone=&section=&round=` |
| `search_polling_places` | `GET /api/v1/polling-places?uf=&municipality=&neighborhood=&query=&lat=&lon=&limit=&round=` |
| `list_candidates` | `GET /api/v1/candidates?uf=&office=&party=&name=&on_ballot_only=&limit=&offset=&round=` |
| `get_candidate` | `GET /api/v1/candidates/by-number?uf=&office=&number=&round=` e `GET /api/v1/candidates/{sq_candidato}?round=` |
| `election_info` | `GET /api/v1/election?on=` |
| `resolve_municipality` | `GET /api/v1/municipalities?name=&uf=&limit=` |
| (não é tool) | `GET /healthz` |

Ordem de declaração das rotas de candidato, que faz parte do contrato de `api.py`:
`GET /api/v1/candidates/by-number` é declarada antes de `GET /api/v1/candidates/{sq_candidato}`.
No FastAPI a primeira rota que casa vence, e a anotação de tipo não muda o casamento: um
`{sq_candidato}` anotado como `int` continua casando qualquer segmento, e a validação só roda
depois, devolvendo 422. O que evita a colisão é a ordem de declaração (ou, como alternativa
equivalente, o conversor de caminho do Starlette, `{sq_candidato:int}`, que restringe o
casamento a dígitos). A anotação `int` continua existindo, mas só para que um `sq_candidato`
não numérico produza uma mensagem de erro clara. O teste do adaptador REST cobre `by-number`
explicitamente.

**`app.py`** é a raiz de composição: escolhe o
`IndexSource` (`GcsIndexSource` em produção, `LocalDirectoryIndexSource` quando apontado para
um diretório), cria o `Core` e chama `start()` e `close()` no lifespan ASGI (abertura
inicial e tarefa de verificação começam e terminam com o processo, nunca no construtor),
monta as duas aplicações ASGI, expõe `/healthz` (repassa
`health()` do `core`: `generated_at` de cada dataset, `index_built_at`, `stale`,
`index_version`, `last_index_check_at`, o instante da última verificação bem-sucedida do
`IndexSource`, e `last_index_check_error`, instante e mensagem da última falha, ou nulo) e
aplica o limite por IP: token bucket em memória por instância,
`429` com `Retry-After`, IP lido de `CF-Connecting-IP` apenas quando a requisição vem das
faixas da Cloudflare (ADR 0005). Logs registram o IP truncado, nunca completo.

Ao contrário do limite por IP, que fica inteiramente no ASGI middleware acima, a telemetria
(`telemetry.py`, ticket #17) atravessa os próprios adaptadores: `create_mcp_server` e
`create_api` recebem um `Telemetry` como parâmetro, e cada tool e cada rota chama
`Telemetry.call` ao redor da chamada ao `core` (seção 2). `app.py` monta a instância a partir
de `Settings.telemetry` (`None` desliga, o padrão e o padrão nos testes) e a repassa aos dois
adaptadores, para que os dois emitam pelo mesmo cliente. O que telemetria coleta e as
variáveis de ambiente que a configuram estão no README ("Telemetria") e em
`docs/local-run.md`, não aqui.

## 5. `pipeline`: separado do serviço

Roda em GitHub Actions agendado (cron alinhado às cadências do TSE) e em `workflow_dispatch`;
nunca dentro do Cloud Run. Cinco estágios, cada um uma função com entrada e saída em arquivo,
para que qualquer estágio rode sozinho:

1. **fetch**: baixa os ZIPs do CDN do TSE por meio de uma porta `Downloader`. Dois adaptadores
   justificam o seam: `CurlCffiDownloader` em produção (impersonação TLS, ADR 0003) e
   `LocalFilesDownloader` nos testes. Grava em diretório temporário, apagado ao fim do run.
2. **build**: lê os CSVs com DuckDB, aplica `index_schema.py`, descarta as colunas proibidas
   antes de qualquer gravação, deriva os campos marcados como derivados no modelo de domínio
   e escreve `index.duckdb`. A mesma função constrói os índices de teste do `core`.
3. **validate**: portões que bloqueiam a publicação: cabeçalho de cada CSV igual ao esperado;
   chave (`uf`, `zone`, `section`, `round`) única nas seções e (`sq_candidato`, `round`) única
   nos candidatos; colunas proibidas ausentes; contagens dentro de 5% da versão anterior;
   `DT_ELEICAO` de cada turno presente igual à data do turno de mesmo número na eleição do
   YAML de mesmo ano que `AA_ELEICAO`/`ANO_ELEICAO`, portão que vale só para os arquivos de
   eleição (o arquivo mensal `ATUAL` o pula, porque não pertence a uma eleição do YAML); e as
   suposições listadas na seção 7 do modelo de domínio.
4. **mirror_photos**: sincroniza os JPEGs por UF com o bucket R2, gravando só o que o TSE
   publica e removendo o que sumiu da fonte (ADR 0004, ADR 0005).
5. **publish**: envia `index.duckdb` e `manifest.json` (`generated_at` por dataset,
   `index_built_at`, `election_year` e `election_dates` por turno presente, contagens,
   SHA-256) para o bucket do índice, mantendo as versões anteriores para rollback. A eleição
   do índice (`election_year` e `election_dates`) só é gravada quando todos os datasets do
   índice são arquivos de eleição do mesmo ano, lidos das linhas já validadas contra o YAML;
   é nula sempre que qualquer dataset vier do arquivo mensal `ATUAL`, mesmo que os candidatos
   continuem vindo de `consulta_cand_2026`. É a única entrada da regra de coincidência da
   seção 3.4.

O pipeline importa `domain.py`, `elections.py` e `index_schema.py`. Nunca importa o `core` nem
os adaptadores; nunca sobe um servidor.

## 6. `data/elections.yaml` e `elections.py`

Um arquivo curado à mão por eleição, com o esquema imposto por `elections.py` e testado em
`tests/test_elections_yaml.py`. É lido pelo `core` (resposta de `election_info` e o campo
`election` de todo envelope) e pelo pipeline (validação de `DT_ELEICAO`). O loader rejeita
duas eleições no mesmo ano, para que "a eleição do YAML de mesmo ano" (seções 3.4 e 5) tenha
sempre uma só resposta; uma eleição suplementar entra como nota, não como entrada própria.
Não contém URLs de datasets nem configuração de infraestrutura; isso fica no pipeline.

## 7. Página estática e Jev

A página em `web/` é HTML, CSS e JavaScript sem build, publicada no Cloudflare Pages, e
consome apenas a REST. Ela tem sempre os formulários estruturados (UF, zona e seção; cidade e
bairro; cargo e nome ou número; data da eleição) e, acima deles, uma caixa de linguagem
natural. A caixa é um adaptador com dois componentes:

- Uma **Pages Function** (`web/functions/ask.js`) que guarda a chave do Jev como segredo,
  aplica seu próprio limite por IP e faz ao Jev uma única pergunta do tipo Choice: a intenção
  do texto entre `onde_voto`, `locais_da_cidade`, `candidatos`, `data_e_horario`,
  `cadastro_individual` e `fora_do_escopo`, com a confiança da resposta.
- JavaScript determinístico na página que extrai UF, zona, seção, município, bairro, cargo,
  nome ou número do texto por expressões regulares e preenche o formulário correspondente à
  intenção, chamando a REST.

Confiança baixa, `cadastro_individual`, `fora_do_escopo`, erro ou indisponibilidade do Jev
levam ao mesmo lugar: os formulários, que já estão na tela, e a orientação para o e-Título
quando a pergunta depende do cadastro. O Jev está fora do caminho crítico: a página funciona
inteira sem ele, e o serviço Python não sabe que ele existe (ADR 0006).

## 8. Contratos das seis tools

Nomes de tool e de campo em inglês; descrições, enums e textos em PT-BR. Toda resposta tem
este envelope, tanto no `structuredContent` do MCP quanto no JSON da REST:

```json
{
  "data": { },
  "not_found": null,
  "warnings": [],
  "election": {
    "id": "general-2026",
    "name": "Eleições Gerais 2026",
    "round": { "number": 1, "date": "2026-10-04" },
    "voting_hours": {
      "start": "08:00", "end": "17:00", "timezone": "America/Sao_Paulo",
      "label": "8h às 17h (horário de Brasília)"
    }
  },
  "source": {
    "kind": "dataset",
    "dataset": "Eleitorado por local de votação - 2026",
    "dataset_url": "https://dadosabertos.tse.jus.br/dataset/eleitorado-2026",
    "file": "eleitorado_local_votacao_2026_BRASIL.csv",
    "generated_at": "2026-09-17T06:30:20-03:00",
    "index_built_at": "2026-09-17T09:05:11-03:00",
    "age_hours": 12.4,
    "stale": false,
    "license": "CC-BY",
    "attribution": "Tribunal Superior Eleitoral - Portal de Dados Abertos"
  }
}
```

- `data` é nulo quando `not_found` está preenchido, e vice-versa.
- `not_found` tem `reason` (enum PT-BR) e `guidance` (texto para o eleitor).
- `warnings` é uma lista de textos em PT-BR prontos para o eleitor, sempre presente, às vezes
  vazia.
- `election` é a eleição corrente do `elections.yaml` com o turno a que a resposta se refere,
  ou nulo; quando é preenchido e quando é nulo está na seção 3.4, única dona da regra.
- `source` segue o objeto de valor da seção 3.6 do modelo de domínio; para `election_info`,
  `kind` é `curated`, com `calendar_source` e `verified_at`.

### 8.1 `find_polling_place`

Descrição: "Encontra o local de votação a partir da UF, da zona e da seção impressas no
título de eleitor ou no e-Título. Não aceita nome, CPF ou número do título: para descobrir a
própria zona e seção, o eleitor usa o e-Título."

Input: `uf` (string, 2 letras: estados, DF ou ZZ para o exterior), `zone` (inteiro, aceita
string com zeros à esquerda), `section` (idem), `round` (inteiro, opcional; resolução na
seção 3.4, linhas T1 a T7).

`data` (exemplo com os valores verificados pelo scout para AC, zona 9, seção 422; `number` do
local e `ibge_code` são ilustrativos):

```json
{
  "municipality": { "tse_code": "01392", "ibge_code": 1200000, "name": "RIO BRANCO", "uf": "AC" },
  "round": 1,
  "zone": 9,
  "section": 422,
  "section_kind": "principal",
  "votes_at_section": 422,
  "voters_in_section": 260,
  "accessibility": "com_acessibilidade",
  "place": {
    "number": 1000, "name": "IEPTEC - ANTIGO INSTITUTO FEDERAL DO ACRE - IFAC - BAIXADA",
    "kind": "Convencional", "address": "RUA RIO GRANDE DO SUL, 2600",
    "neighborhood": "AEROPORTO VELHO", "postal_code": "69911030", "phone": null,
    "latitude": -9.9848126, "longitude": -67.8225501,
    "status": "ativo", "section_count": 12, "accessible_section_count": 12
  },
  "previous_place": null
}
```

`accessibility` é atributo da seção consultada (`DS_SITU_SECAO_ACESSIBILIDADE`), por isso fica
ao lado de `section_kind` e `voters_in_section`. O local só tem a contagem
`accessible_section_count` sobre `section_count`: num prédio com seções acessíveis e não
acessíveis, os dois números mostram a diferença em vez de um rótulo ambíguo. `section_count` e
`accessible_section_count` do exemplo são ilustrativos.

Avisos possíveis: seção agregada ("Sua seção é agregada: a votação acontece na seção 8, no
mesmo local."); local mudou ("O local de votação mudou. Antes era EMEF AMÁLIA PAUNGARTTEN,
endereço X."); os avisos de turno da seção 3.4; dado envelhecido (seção 9).

`not_found.reason`: `secao_nao_encontrada`. `guidance`: "Confira a zona e a seção no
e-Título ou no título impresso. Sem o título, use o serviço Onde votar do TSE:
https://www.tse.jus.br/servicos-eleitorais/autoatendimento-eleitoral#/atendimento-eleitor/onde-votar".

### 8.2 `search_polling_places`

Descrição: "Lista os locais de votação de um município, com filtro por bairro, nome do local
ou endereço, e ordenados pela distância a um ponto quando o cliente informa coordenadas. Para
quem não sabe a zona e a seção."

Input: `uf`, `municipality` (nome ou código TSE), `neighborhood` (opcional), `query`
(opcional, casa com nome do local ou endereço), `near` (opcional, `{latitude, longitude}`),
`limit` (1 a 50, padrão 20), `round` (inteiro, opcional; resolução na seção 3.4, linhas T1 a
T7).

`data`: `round` (o turno respondido, seção 3.4), `municipality`, `places[]` com `number`,
`zone`, `name`, `kind`, `address`,
`neighborhood`, `postal_code`, `phone`, `latitude`, `longitude`, `status`, `section_count`,
`accessible_section_count`, `voters` e `distance_km` (só com `near`), `total` e `guidance`
("Para saber a sua seção, consulte o e-Título."). Sem geocodificação no servidor: `near` é
o que o cliente já tem.

`not_found.reason`: `municipio_nao_encontrado` ou `municipio_ambiguo` (com `options[]` no
formato de `resolve_municipality`).

### 8.3 `list_candidates`

Descrição: "Lista os candidatos de um cargo numa UF (BR para presidente), com filtro por
partido ou por nome de urna ou nome civil. Nunca inclui CPF, título de eleitor, data de
nascimento ou e-mail."

Input: `uf` (estados, DF ou BR), `office` (enum: `presidente`, `governador`, `senador`,
`deputado_federal`, `deputado_estadual`, `deputado_distrital`), `party` (opcional, sigla ou
número), `name` (opcional, sem acento e sem diferenciar maiúsculas), `on_ballot_only`
(padrão `true`), `limit` (1 a 50, padrão 50), `offset` (padrão 0), `round` (inteiro,
opcional; resolução na seção 3.4, linhas C1 a C4).

`data`: `round` (o turno efetivamente respondido), `candidates[]` com `sq_candidato`,
`number`, `ballot_name`, `name`, `office`, `party {number, acronym, name}`,
`federation {acronym, name}` ou nulo, `coalition {name}` ou nulo, `adjudication_status`,
`on_ballot`, `occupation`, `photo_url`; mais `total`, `limit` e `offset`. Nunca inclui
gênero, cor/raça, estado civil ou grau de instrução: esses campos existem só na ficha
individual (8.4).

Avisos possíveis: os de turno da seção 3.4 e o de dado envelhecido (seção 9).

### 8.4 `get_candidate`

Descrição: "Ficha de um candidato, pelo sq_candidato ou por UF, cargo e número. Inclui vice
ou suplentes da chapa, redes sociais declaradas ao TSE e o link da página oficial no
DivulgaCandContas. Nunca inclui CPF, título de eleitor, data de nascimento ou e-mail."

Input: `sq_candidato` ou o trio `uf`, `office`, `number`; `round` (inteiro, opcional;
resolução na seção 3.4, linhas F1 a F5). Em ambos os casos o `core` primeiro determina o
conjunto de turnos da candidatura e só então aplica a tabela. Por `sq_candidato`, são os
turnos em que ele aparece. Pelo trio, o `core` reúne as candidaturas `on_ballot` com esse
(`uf`, `office`, `number`) em qualquer turno, no máximo uma por turno, e usa os turnos delas.
`not_found` com `candidato_nao_encontrado` quando o conjunto é vazio: por `sq_candidato`,
quando ele não existe em turno nenhum; pelo trio, quando nenhum candidato com esse número
está na urna, mesmo que exista uma candidatura fora da urna com o número.

`data.candidate`: os campos de 8.3 mais `round`, `social_name`, `nomination_kind`,
`federation.composition`, `coalition.composition`, `gender`, `race_color`, `marital_status`,
`education` (como o TSE publica, sem inferência), `running_mates[]` (`sq_candidato`,
`office`, `ballot_name`, `name`, `party`), `social_links[]` e `divulgacandcontas_url`.

Avisos possíveis: os de turno da seção 3.4 e o de dado envelhecido (seção 9); o de dado
envelhecido também aparece em `not_found`, já que a idade do índice independe de o número
buscado existir.

`not_found.reason`: `candidato_nao_encontrado`.

### 8.5 `election_info`

Descrição: "Data e horário da votação, turnos, cargos em disputa e a fonte oficial. Responde
'quando é a eleição' e 'até que horas posso votar'."

Input: `on` (data, opcional; padrão: hoje em `America/Sao_Paulo`).

`data`: `rounds[]` (`number`, `date`, `note`), `voting_hours`, `next_round` ou nulo,
`days_until_next_round`, `offices[]`, `notes[]`, `calendar_source {title, url,
verified_at}`. `source.kind = curated`.

### 8.6 `resolve_municipality`

Descrição: "Encontra o código de um município a partir do nome, com ou sem acento, para usar
nas outras ferramentas."

Input: `name`, `uf` (opcional), `limit` (1 a 50, padrão 10).

`data.municipalities[]`: `tse_code`, `ibge_code`, `name`, `uf`, `score`. `source` aponta
para o crosswalk TSE/IBGE.

## 9. Dado envelhecido

O serviço nunca recusa uma resposta por idade do dado. Regras, todas no `core`:

- `source.generated_at` é sempre a data de geração gravada pelo TSE no arquivo de origem,
  nunca a data do build.
- `age_hours` é calculada com o relógio injetado; `stale = age_hours > 48`, constante
  `STALE_AFTER_HOURS = 48`.
- Quando `stale`, `warnings` ganha: "Os dados do TSE usados nesta resposta foram gerados em
  17/09/2026 às 06:30 (há 60 horas). Confira no e-Título se algo mudou."
- `election_info` não envelhece: vem do YAML curado, com `verified_at`.
- `/healthz` expõe os mesmos campos, mais `index_version`, `last_index_check_at` e
  `last_index_check_error` (seção 4), para alertar quando o índice fica mais de 24 horas sem
  build ou quando a verificação do `IndexSource` está falhando, antes de o eleitor ver o
  aviso de 48 horas.

O limiar de 48 horas é decisão de produto: candidatos mudam 4 vezes ao dia e locais 1 vez ao
dia, então 48 horas significa ao menos dois refreshes perdidos.

## 10. Estratégia de testes

- **`core`**: pela interface, sobre um índice construído com a função de build do pipeline a
  partir de fixtures CSV com os cabeçalhos reais e entregue por `LocalDirectoryIndexSource`.
  Cobre todos os cenários da seção 6 do modelo de domínio e a recarga por troca de manifesto
  (via `refresh()`, sem `start()` e sem thread), mais o teste próprio da tarefa de fundo
  descrito em 3.3.
- **`index_store.py`**: `LocalDirectoryIndexSource` com diretórios de fixture;
  `GcsIndexSource` com um cliente GCS falso em memória, cobrindo "manifesto igual, não baixa",
  "manifesto novo, baixa e renomeia" e "download interrompido, versão anterior continua".
- **Adaptadores**: cliente ASGI de teste para a REST e cliente MCP em memória para as tools,
  com um `Core` real sobre o índice de fixtures. Verificam a serialização, o `outputSchema`,
  os códigos de erro e a presença de `source` e `election` em toda resposta.
- **Pipeline**: cada estágio com entrada e saída em arquivo; `fetch` com o
  `LocalFilesDownloader`; `validate` com fixtures que violam cada portão, um por teste.
- **LGPD**: um teste lista as colunas proibidas de `index_schema.py` e falha se qualquer uma
  existir no índice construído ou aparecer em qualquer resposta serializada.
- **Ficha versus lista**: teste de contrato sobre os modelos de `answers.py`: o modelo do item
  de lista de `CandidatesAnswer` não declara `gender`, `race_color`, `marital_status` nem
  `education` (verificado no `outputSchema` gerado), e nenhuma resposta serializada de
  `list_candidates` sobre o índice de fixtures contém essas chaves, enquanto a resposta de
  `get_candidate` para o mesmo candidato as contém.
- **Resolução de turno**: um teste por linha da tabela da seção 3.4, mais um para
  `election` nula com índice do arquivo `ATUAL` e YAML com eleição futura, e um para o trio
  com número compartilhado por um indeferido fora da urna e seu substituto; sobre o índice de
  fixtures de 3.3 (seções nos dois turnos, presidente nos dois turnos, presidente eliminado
  só no turno 1, demais cargos só no turno 1) e sobre uma variante sem o turno 2, com o
  relógio injetado antes, entre e depois dos turnos do calendário. Cada teste afirma
  `data.round`, `election`, o aviso exato e, nas listas, `total > 0`; o do presidente
  eliminado afirma que `get_candidate` sem `round` e com `round=2` devolvem a ficha do turno
  1, nunca `not_found`.
- **Calendário**: `tests/test_elections_yaml.py`, já existente.

Nenhum teste chama a rede. O acesso real ao TSE é verificado por um workflow separado, manual,
que roda o `fetch` de produção e reporta o código HTTP (ADR 0003).

## 11. O que não é seam

- **DuckDB**: um adaptador só (produção e testes usam o mesmo motor). Sem porta de
  repositório. A porta `IndexSource` é sobre de onde vem o arquivo, não sobre como ele é
  consultado.
- **Cloud Run e Cloudflare**: a aplicação é ASGI comum; trocar de hospedagem não toca em
  código.
- **FastAPI**: o `core` devolve modelos pydantic; trocar o framework REST é reescrever
  `api.py`, um arquivo fino.
- **Jev**: adaptador da página, com dois destinos possíveis (Jev ou os formulários); o seam
  fica no JavaScript da página, nunca no serviço.
