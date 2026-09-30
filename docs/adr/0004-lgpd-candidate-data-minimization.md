# 0004. Tratamento LGPD dos dados de candidato: minimização na ingestão

Status: aceito, 2026-09-17. Emendado pelo ADR 0009 (2026-09-25). O ADR 0011 (2026-09-28)
registra que a exclusão de logs tentada para manter localização e seção do eleitor fora dos logs
do Cloud Run não funcionou e foi removida: essas entradas ainda ficam 30 dias no `_Default`
(`wiki/pendencias.md` item 9, aberto).

## Contexto

O CSV `consulta_cand_2026` traz CPF completo, número do título de eleitor e data de
nascimento de todos os 20.984 candidatos, embora o `leiame.pdf` do mesmo ZIP declare o CPF
não divulgável (Res. TSE 23.609/2019, art. 33, §2º, incluído pela Res. 23.729/2024). A API
REST do DivulgaCandContas também devolve CPF, nascimento e título no detalhe do candidato
(relatório do scout, §1.2 b, §1.4, §1.5). A licença dos datasets é CC-BY, com atribuição
obrigatória, e a Portaria TSE 93/2021 cita a LGPD expressamente. Nenhuma pergunta do eleitor
depende desses campos. Os `leiame.pdf` citados aqui (CC-BY) serão versionados em `docs/tse/`
pelo PR do pipeline, que já baixa os ZIPs que os contêm.

## Decisão

Minimização na ingestão, antes de qualquer gravação: o pipeline descarta
`NR_CPF_CANDIDATO`, `DS_EMAIL`, `DT_NASCIMENTO`, `SG_UF_NASCIMENTO` e
`NR_TITULO_ELEITORAL_CANDIDATO` por serem dados pessoais sem uso no produto. A lista é
exatamente essa, decidida pelo capitão no grilling de 2026-09-17; ela vive em
`index_schema.py`, e um teste falha se qualquer coluna dela existir no índice ou aparecer numa
resposta. Gênero, cor/raça, estado civil e grau de instrução (`DS_GENERO`, `DS_COR_RACA`,
`DS_ESTADO_CIVIL`, `DS_GRAU_INSTRUCAO`) ficam como o TSE publica, sem inferência nem
cruzamento, e aparecem só na ficha individual de `get_candidate`, nunca em `list_candidates`
nem em agregados; os códigos `CD_*` correspondentes são descartados por redundância com as
descrições. Os ZIPs brutos ficam num diretório temporário apagado ao fim do
run. Não há enriquecimento nem cruzamento com outras bases; fotos e redes sociais entram como o
TSE publica. Entradas do usuário não são persistidas e os logs não guardam IP completo. Toda
resposta carrega `source` com dataset, arquivo, data de geração e a atribuição ao TSE. O
DivulgaCandContas entra apenas como link para o humano abrir, nunca como fonte de dado.

## Consequências

- O serviço não responde idade nem data de nascimento de candidato, por construção. Gênero,
  cor/raça, estado civil e grau de instrução saem apenas na ficha individual, com o texto do
  TSE; o serviço não agrega, filtra nem ordena por esses campos.
- As fotos, espelhadas por decisão de produto (ADR 0005), são dado pessoal público sob
  custódia do projeto: o pipeline remove do R2 as que o TSE deixar de publicar, a cada
  refresh. O [ADR 0015](0015-publication-aware-photo-cleanup.md) fixa quando: depois do
  `publish`, 48 horas após nenhum índice servido referenciá-las.
- O repositório precisa de uma política de privacidade curta e de um canal de contato, ambos
  fora deste PR.
- Se o TSE passar a mascarar as colunas na fonte, nada muda no pipeline: o descarte é
  idempotente.
