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
    CalendarSourceInfo,
    CandidateListItem,
    CandidatesAnswer,
    CandidatesData,
    Coalition,
    CuratedSource,
    ElectionInfo,
    ElectionInfoAnswer,
    ElectionInfoData,
    ElectionInfoRound,
    ElectionRoundInfo,
    Federation,
    Municipality,
    NotFound,
    Party,
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
from br_elections_mcp.core.normalize import (
    check_office_for_uf,
    normalize_ballot_office,
    normalize_candidate_uf,
    normalize_date,
    normalize_limit,
    normalize_number,
    normalize_offset,
    normalize_polling_uf,
    search_text,
)
from br_elections_mcp.core.queries import candidates as candidate_queries
from br_elections_mcp.core.queries.candidates import CandidateFilter, CandidateRow
from br_elections_mcp.core.queries.polling_place import SectionRow, find_section
from br_elections_mcp.domain import Election
from br_elections_mcp.domain import ElectionRound as DomainElectionRound
from br_elections_mcp.index_schema import TSE_TIMEZONE, DatasetKey

Clock = Callable[[], dt.datetime]
"""Returns the current instant, timezone-aware."""


def system_clock() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


MAX_LIMIT = 50
"""The largest page any list answers (codebase-design 3.1)."""

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

    def election_info(self, on: object = None) -> ElectionInfoAnswer:
        """Rounds, voting hours, next round and offices of the current election.

        ``on`` defaults to today in America/Sao_Paulo. Reads only
        ``data/elections.yaml``, never the index, so this answer never ages:
        ``source.kind`` is ``curated`` and there is no staleness warning.
        After the last round of the last election in the file, ``data`` still
        describes that election, with ``next_round`` null; never ``not_found``.
        """
        day = self._today() if on is None else normalize_date(on, "data inválida")
        election = self._calendar.current_or_last_election(day)
        hours = election.voting_hours
        next_round = election.next_round_on(day)
        return ElectionInfoAnswer(
            data=ElectionInfoData(
                rounds=[_election_info_round(r) for r in election.rounds],
                voting_hours=VotingHoursInfo(
                    start=hours.start.strftime("%H:%M"),
                    end=hours.end.strftime("%H:%M"),
                    timezone=hours.timezone,
                    label=hours.label,
                ),
                next_round=_election_info_round(next_round) if next_round is not None else None,
                days_until_next_round=(
                    (next_round.date - day).days if next_round is not None else None
                ),
                offices=list(election.offices),
                notes=list(election.notes),
                calendar_source=CalendarSourceInfo(
                    title=election.calendar_source.title,
                    url=election.calendar_source.url,
                    verified_at=election.calendar_source.verified_at,
                ),
            ),
            not_found=None,
            warnings=[],
            election=None,
            source=CuratedSource(
                calendar_source=election.calendar_source.title,
                verified_at=election.calendar_source.verified_at,
            ),
        )

    def list_candidates(
        self,
        uf: object,
        office: object,
        party: object = None,
        name: object = None,
        on_ballot_only: bool = True,
        limit: object = MAX_LIMIT,
        offset: object = 0,
        round: object = None,
    ) -> CandidatesAnswer:
        """The candidates of a ballot office in a UF (``BR`` for president).

        ``party`` is an acronym or a number; ``name`` matches the ballot or
        the civil name without accents or case. Only on-ballot candidates by
        default. Raises ``InvalidQuery`` for an unknown office, an office
        impossible for the UF, ``limit`` outside 1..50 or a round outside the
        calendar; an empty list is an answer, never ``not_found``.
        """
        index = self._open()
        uf_value = normalize_candidate_uf(uf)
        office_value = normalize_ballot_office(office)
        check_office_for_uf(office_value, uf_value)
        limit_value = normalize_limit(limit, MAX_LIMIT)
        offset_value = normalize_offset(offset)
        requested_round = None if round is None else normalize_number(round, "turno inválido")
        party_number, party_acronym = _party_filter(party)
        name_filter = search_text(name) if name is not None and str(name).strip() else None

        today = self._today()
        election = self._calendar.coincident_election(today, index.manifest)
        _check_round_bound(requested_round, election)
        source = self._source(index, "candidates")

        with index.cursor() as cursor:
            rounds = candidate_queries.office_rounds(cursor, uf_value, office_value.value)
            if not rounds:
                rounds = candidate_queries.candidate_rounds(cursor)
            if not rounds:
                raise IndexUnavailable("the index has no candidates in any round")
            answered_round = _pick_round(rounds, requested_round)
            filters = CandidateFilter(
                uf=uf_value,
                office=office_value.value,
                round=answered_round,
                on_ballot_only=bool(on_ballot_only),
                party_number=party_number,
                party_acronym=party_acronym,
                name=name_filter,
            )
            rows, total = candidate_queries.list_candidates(
                cursor, filters, limit_value, offset_value
            )

        return CandidatesAnswer(
            data=CandidatesData(
                round=answered_round,
                candidates=[_candidate_list_item(row) for row in rows],
                total=total,
                limit=limit_value,
                offset=offset_value,
            ),
            not_found=None,
            warnings=[],
            election=_election_info(election, answered_round),
            source=source,
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
    _check_round_bound(requested, election)
    return _pick_round(published, requested)


def _check_round_bound(requested: int | None, election: Election | None) -> None:
    """A round outside 1..n of the calendar (1..2 without a coincident election) is
    ``InvalidQuery`` (codebase-design 3.4, common rules)."""
    if requested is None:
        return
    last = len(election.rounds) if election is not None else 2
    if requested > last:
        raise InvalidQuery(f"turno inválido: {requested}; os turnos possíveis vão de 1 a {last}")


def _pick_round(present: tuple[int, ...], requested: int | None) -> int:
    """Absent -> highest present; explicit and present -> that one; explicit and absent ->
    highest present. ``present`` is never empty."""
    if requested is not None and requested in present:
        return requested
    return present[-1]


def _party_filter(party: object) -> tuple[int | None, str | None]:
    """``"45"`` and ``45`` filter by number; ``"psdb"`` by acronym, without accents or case."""
    if party is None:
        return None, None
    if isinstance(party, bool):
        raise InvalidQuery(f"partido inválido: {party!r}")
    if isinstance(party, int):
        return party, None
    text = str(party).strip()
    if not text:
        return None, None
    if text.isdigit():
        return int(text), None
    return None, search_text(text)


def _candidate_list_item(row: CandidateRow) -> CandidateListItem:
    federation = None
    if row.federation_acronym is not None:
        federation = Federation(acronym=row.federation_acronym, name=row.federation_name or "")
    coalition = Coalition(name=row.coalition_name) if row.coalition_name is not None else None
    return CandidateListItem(
        sq_candidato=row.sq_candidato,
        number=row.number,
        ballot_name=row.ballot_name,
        name=row.name,
        office=row.office,  # type: ignore[arg-type]
        party=Party(number=row.party_number, acronym=row.party_acronym, name=row.party_name),
        federation=federation,
        coalition=coalition,
        adjudication_status=row.adjudication_status,
        on_ballot=row.on_ballot,
        occupation=row.occupation,
        photo_url=None,
    )


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


def _election_info_round(round_: DomainElectionRound) -> ElectionInfoRound:
    return ElectionInfoRound(number=round_.number, date=round_.date, note=round_.note)


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
