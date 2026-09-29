# Modelo de domínio

Este documento fixa as entidades do br-elections-mcp, seus invariantes, de onde cada campo vem
nos CSVs do TSE e o que é descartado. O vocabulário canônico está em
[`CONTEXT.md`](../CONTEXT.md); as fronteiras de módulo e os contratos das tools, em
[`codebase-design.md`](codebase-design.md). Os números citados vêm do relatório do scout de
2026-09-17 (investigação dos dados abertos do TSE, mantido fora do repositório), com a seção
indicada entre parênteses.

Convenções: identificadores em inglês; valores de domínio (enums, avisos, orientações) em
PT-BR. Um campo marcado **derivado** é calculado na ingestão, não lido de uma coluna.

## 1. Escopo

O serviço responde cinco grupos de pergunta do eleitor.

| # | Pergunta | Entidades | Fonte |
|---|---|---|---|
| 1 | Onde voto? A partir de UF, zona e seção do título | PollingSection, PollingPlace, Municipality | dataset de locais de votação |
| 2 | Quais são os locais de votação da minha cidade ou bairro? | PollingPlace, Municipality | dataset de locais de votação e crosswalk TSE/IBGE |
| 3 | Quem são os candidatos? Por cargo, nome ou número | Candidate, Office, Party, Federation, Coalition | datasets de candidatos, complementar, redes sociais e fotos |
| 4 | Quando é a eleição e até que horas posso votar? | Election, ElectionRound, VotingHours | `data/elections.yaml`, curado da Resolução TSE 23.760/2026 |
| 5 | Como estas 2 a 4 candidaturas se comparam lado a lado? (ADR 0008) | Candidate, com destino dos votos e total de bens declarados | datasets de candidatos, complementar, redes sociais, bens e fotos |

Fora do domínio, por construção: tudo que depende do cadastro eleitoral individual (zona e
seção a partir de nome, CPF ou título; situação do título; débitos; justificativas; convocação
de mesário) e a apuração de resultados. Para o primeiro grupo o serviço devolve orientação para
o e-Título e para o autoatendimento do TSE; para o segundo, nada. Não existe, e não deve
existir, lista de eleitores em nenhum dataset ingerido: o dado de locais é agregado por seção.

## 2. Datasets de origem (§1.2)

Todos os datasets abaixo são CC-BY, distribuídos em ZIP com um CSV por UF mais `_BRASIL`,
separador `;`, codificação ISO-8859-1, aspas em todos os campos e as colunas `DT_GERACAO` e
`HH_GERACAO` em toda linha.

| Dataset (CKAN) | Arquivo | Conteúdo | Cadência declarada pelo TSE |
|---|---|---|---|
| `eleitorado-2026` | `eleitorado_local_votacao_2026.zip` (88 MB) | 517.179 seções, 83.688 locais (95.601 pela chave certa, 3.3), 5.757 municípios (inclui exterior) | diária, 06:25 |
| `eleitorado-atual` | `eleitorado_local_votacao_ATUAL.zip` (45,9 MB) | mesmo esquema, cadastro mensal; fonte fora do ano eleitoral | mensal, dia 1, 00:00 |
| `candidatos-2026` | `consulta_cand_2026.zip` (3,2 MB) | 20.984 candidaturas | 4x ao dia: 08:30, 12:30, 16:30, 19:30 |
| `candidatos-2026` | `consulta_cand_complementar_2026.zip` (1,3 MB) | situação de julgamento e presença na urna, por `SQ_CANDIDATO` | idem |
| `candidatos-2026` | `rede_social_candidato_2026.zip` (2,9 MB) | `SQ_CANDIDATO`, `DS_URL` | idem |
| `candidatos-2026` | `bem_candidato_2026.zip` (3,7 MB) | um bem declarado por linha: `SQ_CANDIDATO`, `VR_BEM_CANDIDATO` (vírgula decimal), tipo e descrição livre; 77.254 bens de 13.909 candidaturas em 2026-09-25 (ADR 0008) | não declarada; regerado com os candidatos |
| `candidatos-2026` | `foto_cand2026_{UF}_div.zip` (AC 2,3 MB, SP 15,6 MB) | JPEG `F{UF}{SQ_CANDIDATO}_div.jpg` | não declarada |
| `codigos-oficiais-de-uf-e-municipios-segundo-o-tse-e-o-ibge` | `municipio_tse_ibge.zip` (0,1 MB) | 5.571 municípios com código TSE e IBGE | não declarada |

Não ingeridos: perfil do eleitorado por seção (§1.2 d, sem utilidade para o eleitor), vagas,
frequência de atualização (usada só como referência) e qualquer dataset de resultados.

## 3. Entidades

### 3.1 Election (eleição)

Fonte: `data/elections.yaml`, curado à mão a cada eleição. O TSE não publica calendário nem
horário em formato consumível por máquina (§1.3). Implementada em
`src/br_elections_mcp/domain.py`; o esquema do YAML é validado por
`src/br_elections_mcp/elections.py`.

| Campo | Tipo | Origem |
|---|---|---|
| `id` | str | curado, ex.: `general-2026` |
| `name` | str | curado, ex.: "Eleições Gerais 2026" |
| `year` | int | curado |
| `kind` | `ElectionKind`: `geral`, `municipal` | curado |
| `rounds[]` | `ElectionRound(number, date, note)` | curado da Res. TSE 23.760/2026 |
| `voting_hours` | `VotingHours(start, end, timezone)` | curado: 08:00 às 17:00, `America/Sao_Paulo` |
| `offices[]` | `Office` | curado: os cargos em disputa |
| `calendar_source` | `CalendarSource(title, url, verified_at)` | curado |
| `notes[]` | str, PT-BR | curado: avisos ao eleitor |

Invariantes (todos verificados no construtor):

- Turnos numerados de 1 a n, em ordem crescente de data, todos dentro de `year`.
- `start < end`; `timezone` é um nome IANA válido.
- Todo cargo em `offices` é cargo de urna (`Office.is_ballot_office`); vice e suplentes não
  são "cargos em disputa", pertencem a uma chapa.
- `calendar_source.url` é HTTPS.
- Entre eleições do arquivo: `id` único e no máximo uma eleição por `year` (verificados no
  loader, `elections.py`, não no construtor).

Cruzamento com os CSVs: nos arquivos de eleição, o pipeline falha se `DT_ELEICAO` e
`NR_TURNO` do dataset de locais ou de candidatos não baterem com a data do turno de mesmo
número na eleição do YAML de mesmo ano (§1.3, §5.2); o arquivo mensal `ATUAL` não pertence a
uma eleição do YAML e pula esse cruzamento. O YAML é a fonte da resposta; o CSV é a
verificação.

### 3.2 Municipality (município)

Fonte: crosswalk `municipio_tse_ibge` (5.571 linhas) unido às colunas de município do dataset
de locais (5.757 municípios, incluindo o exterior).

| Campo | Tipo | Coluna |
|---|---|---|
| `tse_code` | str, 5 dígitos com zeros à esquerda | `CD_MUNICIPIO_TSE` (crosswalk) = `CD_MUNICIPIO` (locais) |
| `ibge_code` | int de 7 dígitos ou nulo | `CD_MUNICIPIO_IBGE` |
| `name` | str | `NM_MUNICIPIO_TSE`; fallback `NM_MUNICIPIO` (locais) quando o município não está no crosswalk |
| `uf` | `UF` | `SG_UF` |
| `search_name` | str, **derivado** | nome sem acento, em maiúsculas, para busca |

Invariantes: `tse_code` único; `ibge_code` único quando presente; municípios com `uf = ZZ`
(exterior) não têm `ibge_code`. A diferença entre 5.757 e 5.571 é, provavelmente, o conjunto
de localidades no exterior; o pipeline confirma isso na primeira ingestão (seção 7).

Descartadas: `CD_UF_TSE`, `CD_UF_IBGE`, `NM_UF`, `NM_MUNICIPIO_IBGE` (redundantes com a UF e
com o nome do TSE).

### 3.3 PollingPlace (local de votação)

Fonte: dataset de locais de votação, agregado por local. Um local é o prédio; as seções
apontam para ele.

| Campo | Tipo | Coluna |
|---|---|---|
| `uf` | `UF` (estados, DF, ZZ) | `SG_UF` |
| `zone` | int | `NR_ZONA` |
| `number` | int | `NR_LOCAL_VOTACAO` |
| `municipality` | ref. Municipality | `CD_MUNICIPIO` |
| `name` | str | `NM_LOCAL_VOTACAO` |
| `kind` | str, PT-BR | `DS_TIPO_LOCAL` (ex.: "Convencional") |
| `address` | str | `DS_ENDERECO` |
| `neighborhood` | str | `NM_BAIRRO` |
| `postal_code` | str, 8 dígitos | `NR_CEP` |
| `phone` | str ou nulo | `NR_TELEFONE_LOCAL` |
| `latitude`, `longitude` | float ou nulo | `NR_LATITUDE`, `NR_LONGITUDE` (vírgula decimal; `-1` vira nulo; 2,3% das seções sem coordenada) |
| `status` | `ativo`, `bloqueado` | `DS_SITU_LOCAL_VOTACAO`, por seção; `any_value` ao agregar por local |
| `previous_place` | `PreviousPlace(number, name, address)` ou nulo | `NR_LOCAL_VOTACAO_ORIGINAL`, `NM_LOCAL_VOTACAO_ORIGINAL`, `DS_ENDERECO_LOCVT_ORIGINAL`, só quando `NR_LOCAL_VOTACAO_ORIGINAL != NR_LOCAL_VOTACAO` |
| `section_count` | int, **derivado** | contagem de seções do local no turno |
| `accessible_section_count` | int, **derivado** | seções com acessibilidade |
| `voters` | int, **derivado** | soma de `QT_ELEITOR_SECAO` |

Invariantes:

- Identidade: (`uf`, `zone`, `municipality`, `number`) por turno. O número do local é único
  por município dentro da zona, não por zona: na primeira ingestão real (arquivo de 2026,
  gerado em 23/09/2026) 12.212 chaves (`uf`, `zone`, `number`) abrangem mais de um município,
  e a chave com o município dá 95.601 locais com nome e endereço constantes. O pipeline valida
  essa constância (seção 7).
- O índice só inclui em `polling_places` o prédio que tem ao menos uma seção principal no
  turno, ou seja, uma urna. Um local com apenas seções agregadas (1.233 dos 95.601 na chave
  com o município, arquivo de 2026) fica fora da busca; as seções continuam em
  `polling_sections`.
  `section_count`, `accessible_section_count` e `voters` dos locais restantes seguem contando
  todas as seções cadastradas no local, agregadas incluídas.
- `latitude` e `longitude` são ambos presentes ou ambos nulos; presentes, estão em [-90, 90] e
  [-180, 180].
- `previous_place` presente implica aviso "o local mudou" em toda resposta que contenha o
  local (§2.1: 16.713 seções nessa situação).
- A API expõe `status`, mas seu valor por local é arbitrário quando as seções divergem; a
  semântica de `bloqueado` permanece desconhecida. O aviso de mudança de local se apoia em
  `previous_place`, não em `status` (seção 7).

Descartadas: `CD_TIPO_LOCAL`, `CD_SITU_LOCAL_VOTACAO`, `CD_SITU_LOCALIDADE`,
`DS_SITU_LOCALIDADE` (códigos redundantes com as descrições ou sem uso para o eleitor).

### 3.4 PollingSection (seção eleitoral)

Fonte: dataset de locais de votação, uma linha por seção e turno.

| Campo | Tipo | Coluna |
|---|---|---|
| `uf` | `UF` (estados, DF, ZZ) | `SG_UF` |
| `zone` | int | `NR_ZONA` |
| `section` | int | `NR_SECAO` |
| `round` | int | `NR_TURNO` |
| `municipality` | ref. Municipality | `CD_MUNICIPIO` |
| `polling_place` | ref. PollingPlace | `NR_LOCAL_VOTACAO` (com `SG_UF`, `NR_ZONA` e `CD_MUNICIPIO`) |
| `section_kind` | `principal`, `agregada` | `DS_TIPO_SECAO_AGREGADA` |
| `main_section` | int ou nulo | `NR_SECAO_PRINCIPAL` (`-1` vira nulo) |
| `voters` | int | `QT_ELEITOR_SECAO` |
| `accessibility` | `com_acessibilidade`, `sem_acessibilidade` | `DS_SITU_SECAO_ACESSIBILIDADE` |
| `status` | str, PT-BR | `DS_SITU_SECAO` |
| `election_date` | date | `DT_ELEICAO` (só para o cruzamento com o YAML) |

Invariantes:

- (`uf`, `zone`, `section`, `round`) é única em todo o Brasil: 517.179 linhas, 517.179 chaves
  distintas, com ou sem município (§2.1). O município é redundante na busca; uma zona pode
  abranger vários municípios, mas a seção é única dentro da zona.
- `section_kind = agregada` implica `main_section` presente e diferente de `section`;
  `principal` implica `main_section` nulo. 499.248 principais e 17.931 agregadas (§1.2 a).
- O eleitor de uma seção agregada vota no local da seção principal, que em geral é o mesmo
  local da agregada, mas nem sempre: no arquivo de 2026, 1.996 das 17.931 agregadas estão
  cadastradas em outro local, 1.807 delas num local sem nenhuma seção principal, portanto sem
  urna (e `QT_ELEITOR_ELEICAO_*` é zero nas agregadas, contadas na principal). "Onde voto"
  responde o local da principal; o pipeline valida que a principal existe na mesma zona e
  turno e é ela mesma principal (seção 7). Esses locais sem principal não entram em
  `polling_places` (3.3), e a resposta de "onde voto" nunca depende deles.
- Em 2026-09-17 o dataset só tem `NR_TURNO = 1`. Quando o TSE publicar o 2º turno, o índice
  carrega os dois e a chave passa a incluir o turno de fato (§2.1).
- Entrada humana é normalizada antes da busca: "zona 009" e "seção 0422" viram 9 e 422.

Descartadas: `CD_TIPO_SECAO_AGREGADA`, `CD_SITU_SECAO`, `CD_SITU_ZONA`, `DS_SITU_ZONA`,
`CD_SITU_SECAO_ACESSIBILIDADE`, `QT_ELEITOR_ELEICAO_FEDERAL`, `QT_ELEITOR_ELEICAO_ESTADUAL`,
`QT_ELEITOR_ELEICAO_MUNICIPAL`, `AA_ELEICAO`, `DS_ELEICAO` (códigos redundantes ou
contagens sem pergunta do eleitor). `DT_GERACAO` e `HH_GERACAO` não pertencem à seção: vão para
`Source` (3.6).

### 3.5 Candidate (candidato)

Fonte: `consulta_cand_2026`, uma linha por candidatura e turno, unido ao complementar
(situação de julgamento e presença na urna), às redes sociais e à foto. O join com o
complementar é por (`SQ_CANDIDATO`, `NR_TURNO`) quando o complementar trouxer `NR_TURNO`; se
não trouxer, o pipeline deduplica o complementar por `SQ_CANDIDATO` e aplica a mesma linha aos
dois turnos, e a escolha fica registrada na validação (seção 7). Redes sociais e foto não têm
turno: valem para todos os turnos do `SQ_CANDIDATO`. A coluna `DS_SITUACAO_CANDIDATURA` do
arquivo principal vem `#NE` em 100% das linhas; a situação útil está só no complementar
(§1.2 b).

| Campo | Tipo | Coluna |
|---|---|---|
| `sq_candidato` | int, identidade junto com `round` | `SQ_CANDIDATO` |
| `round` | int, identidade junto com `sq_candidato` | `NR_TURNO` |
| `election` | ref. Election | `ANO_ELEICAO`, `DT_ELEICAO` (cruzamento com o YAML) |
| `uf` | `UF` (estados, DF, BR) | `SG_UF` (`BR` para presidente e vice) |
| `office` | `Office` | `DS_CARGO`, mapeado pelo texto e validado na ingestão |
| `number` | int | `NR_CANDIDATO` |
| `ballot_name` | str | `NM_URNA_CANDIDATO` |
| `name` | str | `NM_CANDIDATO` |
| `social_name` | str ou nulo | `NM_SOCIAL_CANDIDATO` (`#NULO` vira nulo) |
| `party` | `Party(number, acronym, name)` | `NR_PARTIDO`, `SG_PARTIDO`, `NM_PARTIDO` |
| `nomination_kind` | `partido_isolado`, `federacao`, `coligacao` | `TP_AGREMIACAO` |
| `federation` | `Federation(acronym, name, composition)` ou nulo | `SG_FEDERACAO`, `NM_FEDERACAO`, `DS_COMPOSICAO_FEDERACAO` (`#NULO` e `NR_FEDERACAO = -1` viram nulo) |
| `coalition` | `Coalition(name, composition)` ou nulo | `NM_COLIGACAO`, `DS_COMPOSICAO_COLIGACAO` ("PARTIDO ISOLADO" e `#NULO` viram nulo) |
| `adjudication_status` | str, PT-BR | `DS_SITUACAO_JULGAMENTO` (complementar) |
| `on_ballot` | bool | `ST_CANDIDATO_INSERIDO_URNA` (complementar; `SIM`/`NÃO`), falso quando outra candidatura do arquivo a substitui (`SQ_SUBSTITUIDO` dela aponta para esta) |
| `occupation` | str, PT-BR | `DS_OCUPACAO` |
| `vote_destination` | str ou nulo, PT-BR | `NM_TIPO_DESTINACAO_VOTOS` (complementar), como o TSE publica: "Válido", "Anulado sub judice", "Nulo técnico"; `#NULO` vira nulo (vices e suplentes vêm assim) |
| `declares_assets` | bool ou nulo | `ST_DECLARAR_BENS` (complementar): `S` verdadeiro, `N` falso (declarou não possuir bens), outro valor ("Não divulgável") nulo |
| `assets_total` | decimal ou nulo, **derivado** | soma de `VR_BEM_CANDIDATO` por `SQ_CANDIDATO` no dataset de bens, tabela `candidate_assets`; só o total, como declarado (ADR 0008) |
| `gender` | str, PT-BR | `DS_GENERO`, como o TSE publica; só na ficha individual |
| `race_color` | str, PT-BR | `DS_COR_RACA`, como o TSE publica; só na ficha individual |
| `marital_status` | str, PT-BR | `DS_ESTADO_CIVIL`, como o TSE publica; só na ficha individual |
| `education` | str, PT-BR | `DS_GRAU_INSTRUCAO`, como o TSE publica; só na ficha individual |
| `photo_url` | URL ou nulo, **derivado** | `F{SG_UF}{SQ_CANDIDATO}_div.jpg` do ZIP de fotos, espelhado no R2 |
| `social_links[]` | URL, **derivado** | `DS_URL` do dataset de redes sociais, normalizado em `pipeline/social_links.py`: só sobrevive o que vira `http(s)://host/...` sem espaço em branco, credenciais nem caracteres de controle; o resto é descartado sem interpretar o que dizia. Deduplicado e limitado a 10 por candidatura, na ordem declarada. |
| `running_mates[]` | ref. Candidate, **derivado** | candidatos de cargo de chapa com o mesmo (`election`, `round`, `uf`, `number`) cujo `Office.ticket_head` é o cargo do titular |
| `divulgacandcontas_url` | URL, **derivado** | página oficial da candidatura, para o humano abrir |

Invariantes:

- (`sq_candidato`, `round`) é a identidade. `sq_candidato` sozinho não é único: em eleições
  anteriores (`consulta_cand_2022`) o mesmo `SQ_CANDIDATO` aparece em duas linhas, `NR_TURNO`
  1 e 2, para presidente e governador que foram ao 2º turno. Em 2026-09-17 o dataset só tem
  `NR_TURNO = 1`; quando o TSE publicar o 2º turno, o índice carrega os dois e as consultas
  aceitam `round`. O padrão de turno para candidatos é diferente do de seções, porque só
  presidente e alguns governadores vão ao 2º turno: na lista é o maior turno em que (`uf`,
  `office`) tem linhas; na ficha é o maior turno da própria candidatura (cenário 14; a regra
  completa está na seção 3.4 de `codebase-design.md`).
- `uf = BR` só para `presidente` e `vice_presidente`; `deputado_distrital` só no DF;
  `deputado_estadual` nunca no DF.
- Entre candidatos `on_ballot`, `number` é único por (`election`, `round`, `uf`, `office`).
  Vice e suplentes repetem o número do titular: a chapa é derivada por (`election`, `round`,
  `uf`, `number`) dentro do grupo `Office.ticket_head`, e o pipeline valida que cada chapa tem
  exatamente um titular (seção 7). Uma candidatura substituída sai da urna mesmo quando o TSE
  ainda a marca `SIM`: no arquivo de 2026, 280 das 282 substituídas vêm com `NÃO` e 2 com
  `SIM`, uma delas ao lado da substituta de mesmo número (SP, deputado federal 3660).
- `gender`, `race_color`, `marital_status` e `education` aparecem só na ficha individual
  (`get_candidate`), nunca em `list_candidates` nem em agregados; entram como o TSE publica,
  sem inferência nem cruzamento (seção 5).
- A resposta nunca contém os campos descartados da seção 5, e a suíte de testes garante que
  eles não existem no índice.

Contagens de 2026-09-17 por cargo (§1.2 b): 11.292 deputados estaduais, 7.801 federais, 433
distritais, 350 e 349 suplentes, 319 senadores, 211 vice-governadores, 201 governadores, 14
presidentes, 14 vices.

Descartadas por LGPD ou minimização: ver seção 5. Descartadas por redundância ou falta de uso:
`CD_TIPO_ELEICAO`, `NM_TIPO_ELEICAO`, `CD_ELEICAO`, `DS_ELEICAO`, `TP_ABRANGENCIA`, `SG_UE`,
`NM_UE`, `CD_CARGO`, `CD_SITUACAO_CANDIDATURA`, `DS_SITUACAO_CANDIDATURA`, `NR_FEDERACAO`,
`SQ_COLIGACAO`, `CD_OCUPACAO`, `CD_GENERO`, `CD_COR_RACA`, `CD_ESTADO_CIVIL`,
`CD_GRAU_INSTRUCAO` (códigos redundantes com as descrições), `CD_SIT_TOT_TURNO`,
`DS_SIT_TOT_TURNO` (resultado da totalização: fora do escopo).

#### Office (cargo)

Enum em `domain.py`, com os dez valores presentes nas candidaturas de 2026:
`presidente`, `vice_presidente`, `governador`, `vice_governador`, `senador`,
`primeiro_suplente`, `segundo_suplente`, `deputado_federal`, `deputado_estadual`,
`deputado_distrital`. Os seis em `BALLOT_OFFICES` (`presidente`, `governador`, `senador`,
`deputado_federal`, `deputado_estadual`, `deputado_distrital`) são cargos de urna; vices e
suplentes têm `ticket_head` apontando para o titular da chapa. O mapeamento a partir de `DS_CARGO`
é feito pelo texto, e a ingestão falha alto diante de um valor desconhecido: o scout verificou
verbatim apenas `"DEPUTADO FEDERAL"`, e os demais textos são fixados na primeira ingestão.
Cargos municipais (prefeito, vice-prefeito, vereador) entram no enum quando uma eleição
municipal entrar no escopo.

### 3.6 Source (fonte), objeto de valor

Toda resposta carrega a fonte do dado que a produziu, por exigência da licença CC-BY (§1.5) e
para que o LLM cliente cite a origem.

| Campo | Tipo | Origem |
|---|---|---|
| `dataset` | str | nome do recurso no CKAN |
| `dataset_url` | URL | página do dataset |
| `file` | str | nome do CSV dentro do ZIP |
| `generated_at` | datetime com fuso | `DT_GERACAO` + `HH_GERACAO`, interpretados em `America/Sao_Paulo` (o scout observou `DT_GERACAO` 06:30 e `Last-Modified` 09:36 GMT no mesmo arquivo, §1.2 a) |
| `index_built_at` | datetime com fuso | manifesto do índice |
| `age_hours` | float, **derivado** | agora menos `generated_at` |
| `stale` | bool, **derivado** | `age_hours > 48` |
| `license` | str | "CC-BY" |
| `attribution` | str | "Tribunal Superior Eleitoral - Portal de Dados Abertos" |

Para respostas que vêm do `elections.yaml`, a fonte é `kind = curated`, com `calendar_source`
no lugar de dataset e `verified_at` no lugar de `generated_at`; não envelhece.

## 4. Relações

```
Election 1 ── n ElectionRound
Election 1 ── n Candidate ── 1 Party
                          ── 0..1 Federation
                          ── 0..1 Coalition
                          ── 0..n Candidate (running_mates, mesma chapa)
Municipality 1 ── n PollingPlace 1 ── n PollingSection
PollingSection (agregada) ── 1 PollingSection (principal, cujo local é onde o eleitor vota)
PollingSection ── 1 ElectionRound (via round + election_date)
Toda resposta ── 1 Source, 0..1 Election
```

## 5. LGPD: o que é descartado na ingestão e por quê

O CSV de candidatos de 2026 traz CPF completo, título de eleitor e data de nascimento de todos
os 20.984 candidatos, apesar de o próprio `leiame.pdf` declarar o CPF não divulgável
(Res. TSE 23.609/2019, art. 33, §2º) (§1.2 b, §1.5). Os `leiame.pdf` de cada dataset (CC-BY)
estão versionados em [`docs/tse/`](tse/README.md) pelo estágio `fetch` do pipeline, para que
estas citações sejam verificáveis. O pipeline descarta as colunas abaixo antes de gravar
qualquer coisa; elas não existem no índice, e um teste falha se voltarem.

| Coluna | Motivo |
|---|---|
| `NR_CPF_CANDIDATO` | dado pessoal; declarado não divulgável pelo próprio TSE |
| `NR_TITULO_ELEITORAL_CANDIDATO` | dado pessoal; identifica o cadastro eleitoral do candidato |
| `DT_NASCIMENTO` | dado pessoal; nenhuma pergunta do eleitor depende dela |
| `SG_UF_NASCIMENTO` | dado pessoal; sem pergunta do eleitor |
| `DS_EMAIL` | dado pessoal (vem "NÃO DIVULGÁVEL", descartada mesmo assim) |
| `DS_BEM_CANDIDATO` | texto livre de cada bem declarado: traz endereços, placas, agências e CPF do candidato e de terceiros (ADR 0009) |

A lista é a decidida pelo capitão no grilling de 2026-09-17, mais `DS_BEM_CANDIDATO`
(ADR 0009, 2026-09-25). A ADR 0009 também admite o título como chave de junção só em memória,
para o crescimento patrimonial da v1.1; ele continua descartado em toda gravação. Gênero, cor/raça,
estado civil e grau de instrução (`DS_GENERO`, `DS_COR_RACA`, `DS_ESTADO_CIVIL`,
`DS_GRAU_INSTRUCAO`) ficam no índice como o TSE publica, sem inferência nem cruzamento, e
aparecem só na ficha individual de `get_candidate`, nunca em `list_candidates` nem em
agregados. Os códigos correspondentes (`CD_*`) são descartados por redundância (3.5).

Regras complementares (detalhadas no ADR 0004):

- Nenhum enriquecimento ou cruzamento com outras bases; redes sociais e fotos entram como o TSE
  publica, sem inferência.
- Fotos espelhadas apenas enquanto o TSE as publica; o pipeline remove as que sumirem da fonte.
- Entradas do usuário (zona, seção, nome buscado) não são persistidas; logs sem IP completo.
- A API REST do DivulgaCandContas, que também devolve CPF e nascimento, não é fonte de dado:
  só entra como link para o humano abrir.

## 6. Cenários que o modelo precisa sustentar

1. **Título na mão.** "Zona 009, seção 0422, Acre": normaliza para (AC, 9, 422), encontra a
   seção principal em Rio Branco, devolve o local com endereço, CEP, coordenadas e
   acessibilidade (§2.1, resposta em 0,6 ms no DuckDB).
2. **Seção agregada.** (PA, 102, 9) é agregada com principal 8: a resposta traz o local e o
   aviso "sua seção é agregada; a votação acontece na seção 8, no mesmo local".
3. **Local mudou.** Belém, zona 29, seção 91 migrou de "EMEF Amália Paungartten" para
   "Universidade Federal do Pará" (caixa do índice, regra de nomes em `codebase-design.md`
   seção 7): `previous_place` preenchido, aviso "o local mudou; antes era EMEF Amália
   Paungartten".
4. **Exterior.** (ZZ, zona, seção) de Frankfurt resolve para um local em Colônia, Alemanha;
   município sem código IBGE; mesmo esquema.
5. **Segundo turno ainda não publicado.** Pedido com `round = 2` antes de o TSE publicar as
   linhas de 2º turno: devolve o 1º turno com aviso, nunca "não encontrado".
6. **Seção inexistente.** (SP, 1, 99999): `not_found` com orientação para conferir no e-Título
   ou no autoatendimento do TSE. Nunca tenta descobrir a seção pelo nome.
7. **Sem zona nem seção.** "Moro em Piracaia, bairro Centro": `resolve_municipality` desfaz
   "Piracaia" para o código TSE, `search_polling_places` lista os 10 locais do município
   filtrados por bairro, com contagem de seções e eleitores (§2.2).
8. **Candidato por número.** "Quem é o 45 para governador do Acre?": (AC, governador, 45) é
   único entre candidatos na urna; devolve a ficha com vice (mesmo número, cargo
   `vice_governador`) e nunca CPF, título, nascimento ou e-mail.
9. **Presidente.** "Candidatos a presidente": `uf = BR`, 14 candidatos e 14 vices em chapa.
10. **Indeferido na urna.** Candidato com `adjudication_status = "INDEFERIDO EM PRAZO RECURSAL
    OU COM RECURSO"` e `on_ballot = true`: listado, com a situação visível; o filtro padrão
    `on_ballot_only` não o esconde.
11. **Dado envelhecido.** Refresh parado há 60 horas: a resposta sai normalmente, com
    `source.generated_at`, `stale = true` e o aviso de que o dado tem mais de 48 horas.
12. **Sem eleição corrente ou índice de outra eleição.** Entre o último turno de uma eleição
    e a entrada da próxima no YAML (de 2026-10-26 em diante), ou quando qualquer dataset do
    índice vem do arquivo mensal `ATUAL` mesmo com uma eleição futura já no YAML: `election`
    da resposta é nulo, pela regra da seção 3.4 de `codebase-design.md`, única dona dela;
    `find_polling_place` e `search_polling_places` sem `round` respondem o maior turno
    presente no índice, sem aviso (turno 2 enquanto o índice de 2026 tiver os dois turnos);
    `source.dataset` identifica o arquivo de origem.
13. **Pergunta sobre o cadastro.** "Meu título está regular?" ou "qual é a minha seção, meu
    nome é X": nenhuma tool cobre; a descrição das tools e a orientação em `not_found` mandam
    o eleitor ao e-Título.
14. **Candidatos depois do 1º turno.** Em 2026-10-10 o TSE já publicou linhas com
    `NR_TURNO = 2` só para presidente e para governador nas UFs com 2º turno. "Candidatos a
    deputado federal em SP" sem turno responde o 1º turno, sem aviso e com a lista completa;
    "candidatos a presidente" responde o 2º turno; a ficha de um senador por `sq_candidato`
    responde a candidatura do 1º turno; `round = 2` para um cargo sem 2º turno responde o 1º
    turno com aviso, nunca lista vazia nem `not_found`. A ficha de um presidente eliminado no
    1º turno (linha só com `NR_TURNO = 1`, enquanto presidente tem turno 2 no índice) responde
    o 1º turno sem aviso quando não há `round`, e com `round = 2` responde a mesma ficha com o
    aviso "Este candidato não disputa o 2º turno; esta é a ficha do 1º turno.", nunca
    `not_found`; o mesmo vale para `get_candidate("BR", "presidente", 13)` com o 13 eliminado.

## 7. Suposições a validar na primeira ingestão

As suposições abaixo foram examinadas na primeira ingestão. Quando testáveis por uma regra
do pipeline, viram validações que bloqueiam a publicação do índice.

- Identidade de PollingPlace como (`uf`, `zone`, `number`), com nome e endereço constantes
  dentro da chave. **Refutada na primeira ingestão (2026-09-24):** a chave inclui o município
  (3.3).
- Seção principal de uma agregada sempre no mesmo local da agregada. **Refutada na primeira
  ingestão (2026-09-24):** a validação agora exige só que a principal exista e seja principal,
  e a resposta usa o local dela (3.4).
- Semântica de `DS_SITU_LOCAL_VOTACAO = BLOQUEADO` em relação a `*_ORIGINAL`:
  **não confirmada na primeira ingestão (2026-09-24).** Há linhas `BLOQUEADO` sem mudança de
  local e mudanças sem `BLOQUEADO`; o campo varia entre seções do mesmo local (3.3).
- Textos exatos de `DS_CARGO` para os dez cargos, além de `"DEPUTADO FEDERAL"`. **Confirmados
  na primeira ingestão (2026-09-24):** os dez textos do arquivo real já estavam no mapeamento,
  inclusive `1º SUPLENTE` e `2º SUPLENTE`.
- Derivação da chapa por (`round`, `uf`, `number`) com exatamente um titular por chapa.
  **Vale na primeira ingestão (2026-09-24)** depois de tirar da urna as candidaturas
  substituídas (3.5).
- Identidade de Candidate como (`sq_candidato`, `round`): a chave é única no arquivo principal,
  e o mesmo `SQ_CANDIDATO` pode aparecer nos dois turnos quando o 2º turno for publicado. O
  complementar traz `NR_TURNO`? Se sim, o join é por (`SQ_CANDIDATO`, `NR_TURNO`); se não, o
  complementar é deduplicado por `SQ_CANDIDATO` antes do join, e a validação falha se houver
  mais de uma linha por `SQ_CANDIDATO` nele.
- Linhas com `NR_TURNO = 2` restritas a `presidente`, `vice_presidente`, `governador` e
  `vice_governador`. Chapa completa por UF: há `vice_governador` com `NR_TURNO = 2` numa UF
  se, e somente se, há `governador` com `NR_TURNO = 2` nela; o mesmo entre `presidente` e
  `vice_presidente`. Cada (`uf`, `governador`) com 2º turno tem exatamente dois titulares
  `on_ballot`, e (`BR`, `presidente`) idem. É a premissa da regra de turno padrão (cenário 14
  e seção 3.4 de `codebase-design.md`); se o TSE publicar 2º turno para outro cargo, a
  validação falha alto e a regra é revista, em vez de responder lista vazia.
- Municípios ausentes do crosswalk restritos a `uf = ZZ`.
- `DT_ELEICAO` de cada turno presente igual à data do turno de mesmo número na eleição do
  `elections.yaml` de mesmo ano, só para os arquivos de eleição; o arquivo mensal `ATUAL`
  pula este portão, e o manifesto grava `election_year` e `election_dates` nulos sempre que
  qualquer dataset do índice vier dele.
- Uma eleição por ano no `elections.yaml`: validação de carga em `elections.py`, para que
  "a eleição do YAML de mesmo ano" seja sempre uma só.
- Cabeçalho de cada CSV igual ao esperado: o TSE muda nomes de colunas entre eleições (§5.2), e
  a ingestão deve falhar alto, não adivinhar.
