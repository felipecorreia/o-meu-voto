"""The link to a candidacy's official page on DivulgaCandContas, derived, never fetched.

The site is a link for the human to open, never a data source (ADR 0004); it
also blocks common HTTP clients (ADR 0003), so nothing here touches the
network. The URL scheme is the one the site uses since 2026-08, as recorded by
turicas/eleicoes-brasil (the site itself cannot be read by a non-browser client):
``/#/candidato/{REGION}/{UF}/{election id}/{sq_candidato}/{year}/{electoral unit}``.
The election id is not the ``CD_ELEICAO`` of the TSE files; it is curated per
election in ``data/elections.yaml`` (``divulgacandcontas_election_id``).
"""

from __future__ import annotations

from br_elections_mcp.domain import UF

BASE_URL = "https://divulgacandcontas.tse.jus.br/divulga/#/candidato"

REGION_BY_UF: dict[UF, str] = {
    UF.AC: "NORTE",
    UF.AM: "NORTE",
    UF.AP: "NORTE",
    UF.PA: "NORTE",
    UF.RO: "NORTE",
    UF.RR: "NORTE",
    UF.TO: "NORTE",
    UF.AL: "NORDESTE",
    UF.BA: "NORDESTE",
    UF.CE: "NORDESTE",
    UF.MA: "NORDESTE",
    UF.PB: "NORDESTE",
    UF.PE: "NORDESTE",
    UF.PI: "NORDESTE",
    UF.RN: "NORDESTE",
    UF.SE: "NORDESTE",
    UF.DF: "CENTRO-OESTE",
    UF.GO: "CENTRO-OESTE",
    UF.MS: "CENTRO-OESTE",
    UF.MT: "CENTRO-OESTE",
    UF.ES: "SUDESTE",
    UF.MG: "SUDESTE",
    UF.RJ: "SUDESTE",
    UF.SP: "SUDESTE",
    UF.PR: "SUL",
    UF.RS: "SUL",
    UF.SC: "SUL",
    UF.BR: "BRASIL",
}
"""The region segment of the URL for every UF a candidacy can have (ZZ has none)."""


def candidate_page_url(
    election_id: str | None, uf: UF, sq_candidato: int, election_year: int
) -> str | None:
    """The candidacy's page, or null when the calendar has no id for its election.

    The electoral unit of a general election is the UF itself (``BR`` for
    president), so the last segment repeats ``uf``.
    """
    if election_id is None:
        return None
    region = REGION_BY_UF[uf]
    return f"{BASE_URL}/{region}/{uf.value}/{election_id}/{sq_candidato}/{election_year}/{uf.value}"
