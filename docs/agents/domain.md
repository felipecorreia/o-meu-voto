# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the
codebase. Layout: **single-context**.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root: the ubiquitous language. English identifiers are the
  canonical names in code and responses; the PT-BR term in parentheses is what the voter and
  the TSE use. Each entry lists terms to _avoid_.
- **`docs/adr/`**: read the ADRs that touch the area you're about to work in
  (`docs/adr/README.md` is the table of contents).
- **`docs/domain-model.md`** (entities, invariants, CSV column mapping, LGPD discards,
  scenarios) and **`docs/codebase-design.md`** (module boundaries, the `core` interface, the
  six tool contracts, test strategy). Section 3.4 of `codebase-design.md` is the single owner
  of the round-resolution rule.
- **`wiki/index.md`** and the top entry of **`wiki/log.md`**: the compiled entry point and the
  current state, including decisions still open with the captain. The wiki is private and absent
  from the public mirror; skip it when it is missing.

## File structure

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── README.md
│   ├── 0001-embedded-duckdb-index.md
│   └── ...
├── docs/domain-model.md
├── docs/codebase-design.md
├── docs/agents/            ← this folder: skill configuration
├── wiki/                   ← compiled index and session log (private, may be missing)
└── src/br_elections_mcp/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis,
a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary
explicitly avoids. Identifiers stay in English; see `AGENTS.md` for the prose-language
convention.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing
language the project doesn't use (reconsider) or there's a real gap (note it for
`/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently
overriding:

> _Contradicts ADR-0001 (embedded DuckDB index), but worth reopening because…_
