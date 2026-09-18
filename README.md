# br-elections-mcp

MCP server and REST API over the open data of the Tribunal Superior Eleitoral (TSE), the
Brazilian electoral court. It answers the questions a voter asks before election day, for any
LLM connected through MCP and for a static web page, without touching any personal data.

## What it answers

- **Where do I vote?** The state, zone and section printed on the voter's title become the
  polling place address, with warnings when the place changed or the section votes at another one.
- **Polling places by city and neighborhood**, for voters who do not know their section.
- **Candidates** by office, name or ballot number: ballot name, party, federation, coalition,
  status, occupation and photo. Never CPF, voter title, birth date or e-mail.
- **Election date and voting hours**, from the official electoral calendar.

## What it never answers

Anything that depends on the individual voter registration: zone and section from a name or
CPF, the status of a voter's title, justifications or debts. Those questions are redirected to
the official e-Titulo app and TSE self-service.

## Status

Design phase. There is no server or pipeline code yet. Start with:

- [`CONTEXT.md`](CONTEXT.md) - the glossary of the domain.
- [`docs/domain-model.md`](docs/domain-model.md) - entities, invariants and the mapping from
  TSE CSV columns, including the columns discarded for privacy (LGPD).
- [`docs/codebase-design.md`](docs/codebase-design.md) - module boundaries and the contracts of
  the six tools.
- [`docs/adr/`](docs/adr/) - architecture decision records.
- [`data/elections.yaml`](data/elections.yaml) - the hand-curated electoral calendar.

## Development

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run ruff check .
uv run pytest
```

## Data source and attribution

Data: Tribunal Superior Eleitoral - Portal de Dados Abertos (CC-BY),
<https://dadosabertos.tse.jus.br>. Every response carries the dataset, file and generation
timestamp it came from.

## License

MIT. See [`LICENSE`](LICENSE).
