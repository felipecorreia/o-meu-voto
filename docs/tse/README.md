# TSE dataset documentation (`leiame.pdf`)

The `leiame.pdf` that the TSE ships inside each ZIP of the Portal de Dados Abertos, versioned
here so the LGPD citations in [ADR 0004](../adr/0004-lgpd-candidate-data-minimization.md) can
be verified against the exact document the pipeline read. The files are CC-BY, published by the
Tribunal Superior Eleitoral at <https://dadosabertos.tse.jus.br>; questions about them go to
`estatistica@tse.jus.br`, the contact the documents themselves name.

Downloaded on 2026-09-19 (UTC) by the pipeline's `fetch` stage
(`python -m br_elections_mcp.pipeline fetch`), from a residential connection in Brazil, and
extracted unchanged from the ZIPs below. Re-run `fetch` and replace these files when the TSE
updates a dataset; the `Last-Modified` header of each ZIP is the one the CDN returned.

| File | Source ZIP (dataset page) | ZIP `Last-Modified` | SHA-256 of the PDF |
|---|---|---|---|
| `eleitorado_local_votacao_2026_leiame.pdf` | [`eleitorado_local_votacao_2026.zip`](https://cdn.tse.jus.br/estatistica/sead/odsele/eleitorado_locais_votacao/eleitorado_local_votacao_2026.zip) ([`eleitorado-2026`](https://dadosabertos.tse.jus.br/dataset/eleitorado-2026)) | 2026-09-18 09:30:29 GMT | `f13dc50e0c1cd81a97c4f222bd427e84353b2d01dbecedbaec8185e6545e67fd` |
| `consulta_cand_2026_leiame.pdf` | [`consulta_cand_2026.zip`](https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2026.zip) ([`candidatos-2026`](https://dadosabertos.tse.jus.br/dataset/candidatos-2026)) | 2026-09-18 22:35:56 GMT | `f30553fb57dddd4ea6a3b1a636b50cb90edf2ac40ada27fe5cb7993d0c0cad70` |
| `consulta_cand_complementar_2026_leiame.pdf` | [`consulta_cand_complementar_2026.zip`](https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand_complementar/consulta_cand_complementar_2026.zip) ([`candidatos-2026`](https://dadosabertos.tse.jus.br/dataset/candidatos-2026)) | 2026-09-18 22:35:52 GMT | `67141c06dbc17ea0a803e9decd14893b328d0309cc1afc4986d307ae9297ca96` |
| `rede_social_candidato_2026_leiame.pdf` | [`rede_social_candidato_2026.zip`](https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/rede_social_candidato_2026.zip) ([`candidatos-2026`](https://dadosabertos.tse.jus.br/dataset/candidatos-2026)) | 2026-09-18 22:33:33 GMT | `6c3339f3d54069eea25d8d2cffc0d79e56fc3d97cb7d1f9d5f2a1421e3727e61` |
| `municipio_tse_ibge_leiame.pdf` | [`municipio_tse_ibge.zip`](https://cdn.tse.jus.br/estatistica/sead/odsele/municipio_tse_ibge/municipio_tse_ibge.zip) ([`codigos-oficiais-de-uf-e-municipios-segundo-o-tse-e-o-ibge`](https://dadosabertos.tse.jus.br/dataset/codigos-oficiais-de-uf-e-municipios-segundo-o-tse-e-o-ibge)) | 2026-09-13 12:00:27 GMT | `c6995db3ca1e0e2edb16cca0c78b7081953374c9b371619b5f5e4d326f18ee95` |

The three CKAN datasets are the ones the pipeline ingests (polling places, candidates and the
TSE/IBGE municipality crosswalk); `candidatos-2026` ships three ZIPs, each with its own
`leiame.pdf`, so all three are here. `consulta_cand_2026_leiame.pdf`, page 1, is the source of
the citation in ADR 0004: Res. TSE 23.609/2019, art. 33, § 2º (as amended by Res. 23.729/2024)
makes `NR_CPF_CANDIDATO` non-disclosable, even though the CSV still carries it.
