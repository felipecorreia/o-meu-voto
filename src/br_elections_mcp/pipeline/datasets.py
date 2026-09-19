"""Registry of the TSE open-data ZIPs the pipeline ingests.

Every entry is one CC-BY resource of the Portal de Dados Abertos do TSE
(docs/domain-model.md, section 2). The CKAN dataset page is what every answer
cites as `source.dataset_url`; the ZIP URL on the CDN is what `fetch` downloads.
Photos are not here: they belong to the mirror_photos stage.
"""

from __future__ import annotations

from dataclasses import dataclass

CKAN_BASE_URL = "https://dadosabertos.tse.jus.br/dataset"
CDN_BASE_URL = "https://cdn.tse.jus.br/estatistica/sead/odsele"


@dataclass(frozen=True, slots=True)
class Dataset:
    """One ZIP of the TSE open-data portal.

    `id` is the pipeline's own name for the file; `ckan_dataset` is the slug of
    the dataset page that groups it (one page holds several ZIPs).
    """

    id: str
    ckan_dataset: str
    title: str
    file_name: str
    url: str

    @property
    def dataset_url(self) -> str:
        """Page of the dataset on the portal, cited in every answer."""
        return f"{CKAN_BASE_URL}/{self.ckan_dataset}"


POLLING_PLACES_2026 = Dataset(
    id="polling_places_2026",
    ckan_dataset="eleitorado-2026",
    title="Eleitorado por local de votação - 2026",
    file_name="eleitorado_local_votacao_2026.zip",
    url=f"{CDN_BASE_URL}/eleitorado_locais_votacao/eleitorado_local_votacao_2026.zip",
)

CANDIDATES_2026 = Dataset(
    id="candidates_2026",
    ckan_dataset="candidatos-2026",
    title="Candidatos - 2026",
    file_name="consulta_cand_2026.zip",
    url=f"{CDN_BASE_URL}/consulta_cand/consulta_cand_2026.zip",
)

CANDIDATES_COMPLEMENTARY_2026 = Dataset(
    id="candidates_complementary_2026",
    ckan_dataset="candidatos-2026",
    title="Candidatos - Informações complementares - 2026",
    file_name="consulta_cand_complementar_2026.zip",
    url=f"{CDN_BASE_URL}/consulta_cand_complementar/consulta_cand_complementar_2026.zip",
)

CANDIDATE_SOCIAL_LINKS_2026 = Dataset(
    id="candidate_social_links_2026",
    ckan_dataset="candidatos-2026",
    title="Redes sociais de candidatos - 2026",
    file_name="rede_social_candidato_2026.zip",
    url=f"{CDN_BASE_URL}/consulta_cand/rede_social_candidato_2026.zip",
)

MUNICIPALITIES_TSE_IBGE = Dataset(
    id="municipalities_tse_ibge",
    ckan_dataset="codigos-oficiais-de-uf-e-municipios-segundo-o-tse-e-o-ibge",
    title="Códigos oficiais de UF e municípios segundo o TSE e o IBGE",
    file_name="municipio_tse_ibge.zip",
    url=f"{CDN_BASE_URL}/municipio_tse_ibge/municipio_tse_ibge.zip",
)

DATASETS: tuple[Dataset, ...] = (
    POLLING_PLACES_2026,
    CANDIDATES_2026,
    CANDIDATES_COMPLEMENTARY_2026,
    CANDIDATE_SOCIAL_LINKS_2026,
    MUNICIPALITIES_TSE_IBGE,
)

_BY_ID = {dataset.id: dataset for dataset in DATASETS}


def dataset_by_id(dataset_id: str) -> Dataset:
    """Look a dataset up by its pipeline id; raises KeyError with the known ids."""
    try:
        return _BY_ID[dataset_id]
    except KeyError:
        raise KeyError(f"unknown dataset {dataset_id!r}; known: {sorted(_BY_ID)}") from None
