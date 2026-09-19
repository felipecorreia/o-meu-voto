"""``Core``: the deep module that answers the voter's questions over a local index.

No HTTP, no network, no knowledge of who is asking. The index arrives through
the ``IndexSource`` port; the calendar comes from ``data/elections.yaml``; the
clock is injected so tests can move in time.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path
from zoneinfo import ZoneInfo

from br_elections_mcp.core.answers import (
    ElectionInfo,
    ElectionRoundInfo,
    Municipality,
    NotFound,
    PollingPlace,
    PollingPlaceAnswer,
    PollingPlaceData,
    PreviousPlace,
    Source,
    VotingHoursInfo,
)
from br_elections_mcp.core.calendar import Calendar
from br_elections_mcp.core.errors import IndexUnavailable, InvalidQuery
from br_elections_mcp.core.index import Index, open_index
from br_elections_mcp.core.index_source import IndexSource, IndexSourceUnavailable
from br_elections_mcp.core.normalize import normalize_number, normalize_polling_uf
from br_elections_mcp.core.queries.polling_place import SectionRow, find_section
from br_elections_mcp.domain import Election
from br_elections_mcp.index_schema import TSE_TIMEZONE, DatasetKey

Clock = Callable[[], dt.datetime]
"""Returns the current instant, timezone-aware."""


def system_clock() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


SECTION_NOT_FOUND_GUIDANCE = (
    "Confira a zona e a seção no e-Título ou no título impresso. Sem o título, use o serviço "
    "Onde votar do TSE: https://www.tse.jus.br/servicos-eleitorais/autoatendimento-eleitoral"
    "#/atendimento-eleitor/onde-votar"
)


def aggregated_section_warning(main_section: int) -> str:
    return f"Sua seção é agregada: a votação acontece na seção {main_section}, no mesmo local."


def place_changed_warning(previous: PreviousPlace) -> str:
    return f"O local de votação mudou. Antes era {previous.name}, endereço {previous.address}."


class Core:
    """Constructing a Core opens nothing; ``open_index()`` or ``start()`` does."""

    def __init__(
        self, index_source: IndexSource, elections_file: Path, clock: Clock = system_clock
    ) -> None:
        self._index_source = index_source
        self._calendar = Calendar.from_file(elections_file)
        self._clock = clock
        self._index: Index | None = None

    # Lifecycle

    def open_index(self) -> None:
        """The initial, synchronous open: the one call to ``IndexSource.current()`` here."""
        try:
            version = self._index_source.current()
        except IndexSourceUnavailable as exc:
            raise IndexUnavailable(str(exc)) from exc
        new_index = open_index(version)
        previous, self._index = self._index, new_index
        if previous is not None:
            previous.close()

    def start(self) -> None:
        """Called by the ASGI lifespan: the initial open.

        The background verification task of codebase-design 3.2 (reload without
        restart) is not part of this tracer bullet; ``start()`` is the initial
        open only.
        """
        self.open_index()

    def close(self) -> None:
        if self._index is not None:
            self._index.close()
            self._index = None

    # Queries

    def find_polling_place(
        self, uf: object, zone: object, section: object, round: object = None
    ) -> PollingPlaceAnswer:
        """Where a voter with UF, zone and section on their title votes.

        Input is normalized here ("009" is 9, "ac" is AC). Raises ``InvalidQuery``
        for an unknown UF, a non-numeric zone or section or a round outside the
        calendar; "not found" is an answer, never an exception.
        """
        index = self._open()
        uf_value = normalize_polling_uf(uf)
        zone_number = normalize_number(zone, "zona inválida")
        section_number = normalize_number(section, "seção inválida")
        requested_round = None if round is None else normalize_number(round, "turno inválido")

        today = self._today()
        election = self._calendar.coincident_election(today, index.manifest)
        answered_round = _resolve_round(index, requested_round, election)
        election_info = _election_info(election, answered_round)
        source = self._source(index, "polling_places")

        with index.cursor() as cursor:
            row = find_section(cursor, uf_value, zone_number, section_number, answered_round)
        if row is None:
            return PollingPlaceAnswer(
                data=None,
                not_found=NotFound(
                    reason="secao_nao_encontrada", guidance=SECTION_NOT_FOUND_GUIDANCE
                ),
                warnings=[],
                election=election_info,
                source=source,
            )

        data = _polling_place_data(row)
        warnings: list[str] = []
        if row.section_kind == "agregada":
            warnings.append(aggregated_section_warning(data.votes_at_section))
        if data.previous_place is not None:
            warnings.append(place_changed_warning(data.previous_place))
        return PollingPlaceAnswer(
            data=data, not_found=None, warnings=warnings, election=election_info, source=source
        )

    # Helpers

    def _open(self) -> Index:
        if self._index is None:
            raise IndexUnavailable("index is not open; call open_index() or start() first")
        return self._index

    def _today(self) -> dt.date:
        return self._clock().astimezone(ZoneInfo(TSE_TIMEZONE)).date()

    @staticmethod
    def _source(index: Index, dataset: DatasetKey) -> Source:
        origin = index.manifest.datasets[dataset]
        return Source(
            dataset=origin.dataset,
            dataset_url=origin.dataset_url,
            file=origin.file,
            generated_at=origin.generated_at,
            index_built_at=index.manifest.index_built_at,
        )


def _resolve_round(index: Index, requested: int | None, election: Election | None) -> int:
    """Round handling of this tracer bullet: absent -> highest published; explicit and
    published -> that one; explicit and unpublished -> highest published. The warnings of the
    full round table (codebase-design 3.4) are added when the table is implemented."""
    published = index.published_rounds
    if not published:
        raise IndexUnavailable("the index has no polling sections in any round")
    if requested is None:
        return published[-1]
    last = len(election.rounds) if election is not None else 2
    if requested > last:
        raise InvalidQuery(f"turno inválido: {requested}; os turnos possíveis vão de 1 a {last}")
    if requested in published:
        return requested
    return published[-1]


def _election_info(election: Election | None, answered_round: int) -> ElectionInfo | None:
    if election is None:
        return None
    round_ = next((r for r in election.rounds if r.number == answered_round), None)
    if round_ is None:
        return None
    hours = election.voting_hours
    return ElectionInfo(
        id=election.id,
        name=election.name,
        round=ElectionRoundInfo(number=round_.number, date=round_.date),
        voting_hours=VotingHoursInfo(
            start=hours.start.strftime("%H:%M"),
            end=hours.end.strftime("%H:%M"),
            timezone=hours.timezone,
            label=hours.label,
        ),
    )


def _polling_place_data(row: SectionRow) -> PollingPlaceData:
    previous = None
    if row.previous_place_number is not None:
        previous = PreviousPlace(
            number=row.previous_place_number,
            name=row.previous_place_name or "",
            address=row.previous_place_address or "",
        )
    return PollingPlaceData(
        municipality=Municipality(
            tse_code=row.municipality_tse_code,
            ibge_code=row.municipality_ibge_code,
            name=row.municipality_name,
            uf=row.uf,
        ),
        round=row.round,
        zone=row.zone,
        section=row.section,
        section_kind=row.section_kind,  # type: ignore[arg-type]
        votes_at_section=row.main_section if row.main_section is not None else row.section,
        voters_in_section=row.voters,
        accessibility=row.accessibility,  # type: ignore[arg-type]
        place=PollingPlace(
            number=row.place_number,
            name=row.place_name,
            kind=row.place_kind,
            address=row.place_address,
            neighborhood=row.place_neighborhood,
            postal_code=row.place_postal_code,
            phone=row.place_phone,
            latitude=row.place_latitude,
            longitude=row.place_longitude,
            status=row.place_status,  # type: ignore[arg-type]
            section_count=row.place_section_count,
            accessible_section_count=row.place_accessible_section_count,
        ),
        previous_place=previous,
    )
