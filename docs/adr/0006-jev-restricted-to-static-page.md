# 0006. Jev restrito à caixa de linguagem natural da página estática

Status: aceito, 2026-09-17.

## Contexto

A página estática deve aceitar uma pergunta em linguagem natural ("onde voto, zona 9 seção
422 no Acre?") além dos formulários, e a decisão de produto é fazer isso com o Jev, fora do
caminho crítico. O Jev é o modelo System One da TypeSafe: recebe um estado e perguntas
tipadas (Choice, Score, Noul) e devolve respostas estruturadas com probabilidade calibrada e
confiança; não gera texto. Os clientes MCP já trazem o próprio LLM, então o serviço não
precisa de nenhum modelo para responder; o `core` é determinístico e testado sem rede. A
chave de API do Jev não pode ficar num JavaScript público.

## Decisão

O Jev é adaptador da página e de nada mais. Uma Pages Function no Cloudflare guarda a chave
como segredo, aplica limite por IP e faz ao Jev uma única pergunta do tipo Choice: a intenção
do texto entre `onde_voto`, `locais_da_cidade`, `candidatos`, `data_e_horario`,
`cadastro_individual` e `fora_do_escopo`. JavaScript determinístico na página extrai UF,
zona, seção, município, bairro, cargo, nome ou número por expressões regulares, preenche o
formulário da intenção e chama a REST. Confiança baixa, intenção fora do escopo, erro ou
indisponibilidade do Jev caem nos formulários, que estão sempre na tela. O `core`, os
adaptadores MCP e REST, o pipeline e o `pyproject.toml` não conhecem o Jev.

## Consequências

- A página funciona inteira sem o Jev; ele só encurta o caminho de quem chega com uma frase.
- O custo do Jev é limitado pelo tráfego da página e pelo limite da Pages Function, e não
  pelo tráfego do MCP.
- Os rótulos de intenção são preocupação da página e mudam sem tocar no serviço.
- Levar o Jev para dentro do serviço, por exemplo para desambiguar município, exige um novo
  ADR que supere este.
