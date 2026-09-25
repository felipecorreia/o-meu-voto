# 0008. Candidate comparator v1: scope, content and neutrality rules (amends 0007)

Status: accepted, 2026-09-25.

## Context

ADR 0007 made the candidate comparator the first scope beyond the four MVP questions, with v1
restricted to fields already in the index, no ingestion changes and round 2 as the target. A
research round on 2026-09-25 (report `bre-comparador-pesquisa`, kept outside the repository)
changed the picture:

- The complementary candidate file the pipeline already downloads carries
  `NM_TIPO_DESTINACAO_VOTOS`: "Válido", "Anulado sub judice" or "Nulo técnico". In the file
  generated on 2026-09-25 at 16:30, 663 on-ballot candidacies were "Anulado sub judice" and 74
  "Nulo técnico", 50 of those after a renunciation. `on_ballot` alone does not tell a voter
  whether a vote for that number will count.
- The TSE publishes declared assets for 2026 (`bem_candidato_2026.zip`, dataset
  `candidatos-2026`): 77,254 items for 13,909 candidacies on 2026-09-25. The total per
  candidacy is cheap to compute; the free-text description of each item carries addresses,
  plates, bank agencies and CPF mentions (ADR 0009).
- Existing public comparators (Puxa Ficha, Raio-X 2026 and others) cover the executive offices
  and the Senate, rank or flag candidates, or summarize plans with AI. None compares deputies,
  shows vote validity side by side, or offers the comparison as an MCP tool.
- The comparator leads the public launch on 2026-09-30; where-to-vote becomes secondary on the
  page.

The captain answered the report's grilling list on 2026-09-25, verbatim: "grilling do
comparador: ok, para tudo com suas sugestões, porém apenas um ajuste queria as fotos dos
candidatos isso será possível?", then "avance". Earlier answers in the same round asked for a
FAQ on the page explaining vote destination, the growth calculation and privacy.

## Decision

**Scope.** The comparator ships at the public launch (2026-09-30), not only for round 2. A
comparison has 2 to 4 on-ballot candidacies of the same UF, ballot office and round, for all
six ballot offices, selected by `sq_candidato` or by ballot number. The round follows the list
rules C1-C4 of `docs/codebase-design.md` 3.4. Without a selector, the comparison takes every
on-ballot candidacy of the round when there are 2 to 4 (the round-2 finalists). The four
where-to-vote tools and their REST routes stay unchanged; the page only demotes them.

**Content of v1**, per candidacy: the official photo (`photo_url`, the captain's one
adjustment; null until `mirror_photos` runs, issue #43), ballot name and number, civil and
social name, party, nomination kind with the federation or coalition and its composition, the
adjudication status verbatim, `on_ballot`, the vote destination verbatim with one explanatory
PT-BR line, the self-declared occupation, the running mates by name and party only, the social
links, the DivulgaCandContas link, and the 2026 declared-assets total (or "declared having no
assets", or "no information"). The answer cites both files it draws on: `source` is the
candidates file, `data.assets_source` the asset file, and a stale one of them warns.

**Ingestion changes** (amending ADR 0007's "no ingestion changes for v1"): the build keeps
`NM_TIPO_DESTINACAO_VOTOS` and `ST_DECLARAR_BENS` from the complementary file, and ingests
`bem_candidato_2026` as one total per candidacy summed at build time. The asset kind is not
stored (total only, no categories); the free text is dropped at the first read (ADR 0009).
`vote_destination` is also added to `list_candidates` and `get_candidate`, since it fixes the
same blind spot there.

**Neutrality rules.** Entries always come in ballot-number order, never by any value. No
percentages, no scores, no colour for up or down, no "atypical value" flag: an outlier is
shown as declared, next to a fixed caveat (values as declared to the TSE, usually at
acquisition cost, not corrected or judged by the service) and the official page that lists
every item. The short text of the MCP tool follows the same order and says that it is neither
a ranking nor a vote recommendation. A comparison never carries gender, race/colour, marital
status, education, age, birthplace, CPF, título or the asset free text: it is list-shaped under
ADR 0004.

**Later versions**, decided now so v1 does not preclude them:

- v1.1, asset growth versus the previous election, through the título join key of ADR 0009:
  baseline is the most recent prior declaration of any office in 2018-2024, always printed
  with its year and office; growth in reais, both nominal and IPCA-corrected; no percentages.
- v2: campaign-finance composition by origin (party funds, individuals, own resources),
  linking to the TSE's own comparator for totals; government plans as a PDF link only, never
  summarized; previous candidacies with results; grounds for rejection.

**The page** carries a FAQ explaining the vote destination, how growth is calculated and what
the service does with personal data.

## Consequences

- The index schema goes to version 5: two candidate columns (`vote_destination`,
  `declares_assets`) and the `candidate_assets` table. The refresh workflow downloads one more
  ZIP, and `build` and `validate` take `--candidate-assets`.
- The TSE changes the vote destination until election day; a stale index misleads on the most
  decision-relevant field. The 48-hour warning covers it, and it now covers the asset file too.
- Photos appear only once the photo ZIPs are downloaded and mirrored (issue #43); until then
  `photo_url` is null and the page shows a placeholder.
- ADR 0007's product recorte otherwise stands: the comparator is additive, the four MVP
  questions are unchanged, and finance totals stay with the TSE.
