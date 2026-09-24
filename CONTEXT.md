# br-elections-mcp

Contexto único: as perguntas que um eleitor faz antes do dia da votação, respondidas a partir
dos dados abertos do TSE, sem nenhum dado do cadastro eleitoral individual. O identificador em
inglês é o nome canônico no código e nas respostas; o termo em PT-BR entre parênteses é o que o
eleitor e o TSE usam nos textos.

## Language

### Eleição

**Election** (eleição):
Um pleito com um ou mais turnos, definido pelo calendário eleitoral do TSE. Em 2026, as
Eleições Gerais.
_Avoid_: pleito, "eleições" no plural para um único pleito

**Round** (turno):
Um dia de votação de uma eleição. O segundo turno só ocorre onde houver, isto é, onde nenhum
candidato a presidente ou governador alcançou maioria absoluta no primeiro.
_Avoid_: etapa, fase, rodada

**Voting hours** (horário de votação):
A janela em que as seções recebem votos, a mesma em todo o país, no horário de Brasília.
_Avoid_: expediente, funcionamento

**Office** (cargo):
O posto eletivo de uma candidatura. Um **ballot office** (cargo de urna) é o que o eleitor
escolhe na urna; vice e suplentes têm cargo de chapa.
_Avoid_: posição, vaga (vaga é a quantidade de cadeiras, não o cargo)

**Ticket** (chapa):
O titular de um cargo majoritário e quem o acompanha, vice ou suplentes, registrados com o
mesmo número do titular.
_Avoid_: dobradinha

**Calendar source** (fonte do calendário):
A resolução do TSE de onde datas e horário foram copiados à mão, com a data em que foram
conferidos.

### Onde votar

**UF** (unidade da federação):
A sigla de dois caracteres que particiona todo o cadastro: 26 estados, DF, ZZ para o exterior e
BR apenas para candidaturas nacionais.
_Avoid_: estado (DF e ZZ não são estados)

**Electoral zone** (zona eleitoral):
A subdivisão administrativa da Justiça Eleitoral dentro de uma UF, identificada por número.
Pode abranger mais de um município.
_Avoid_: zona de votação, cartório (o cartório é o órgão da zona, não a zona)

**Polling section** (seção eleitoral):
A menor unidade de votação: um número dentro de uma zona, ligado a exatamente um local de
votação por turno. É o que está impresso no título e no e-Título.
_Avoid_: seção de votação, sala, mesa

**Main section** (seção principal) e **Aggregated section** (seção agregada):
Uma seção agregada não recebe votos por si: seus eleitores votam na seção principal indicada,
no local dela, que em geral é o mesmo da agregada, mas nem sempre (`docs/domain-model.md`, 3.4).
_Avoid_: seção fundida, seção anexada

**Polling place** (local de votação):
O prédio onde as seções funcionam: número, nome, endereço, bairro, CEP, telefone, coordenadas e
situação.
_Avoid_: colégio eleitoral, escola, posto, ponto de votação

**Previous polling place** (local anterior):
O local que a seção ocupava antes de ser transferida. Quando existe, o eleitor recebe o aviso
de que o local mudou.
_Avoid_: local original (é o nome da coluna do TSE, não o termo do eleitor)

**Municipality** (município):
A cidade do local de votação, identificada pelo código do TSE e, quando existe, pelo código do
IBGE. Cidades no exterior são municípios sem código IBGE.
_Avoid_: cidade, localidade

**Accessibility** (acessibilidade):
A indicação do TSE de que a seção funciona em espaço acessível.

### Candidatos

**Candidate** (candidato):
Um pedido de registro de candidatura numa eleição, identificado pelo número sequencial do TSE
(`sq_candidato`) e pelo turno, com cargo, número de urna e nome de urna. O mesmo
`sq_candidato` aparece nos dois turnos quando a candidatura vai ao segundo.
_Avoid_: político, concorrente, postulante

**Ballot number** (número):
O número que o eleitor digita na urna. Vice e suplentes repetem o número do titular da chapa.
_Avoid_: código, legenda (legenda é o partido)

**Ballot name** (nome de urna):
O nome que aparece na urna, escolhido pelo candidato. Diferente do nome civil e do nome
social.
_Avoid_: apelido, nome fantasia

**Party** (partido), **Federation** (federação) e **Coalition** (coligação):
O partido registra a candidatura; a federação é a união de partidos que atua como um só; a
coligação é a aliança apenas para a eleição majoritária. Um candidato pode ter federação e
coligação ao mesmo tempo, uma delas ou nenhuma.
_Avoid_: aliança, frente, legenda (para federação ou coligação)

**Adjudication status** (situação de julgamento):
O estado do pedido de registro na Justiça Eleitoral: deferido, indeferido, renúncia, pendente.
_Avoid_: situação da candidatura (a coluna com esse nome vem vazia no dataset)

**On ballot** (na urna):
Indica se o candidato está carregado na urna eletrônica. É informação independente da
situação de julgamento.

**Photo** (foto):
A imagem oficial de campanha publicada pelo TSE, espelhada pelo serviço.

**Social links** (redes sociais):
As URLs de redes sociais que o candidato declarou ao TSE.

### Fonte e frescor

**Dataset** (conjunto de dados):
Um recurso do Portal de Dados Abertos do TSE, licenciado CC-BY. Toda resposta cita o dataset.

**Generated at** (data de geração):
O instante em que o TSE gerou o arquivo, gravado dentro do próprio CSV. É a idade real do
dado.
_Avoid_: última atualização (é a data do catálogo, que não acompanha o arquivo)

**Source** (fonte):
O rodapé de toda resposta: dataset, arquivo, data de geração, licença e atribuição ao TSE.

**Stale data** (dado envelhecido):
Dado cuja geração tem mais de 48 horas. Continua sendo servido, com a data e um aviso ao
eleitor.
_Avoid_: dado expirado, dado inválido

### Fora do domínio

**Voter registration** (cadastro eleitoral):
O registro individual de cada eleitor no TSE: título, zona e seção por nome ou CPF, situação,
débitos. Nada disso entra neste serviço.

**e-Título**:
O aplicativo oficial do TSE que mostra ao eleitor a própria zona e seção. É o destino de toda
pergunta que depende do cadastro eleitoral.

**Results** (apuração):
Contagem de votos. Fora do escopo por decisão.
