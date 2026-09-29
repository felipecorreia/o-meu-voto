# Test fixtures

Hand-written CSV files in the format the TSE distributes: `;` separator, every field
quoted, ISO-8859-1 encoding, headers exactly as named in `docs/domain-model.md` and
`src/br_elections_mcp/index_schema.py`. Nothing here was downloaded.

## `acre/`

A slice of Acre for the "where do I vote" tracer bullet and the "places by city or
neighborhood" search, in the two-round shape of `docs/codebase-design.md` 3.3: every section
appears in round 1 (`DT_ELEICAO` 04/10/2026) and again, unchanged, in round 2 (25/10/2026).
The variant without round 2 at all is derived by `tests/conftest.py` (`without_round_2`,
fixture `acre_round_1_index_dir`) by dropping the `NR_TURNO = 2` rows, never stored here.
The file keeps the `_AC` name of the per-UF ZIP entry but also carries two rows of `ZZ`, so
one fixture covers the electorate abroad without a second file.

- `eleitorado_local_votacao_2026_AC.csv`: ten sections per round. Zone 9, section 422 (Rio Branco,
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

The vocabulary of `DS_SITU_SECAO_ACESSIBILIDADE` and `DS_SITU_LOCAL_VOTACAO` was a guess the
first real ingestion (2026-09-24) confirmed up to case (`Com acessibilidade`, `ATIVO`,
`BLOQUEADO`); `DS_TIPO_SECAO_AGREGADA` is `Principal`/`Agregada` in the real file, but the
`build` stage derives the section kind from `NR_SECAO_PRINCIPAL` and never reads it. Two shapes
of the real file that these rows do not carry are derived in `tests/conftest.py`
(`SHARED_PLACE_NUMBER`, `AGGREGATED_ELSEWHERE`, through `with_section_fields`); the second
also leaves place 1099 with no main section, so it is not a `polling_places` row.

### Candidates (`consulta_cand_2026_BRASIL.csv` and companions)

The candidate slice of the same election in the three files the TSE ships under
`candidatos-2026`, with the round-2 rows the round table needs (codebase-design 3.3 and 3.4):
presidents 45 and 22 with their vices have a row in round 1 and another in round 2, president
13 (eliminated in round 1) has a row in round 1 only, and every other office has round 1 only
(Acre decided its governor in round 1). Every person, party composition, coalition, federation and social
link is invented; only the party numbers and acronyms and the shape of the TSE vocabulary
(`#NULO`, `-1`, `PARTIDO ISOLADO`, `DEFERIDO`, `INDEFERIDO EM PRAZO RECURSAL OU COM
RECURSO`, `S`/`N`) follow the `leiame.pdf` in `docs/tse/`. The file is named `BRASIL`
because president rows carry `SG_UF = BR` and production ingests the national file.

- `consulta_cand_2026_BRASIL.csv`, 23 rows, one per candidacy and round, with the full TSE
  header including the five forbidden columns of ADR 0004 filled with placeholders (CPF
  `00000000000`, title `000000000000`, `01/01/1970`, `AC`, `NÃO DIVULGÁVEL`), so the LGPD
  contract test runs over the real seam:
  - AC governor 45 (coalition "ACRE PARA TODOS") with vice 45; governor 13 (federation
    "BRASIL DA ESPERANÇA", `NM_COLIGACAO = #NULO`) with vice 13, both `INDEFERIDO ...` and
    on the ballot (domain-model scenario 10); governor 22 (`PARTIDO ISOLADO`, `RENÚNCIA`,
    off the ballot, nobody else with the number: the trio is `not_found`).
  - AC senator 456 with `1º SUPLENTE` and `2º SUPLENTE`; federal deputies 4512 and 1313;
    state deputies 45123 (`JOANA D'ARC`, an apostrophe in the ballot name) and 22222, plus a
    second 22222 (`ROBERTO NUNES`, `INDEFERIDO`, off the ballot, `ST_SUBSTITUIDO = S`): the
    rejected candidate the on-ballot 22222 replaced, so the trio resolves to the substitute.
  - Presidents 13, 45 and 22 with their vices, `SG_UF = BR` (scenario 9), in round 1; 45 and
    22 with their vices again in round 2 (`NR_TURNO = 2`, `DT_ELEICAO` 25/10/2026), 13
    eliminated (scenario 14).
- `consulta_cand_complementar_2026_BRASIL.csv`: one row per `SQ_CANDIDATO`, full header,
  without `NR_TURNO` (as the 2026 `leiame.pdf` documents), so the build deduplicates by
  `SQ_CANDIDATO` and a candidacy in both rounds shares its row; the tests derive a variant
  with `NR_TURNO` to cover the other join.
- `rede_social_candidato_2026_BRASIL.csv`: four links for three candidates.
- `bem_candidato_2026_BRASIL.csv`: declared assets with the real 2026 header (checked against
  the TSE file of 2026-09-25), nine items: governor 45 (three items, total 1,216,500.00),
  governor 13 (two items, one of them negative, as the real file has a few), federal deputy
  4512, presidents 13 and 45, and one `SQ_CANDIDATO` that is no candidacy of the candidates
  file, which the build drops. Every `DS_BEM_CANDIDATO` is invented free text with the shapes
  that make it forbidden (a street, a plate, a bank agency, a CPF and a CNPJ placeholder), so
  the LGPD contract test proves the column never reaches the index or an answer (ADR 0009).

The complementary file carries `NM_TIPO_DESTINACAO_VOTOS` as the real one does: "Válido" for
the on-ballot candidacies, "Anulado sub judice" for governor 13 and its vice (rejected with an
appeal, on the ballot), `#NULO` for the two off-ballot ones. `ST_DECLARAR_BENS` is `S` except
federal deputy 1313 (`N`, declared having no assets) and president 22 (`Não divulgável`, a real
value, read as unknown).

The `DS_CARGO` texts are the spellings mapped in `pipeline/build.py` (`OFFICE_BY_DS_CARGO`);
the first real ingestion (2026-09-24) found exactly those ten texts, and the build still fails
loudly on any other. The real shape of a substituted candidacy still flagged on the ballot is
derived in `tests/conftest.py` (`SUBSTITUTED_STILL_ON_BALLOT`, through `with_fields`).

## `acre_lgpd/`

The same six rows with the five forbidden personal-data columns of ADR 0004 appended
(`NR_CPF_CANDIDATO`, `NR_TITULO_ELEITORAL_CANDIDATO`, `DT_NASCIMENTO`, `SG_UF_NASCIMENTO`,
`DS_EMAIL`), with placeholder values. The LGPD contract test builds an index from it and
fails if any of those columns reaches the index or an answer.
