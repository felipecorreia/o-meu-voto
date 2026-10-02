# Start here

O meu voto answers a Brazilian voter's questions from the TSE open data, through an MCP server,
a REST API and a web page. Read the documents in this order: use the service first, then look
up the reference, then the concepts and guides, and last the design records behind them. The
project overview is the [README](../README.md).

## 1. Quickstart

- [README: Try it in 30 seconds](../README.md#try-it-in-30-seconds): connect an AI assistant
  and ask a first question.
- [`api.md`](api.md): call the service over MCP or REST, with the tools, `curl` examples, the
  answer envelope and the error codes.
- [`local-run.md`](local-run.md): run the server on localhost from the test fixtures or real
  TSE files, and connect Claude Desktop to it.

## 2. Reference

- [OpenAPI](https://omeuvoto.pages.dev/api/v1/openapi.json) and the
  [interactive page](https://omeuvoto.pages.dev/api/v1/docs): every REST route, parameter and
  response field, generated from the code.
- MCP tool schemas: the server lists each tool with its `inputSchema` and `outputSchema`
  (`tools/list`); [`api.md`](api.md#tools-and-routes) maps them to the REST routes.

## 3. Concepts and guides

- [`architecture.md`](architecture.md): the pipeline, the service, the edge and a one-line
  summary of every decision.
- [`how-it-was-built.md`](how-it-was-built.md): how AI coding agents built it, one decision end
  to end and what went wrong.
- [`pipeline.md`](pipeline.md): the refresh pipeline, the index bucket and the photo mirror,
  for whoever operates it.
- [`../ops/README.md`](../ops/README.md): the Cloud Run service, budget, monitoring and the
  scheduled refresh.
- [`../web-next/README.md`](../web-next/README.md): build, run and deploy the web page and its
  edge.
- [`tse/README.md`](tse/README.md): the TSE's own dataset documentation (`leiame.pdf`) the
  pipeline read.

## 4. Design records

In Portuguese, the language of the domain; [`architecture.md`](architecture.md#decisions)
summarizes the decisions in English.

- [`../CONTEXT.md`](../CONTEXT.md): the glossary, with the terms to use and to avoid.
- [`domain-model.md`](domain-model.md): entities, invariants and the TSE column mapping.
- [`codebase-design.md`](codebase-design.md): module boundaries and the tool contracts.
- [`adr/README.md`](adr/README.md): the architecture decision records, one per decision.

## For coding agents

How the agent skills in this repository use the issue tracker and the domain docs:
[`agents/issue-tracker.md`](agents/issue-tracker.md),
[`agents/triage-labels.md`](agents/triage-labels.md) and [`agents/domain.md`](agents/domain.md).
