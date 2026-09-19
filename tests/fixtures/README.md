# Test fixtures

Hand-written CSV files in the format the TSE distributes: `;` separator, every field
quoted, ISO-8859-1 encoding, headers exactly as named in `docs/domain-model.md` and
`src/br_elections_mcp/index_schema.py`. Nothing here was downloaded.

## `acre/`

A slice of Acre for the "where do I vote" tracer bullet, round 1 only (as the TSE
published it in 2026-09).

- `eleitorado_local_votacao_2026_AC.csv`: six sections. Zone 9, section 422 (Rio Branco,
  IEPTEC, voters, coordinates and CEP) reproduces the values the scout verified and
  `docs/codebase-design.md` 8.1 shows; every other row (section numbers, the other places,
  addresses, phone, voter counts, the moved place) is invented to exercise one scenario each:
  - 9/422 and 9/423: two main sections at the same place, one accessible and one not
    (section counts on the place: 3 sections, 2 accessible).
  - 9/424: aggregated section, votes at 422, same place (domain-model scenario 2).
  - 9/100: place changed (`NR_LOCAL_VOTACAO_ORIGINAL` differs), previous place filled
    (scenario 3).
  - 1/7 and 1/8 in Cruzeiro do Sul: a place with no coordinates (`-1`) and status
    `BLOQUEADO`, reported as it comes.
- `municipio_tse_ibge.csv`: the two municipalities above. The IBGE codes are the real ones;
  the TSE code of Rio Branco (`01392`) is the one in the design document, the rest of the
  crosswalk columns are illustrative.

The vocabulary of `DS_TIPO_SECAO_AGREGADA`, `DS_SITU_SECAO_ACESSIBILIDADE` and
`DS_SITU_LOCAL_VOTACAO` is a plausible guess; the `build` stage derives the section kind from
`NR_SECAO_PRINCIPAL` and fails loudly on an accessibility or status text it cannot map, so the
first real ingestion fixes the exact texts (domain-model section 7).

## `acre_lgpd/`

The same six rows with the five forbidden personal-data columns of ADR 0004 appended
(`NR_CPF_CANDIDATO`, `NR_TITULO_ELEITORAL_CANDIDATO`, `DT_NASCIMENTO`, `SG_UF_NASCIMENTO`,
`DS_EMAIL`), with placeholder values. The LGPD contract test builds an index from it and
fails if any of those columns reaches the index or an answer.
