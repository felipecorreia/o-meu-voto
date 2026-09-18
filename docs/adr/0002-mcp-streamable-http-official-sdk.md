# 0002. MCP por Streamable HTTP com o SDK oficial `mcp`, mais REST sobre o mesmo core

Status: aceito, 2026-09-17.

## Contexto

O MCP remoto é o artefato principal, mas o alcance real vem de quem não tem MCP: uma página
estática precisa da mesma lógica por HTTP comum (relatório do scout, §3.2). O transporte
Streamable HTTP substituiu o HTTP+SSE na especificação MCP 2025-06-18; Perplexity, Gemini CLI
e Copilot Studio o aceitam, e Gemini app e Copilot Studio o exigem (§3, §5.2). Havia duas bibliotecas Python: o SDK oficial `mcp` (2.2.0 no PyPI em
2026-09-17) e `fastmcp` (4.0.5), com mais mágica.

## Decisão

Um serviço Python expõe o MCP em `/mcp` por Streamable HTTP, sem estado por sessão, usando o
SDK oficial `mcp`, e a mesma lógica em `/api/v1` como REST JSON. Os dois são adaptadores finos
sobre o `core`; as tools são somente leitura, com `outputSchema` e `structuredContent`
gerados dos mesmos modelos pydantic que geram o OpenAPI da REST. O SDK oficial foi escolhido
porque deixa o protocolo visível, o que importa num projeto de portfólio, e porque acompanha
as mudanças de versão da especificação.

## Consequências

- Clientes que só falam o SSE legado ficam de fora; não há plano de mantê-lo.
- Uma mudança de contrato de tool acontece num único arquivo de modelos e se propaga para
  MCP e REST ao mesmo tempo.
- Distribuição local por stdio (`uvx`) fica possível sem mudança no `core`, porque o
  adaptador MCP não depende do transporte; não faz parte da primeira entrega.
- O limite por IP e a leitura de `CF-Connecting-IP` valem para os dois adaptadores, na raiz
  de composição, e não dentro de nenhum deles.
