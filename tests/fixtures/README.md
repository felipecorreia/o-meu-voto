# Test fixtures

Hand-written CSV files in the format the TSE distributes: `;` separator, every field
quoted, ISO-8859-1 encoding, headers exactly as named in `docs/domain-model.md` and
`src/br_elections_mcp/index_schema.py`. Nothing here was downloaded.

## `acre/`

A slice of Acre for the "where do I vote" tracer bullet and the "places by city or
neighborhood" search, round 1 only (as the TSE published it in 2026-09). The file keeps the
`_AC` name of the per-UF ZIP entry but also carries two rows of `ZZ`, so one fixture covers
the electorate abroad without a second file.

- `eleitorado_local_votacao_2026_AC.csv`: ten sections. Zone 9, section 422 (Rio Branco,
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
  - 9/150 in Rio Branco: a second place in the neighborhood `CENTRO`, next to 1035, so the
    neighborhood filter lists two of the three places (domain-model scenario 7).
  - 1/20 in Cruzeiro do Sul: a place with coordinates, so `near` puts the place without
    coordinates (1015) last.
  - ZZ 1/1 and 1/2: a municipality abroad (`COLÔNIA`, code `30015`, not in the crosswalk)
    whose place is the consulate in Cologne, Germany (scenario 4); two sections, one
    accessible. The postal code is a German one, kept as the TSE would print it.
- `municipio_tse_ibge.csv`: Rio Branco and Cruzeiro do Sul, plus Porto Acre and Porto Walter
  without any section, so "porto" is ambiguous within AC and an exact name can resolve to a
  municipality with no places. The IBGE codes are the real ones; the TSE code of Rio Branco
  (`01392`) is the one in the design document, the other TSE codes and the rest of the
  crosswalk columns are illustrative.

The vocabulary of `DS_TIPO_SECAO_AGREGADA`, `DS_SITU_SECAO_ACESSIBILIDADE` and
`DS_SITU_LOCAL_VOTACAO` is a plausible guess; the `build` stage derives the section kind from
`NR_SECAO_PRINCIPAL` and fails loudly on an accessibility or status text it cannot map, so the
first real ingestion fixes the exact texts (domain-model section 7).

### Candidates (`consulta_cand_2026_BRASIL.csv` and companions)

The candidate slice of the same election, round 1 only, in the three files the TSE ships
under `candidatos-2026`. Every person, party composition, coalition, federation and social
link is invented; only the party numbers and acronyms and the shape of the TSE vocabulary
(`#NULO`, `-1`, `PARTIDO ISOLADO`, `DEFERIDO`, `INDEFERIDO EM PRAZO RECURSAL OU COM
RECURSO`, `S`/`N`) follow the `leiame.pdf` in `docs/tse/`. The file is named `BRASIL`
because president rows carry `SG_UF = BR` and production ingests the national file.

- `consulta_cand_2026_BRASIL.csv`, 16 rows, one per candidacy, with the full TSE header
  including the five forbidden columns of ADR 0004 filled with placeholders (CPF
  `00000000000`, title `000000000000`, `01/01/1970`, `AC`, `NÃO DIVULGÁVEL`), so the LGPD
  contract test runs over the real seam:
  - AC governor 45 (coalition "ACRE PARA TODOS") with vice 45; governor 13 (federation
    "BRASIL DA ESPERANÇA", `NM_COLIGACAO = #NULO`) with vice 13, both `INDEFERIDO ...` and
    on the ballot (domain-model scenario 10); governor 22 (`PARTIDO ISOLADO`, `RENÚNCIA`,
    off the ballot).
  - AC senator 456 with `1º SUPLENTE` and `2º SUPLENTE`; federal deputies 4512 and 1313;
    state deputies 45123 (`JOANA D'ARC`, an apostrophe in the ballot name) and 22222.
  - Presidents 13 and 45 with their vices, `SG_UF = BR` (scenario 9).
- `consulta_cand_complementar_2026_BRASIL.csv`: one row per `SQ_CANDIDATO`, full header,
  without `NR_TURNO` (as the 2026 `leiame.pdf` documents), so the build deduplicates by
  `SQ_CANDIDATO`; the tests derive a variant with `NR_TURNO` to cover the other join.
- `rede_social_candidato_2026_BRASIL.csv`: four links for three candidates.

The `DS_CARGO` texts other than `"DEPUTADO FEDERAL"` are the plausible spellings mapped in
`pipeline/build.py` (`OFFICE_BY_DS_CARGO`); the build fails loudly on any other text, so the
first real ingestion fixes them (domain-model section 7).

## `acre_lgpd/`

The same six rows with the five forbidden personal-data columns of ADR 0004 appended
(`NR_CPF_CANDIDATO`, `NR_TITULO_ELEITORAL_CANDIDATO`, `DT_NASCIMENTO`, `SG_UF_NASCIMENTO`,
`DS_EMAIL`), with placeholder values. The LGPD contract test builds an index from it and
fails if any of those columns reaches the index or an answer.
