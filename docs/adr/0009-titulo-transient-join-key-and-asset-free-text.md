# 0009. The título as a transient join key for asset growth; asset free text dropped (amends 0004)

Status: accepted, 2026-09-25. The join key is for v1.1 (ADR 0008) and is not implemented yet;
dropping the asset free text is implemented with the v1 comparator.

## Context

ADR 0004 discards `NR_CPF_CANDIDATO`, `NR_TITULO_ELEITORAL_CANDIDATO`, `DT_NASCIMENTO`,
`SG_UF_NASCIMENTO` and `DS_EMAIL` before any write, and says the service does no enrichment
and no cross-referencing with other bases. Two needs of the candidate comparator (ADR 0008)
touch that decision.

**Asset growth versus the previous election.** `SQ_CANDIDATO` identifies a candidacy, not a
person, so a 2026 candidacy can only be linked to the same person's earlier declarations
through a personal key. The research of 2026-09-25 (report `bre-comparador-pesquisa`, kept
outside the repository) measured the keys in the TSE's own `consulta_cand_<year>` files:

- CPF is masked (`-4`) in the whole 2024 file, and the 2026 `leiame.pdf` already calls it
  non-disclosable, so CPF cannot link 2024 and may disappear from 2026.
- The título is present in every year from 2018 to 2026. Where both keys exist (2026 to 2022),
  título and CPF agree on 6,522 of 6,524 links.
- Matching by civil name agrees with CPF on 5,069 of 5,157 links (98.3 %): 1.7 % of the links
  would attach someone else's assets to a candidacy.

**The asset free text.** `bem_candidato` describes each item in free text
(`DS_BEM_CANDIDATO`). Among the 77,254 descriptions of 2026-09-25, the report counted matches
for street addresses ("RUA " 1,189), vehicle plates ("PLACA" 500), bank agencies (474), CPF
mentions (211), CNPJ mentions (1,579), RENAVAM and chassis numbers: identifiers of the
candidate and of third parties. Hiding the column in the answers would still keep it in the
index.

The captain accepted both recommendations on 2026-09-25 ("grilling do comparador: ok, para
tudo com suas sugestões", ADR 0008), including two separate ADRs so this LGPD decision reads
on its own.

## Decision

1. **`DS_BEM_CANDIDATO` joins the forbidden columns** of `index_schema.py`: it is dropped at
   the first read of the file, like the five columns of ADR 0004, never stored, never served,
   and the LGPD contract test fails if it reaches the index or an answer. The service keeps
   only one total per candidacy (ADR 0008); the official DivulgaCandContas page, which the
   answer links to, lists every item.
2. **The título may be used as a transient join key, and only as that.** A pipeline build may
   read `NR_TITULO_ELEITORAL_CANDIDATO` in memory, only to match a 2026 candidacy with the same
   person's candidacies in the TSE's own candidate and asset files of 2018 to 2024. It may store
   only values derived from that match, keyed by the 2026 `sq_candidato`: the year and office of
   the baseline candidacy and its declared total. The título never reaches the index, the
   manifest, a log, a validation report, a test fixture other than placeholders, or an answer;
   it stays in `FORBIDDEN_COLUMNS`, so every read outside that join still drops it. When one
   título holds several candidacies in a year (re-registrations, substitutions), the one with
   an asset declaration wins, then the one that reached the ballot.
3. **No other base and no other key.** The match uses only the TSE's own open-data files;
   ADR 0004's rule against enrichment from other bases stands. Matching by name is rejected. If
   the TSE masks the título as it masked the CPF in 2024, growth stops being computable and the
   answer says so; it never falls back to another key.

## Consequences

- ADR 0004's list of discarded columns grows by one, and its "no cross-referencing" rule gains
  one narrow, stated exception: the TSE's own candidate files of earlier elections, joined in
  memory by the título, for asset growth only.
- The v1.1 history build must prove, by test, that no column or value of the título survives
  the build (the same contract test, extended to the history inputs).
- A voter can be shown someone else's money only if the TSE's own título is wrong; the report
  found 2 disagreements with the CPF in 6,524 links.
- Growth coverage depends on the TSE keeping the título public in its candidate files.
