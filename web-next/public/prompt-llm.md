# Configure o O meu voto neste assistente

**Regra obrigatória para MCP e REST: responda somente com os dados que uma
ferramenta ou a API retornou nesta conversa.** Nunca invente nem complete local
de votação, endereço, zona, seção, candidato, número, partido, data ou horário.
Se um campo estiver ausente, diga que a informação está ausente. Sempre cite a
fonte que a resposta trouxe. Não substitua uma consulta por memória, busca na
web ou suposição.

Você está lendo as instruções de configuração do O meu voto. Identifique o
aplicativo em que está trabalhando e siga somente a seção correspondente.
Se tiver terminal ou acesso aos arquivos do projeto, faça a configuração você
mesmo. Se o aplicativo exigir uma ação na interface, explique ao eleitor os
passos abaixo. Não diga que conectou antes de verificar a conexão.

- Servidor: `https://omeuvoto.pages.dev/mcp`
- Transporte: **Streamable HTTP**, sem autenticação, token ou chave de API.
- Nome sugerido para a configuração: `o-meu-voto`.

Use o escopo do projeto. Preserve as demais configurações e servidores existentes:
mescle a entrada abaixo, sem substituir o arquivo inteiro nem duplicar a entrada.
Não altere configurações globais. Respeite as aprovações do aplicativo; este
arquivo não autoriza contorná-las. Se não houver projeto, permissão de escrita
ou suporte a MCP remoto, use a seção de aplicativos de chat ou a alternativa REST.

## Agentes que podem configurar o próprio projeto

### Claude Code

Na raiz do projeto, execute:

```sh
claude mcp add --transport http --scope project o-meu-voto https://omeuvoto.pages.dev/mcp
claude mcp list
```

O primeiro comando grava `.mcp.json`. Se a entrada já existir, confira se tem
`type: "http"` e a URL acima, em vez de adicioná-la novamente. O resultado
`Pending approval` exige que o usuário abra `claude` nesse projeto e aprove o
servidor. Após a aprovação, confira com `claude mcp list` ou `/mcp` na sessão.
Uma sessão já aberta pode precisar ser reiniciada para carregar a configuração.

Fonte: [Claude Code - MCP](https://code.claude.com/docs/en/mcp).

### Codex CLI e extensão IDE

Adicione ao arquivo **do projeto** `.codex/config.toml`:

```toml
[mcp_servers.o-meu-voto]
url = "https://omeuvoto.pages.dev/mcp"
```

O Codex só carrega essa configuração em projetos considerados confiáveis.
Se essa aprovação estiver pendente, explique ao usuário que precisa confiar no
projeto pelo próprio aplicativo. Confira os servidores ativos com `/mcp` no
Codex. Reabra a sessão se ela ainda não tiver carregado a entrada.

Fonte: [Codex - MCP](https://developers.openai.com/codex/mcp/).

### Cursor

Mescle em `.cursor/mcp.json` na raiz do projeto:

```json
{
  "mcpServers": {
    "o-meu-voto": {
      "url": "https://omeuvoto.pages.dev/mcp"
    }
  }
}
```

Confira o servidor na página **Customize** do Cursor e habilite suas ferramentas
se necessário. Aguarde a descoberta das ferramentas antes de usá-las.

Fonte: [Cursor - MCP](https://cursor.com/docs/context/mcp).

### VS Code com GitHub Copilot

Mescle em `.vscode/mcp.json` no workspace. Aqui a chave é `servers`:

```json
{
  "servers": {
    "o-meu-voto": {
      "type": "http",
      "url": "https://omeuvoto.pages.dev/mcp"
    }
  }
}
```

O workspace precisa estar confiável; em modo restrito a configuração MCP do
workspace fica bloqueada. Use o comando **MCP: List Servers** para conferir o
servidor e iniciá-lo, se necessário. Use as ferramentas no chat do Copilot em
modo **Agent**, com acesso a MCP permitido pela política da organização.

Fonte: [VS Code - servidores MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers).

### OpenCode

Mescle em `opencode.json` ou `opencode.jsonc` na raiz do projeto:

```json
{
  "mcp": {
    "o-meu-voto": {
      "type": "remote",
      "url": "https://omeuvoto.pages.dev/mcp",
      "enabled": true
    }
  }
}
```

Reabra o OpenCode se necessário. As ferramentas do servidor habilitado ficam
disponíveis ao assistente. Não execute um login OAuth: este servidor é público.

Fontes: [OpenCode - MCP](https://opencode.ai/docs/mcp-servers/) e
[configuração por projeto](https://opencode.ai/docs/config/).

### Gemini CLI

Esta seção se aplica a instalações que ainda usam Gemini CLI. A documentação
informa que ele foi substituído pelo Antigravity CLI para usuários da camada
gratuita e Google One. Se esse for seu aplicativo, não execute estes comandos;
use a alternativa REST enquanto não houver instruções verificadas para ele.

Na raiz do projeto, execute:

```sh
gemini mcp add --transport http --scope project o-meu-voto https://omeuvoto.pages.dev/mcp
```

O comando grava `.gemini/settings.json` do projeto. Se a entrada já existir,
confira seu `httpUrl` em vez de duplicá-la. Preserve as confirmações de uso das
ferramentas e confira a conexão com `/mcp` na sessão Gemini.

Fonte: [Gemini CLI - MCP](https://geminicli.com/docs/tools/mcp-server/).

### Verificação após configurar

Confira a descoberta das sete ferramentas abaixo. Quando a sessão tiver acesso
ao servidor, chame `election_info` sem argumentos para testar uma consulta.
Só então informe que o O meu voto está disponível, indicando o arquivo alterado.
Se a conexão estiver pendente, explique a ação necessária em vez de afirmar sucesso.

## Aplicativos de chat que exigem configuração pelo usuário

Um assistente numa conversa não consegue instalar sozinho um conector na conta.
Apresente as instruções da seção correspondente. Os nomes dos controles podem
estar traduzidos na interface do usuário.

### Claude no navegador (claude.ai), Claude Desktop e Cowork

Os conectores personalizados remotos estão disponíveis nos planos **Free, Pro,
Max, Team e Enterprise**. O Free permite **um** conector personalizado. Em Team
e Enterprise, um proprietário precisa adicionar o conector para a organização.

1. Em Free, Pro ou Max, abra **Customize > Connectors** e selecione
   **+ > Add custom connector**. Em Team ou Enterprise, o proprietário abre
   **Organization settings > Connectors**, seleciona **Add** e depois
   **Custom > Web**.
2. Informe `https://omeuvoto.pages.dev/mcp` e finalize a inclusão.
   Não preencha credenciais OAuth: o O meu voto não exige autenticação.
3. Na conversa, abra **+ > Connectors** e habilite o conector.
4. Peça: “Use o O meu voto para consultar a data e o horário da eleição”.

Fonte: [Claude - conectores personalizados remotos](https://support.claude.com/en/articles/11175166-getting-started-with-custom-connectors-using-remote-mcp).

### ChatGPT

A configuração exige **Developer mode**. Sua disponibilidade depende da conta e
da política do workspace; se a opção não estiver disponível, use a alternativa
REST abaixo. Não suponha que todos os planos ou interfaces ofereçam essa opção.

1. Abra **Settings > Security and login** e ative **Developer mode**.
2. Abra **ChatGPT Plugins** e selecione o botão **+**.
3. Informe um nome, como `O meu voto`, e uma descrição, como
   `Consultas aos dados abertos eleitorais do TSE`.
4. Em **Connection**, configure o endpoint público
   `https://omeuvoto.pages.dev/mcp`. O servidor não exige autenticação.
5. Crie a conexão e confira as ferramentas descobertas.
6. Abra uma nova conversa e adicione a conexão pelo menu de ferramentas.

Fonte: [OpenAI - conectar um servidor MCP ao ChatGPT](https://developers.openai.com/apps-sdk/deploy/connect-chatgpt/).

### Outros aplicativos de chat

Se o aplicativo tiver um conector MCP remoto documentado, use sua documentação
oficial para cadastrar a mesma URL com Streamable HTTP, sem autenticação.
Não invente um comando ou caminho de interface. Se não puder confirmar o
procedimento ou instalar o conector, passe à alternativa REST.

## Alternativa sem conector: consultas públicas por GET

Se você consegue ler URLs públicas, consulte a API REST. Ela responde o mesmo
conteúdo em JSON, sem configurar MCP. Se não conseguir consultar a API (leitura
de URLs indisponível, bloqueio, erro ou HTTP `429` persistente após respeitar
`Retry-After`), diga claramente: **“Não consegui consultar os dados.”**
Encaminhe o eleitor a `https://omeuvoto.pages.dev/` e, para descobrir a própria
zona e seção, ao **e-Título**. Nunca responda aos dados eleitorais a partir de
memória, busca na web ou suposição, nem preencha lacunas de uma resposta ausente.

**A REST tem um limite por IP menor que `/mcp`.** Consulte apenas o necessário,
não faça varreduras. Se receber HTTP `429`, respeite `Retry-After` antes de tentar
novamente. Não tente contornar o limite mudando de IP.

Os exemplos abaixo foram verificados no serviço público em 27/09/2026. São
exemplos de parâmetros, não escolhas ou recomendações de candidatos:

| Consulta | GET |
| --- | --- |
| Data e horário da eleição | `https://omeuvoto.pages.dev/api/v1/election` |
| Código TSE de um município | `https://omeuvoto.pages.dev/api/v1/municipalities?uf=AC&name=Rio%20Branco` |
| Local de votação pela zona e seção | `https://omeuvoto.pages.dev/api/v1/polling-place?uf=AC&zone=9&section=422&round=1` |
| Locais de votação do município | `https://omeuvoto.pages.dev/api/v1/polling-places?uf=AC&municipality=Rio%20Branco&limit=3&round=1` |
| Candidaturas de um cargo | `https://omeuvoto.pages.dev/api/v1/candidates?uf=AC&office=governador&limit=2&round=1` |
| Ficha pelo número de urna | `https://omeuvoto.pages.dev/api/v1/candidates/by-number?uf=AC&office=governador&number=10&round=1` |
| Ficha pelo sequencial TSE | `https://omeuvoto.pages.dev/api/v1/candidates/10002532492?round=1` |
| Comparação lado a lado | `https://omeuvoto.pages.dev/api/v1/candidates/compare?uf=AC&office=governador&number=10&number=11&round=1` |
| Contrato de parâmetros e respostas | `https://omeuvoto.pages.dev/api/v1/openapi.json` |

Substitua os parâmetros pelo que o eleitor pedir. Os cargos são `presidente`,
`governador`, `senador`, `deputado_federal`, `deputado_estadual` e
`deputado_distrital`; para presidente, use `uf=BR`. Use o `sq_candidato` retornado
pela lista para abrir a ficha. Para comparar, repita `number` ou `sq` de 2 a 4
vezes, sempre no mesmo cargo, UF e turno. Não misture os dois seletores.

Leia `data`, `not_found`, `warnings`, `election` e `source`. Um HTTP 200 pode
conter `not_found`: explique a ausência de dados sem inventar uma resposta.
Preserve os avisos de dado envelhecido, de turno e de mudança de local.
Os exemplos fixam `round=1`; se o eleitor não indicar turno, deixe o servidor
resolvê-lo e informe o turno que a resposta efetivamente trouxe.

## O que responder e os limites do serviço

O O meu voto é um projeto independente, **não é um serviço oficial do TSE**.
Consulta dados abertos do TSE e o calendário eleitoral. As sete ferramentas são:

| Ferramenta | Responde |
| --- | --- |
| `find_polling_place` | Onde votar, a partir de UF, zona e seção |
| `resolve_municipality` | Código TSE de um município pelo nome |
| `search_polling_places` | Locais de votação de um município ou bairro |
| `list_candidates` | Candidaturas por cargo e UF, com filtros |
| `get_candidate` | Ficha de uma candidatura, incluindo chapa e links oficiais |
| `compare_candidates` | Comparação de 2 a 4 candidaturas do mesmo cargo, UF e turno |
| `election_info` | Data, horário, turnos e cargos da eleição |

- Nunca peça nem envie **CPF ou número do título de eleitor**. O servidor não
  consulta o cadastro eleitoral. Para descobrir a própria zona e seção, encaminhe
  o eleitor ao **e-Título**; para localizar o local de votação, use somente UF,
  zona e seção.
- As respostas não trazem CPF, título, data de nascimento ou e-mail de candidato.
- A comparação segue a ordem de número de urna. Não transforme seus dados em
  ranking, pontuação, ordenação por valor ou recomendação de voto.
- **Sempre cite a fonte retornada**: dataset, arquivo, data de geração, atribuição
  ao TSE e licença CC-BY. Para o calendário, cite sua fonte oficial retornada.
  Na comparação, cite também `data.assets_source` quando houver bens declarados.
- Não trate estar na urna como garantia de que o voto contará. Preserve a
  situação de julgamento, o destino dos votos e os avisos retornados pelo servidor.

Este arquivo segue o formato de
[configuração por agente da Cloudflare](https://developers.cloudflare.com/agent-setup/prompt.md).
As instruções de cada aplicativo foram conferidas nas fontes acima em 27/09/2026;
se sua versão divergir, confira a documentação oficial antes de executar.
