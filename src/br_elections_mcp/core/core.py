"""``Core``: the deep module that answers the voter's questions over a local index.

No HTTP, no network, no knowledge of who is asking. The index arrives through
the ``IndexSource`` port; the calendar comes from ``data/elections.yaml``; the
clock is injected so tests can move in time.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from br_elections_mcp.core.answers import (
    CalendarSourceInfo,
    CandidateAnswer,
    CandidateData,
    CandidateListItem,
    CandidateProfile,
    CandidatesAnswer,
    CandidatesData,
    Coalition,
    CoalitionDetail,
    CuratedSource,
    DatasetHealth,
    ElectionInfo,
    ElectionInfoAnswer,
    ElectionInfoData,
    ElectionInfoRound,
    ElectionRoundInfo,
    Federation,
    FederationDetail,
    IndexHealth,
    IndexHealthCheckError,
    MunicipalitiesAnswer,
    MunicipalitiesData,
    Municipality,
    MunicipalityMatch,
    NotFound,
    Party,
    PollingPlace,
    PollingPlaceAnswer,
    PollingPlaceData,
    PollingPlaceListItem,
    PollingPlacesAnswer,
    PollingPlacesData,
    PreviousPlace,
    RunningMate,
    Source,
    VotingHoursInfo,
)
from br_elections_mcp.core.calendar import Calendar
from br_elections_mcp.core.clock import Clock, system_clock
from br_elections_mcp.core.divulgacandcontas import candidate_page_url
from br_elections_mcp.core.errors import IndexUnavailable, InvalidQuery
from br_elections_mcp.core.index import Index, IndexManager
from br_elections_mcp.core.index_source import IndexSource
from br_elections_mcp.core.normalize import (
    check_office_for_uf,
    normalize_ballot_office,
    normalize_candidate_uf,
    normalize_date,
    normalize_limit,
    normalize_number,
    normalize_offset,
    normalize_polling_uf,
    normalize_text,
    search_text,
)
from br_elections_mcp.core.queries import candidates as candidate_queries
from br_elections_mcp.core.queries.candidates import (
    CandidateFilter,
    CandidateProfileRow,
    CandidateRow,
    RunningMateRow,
)
from br_elections_mcp.core.queries.municipalities import (
    MunicipalityRow,
    get_municipality,
    search_municipalities,
)
from br_elections_mcp.core.queries.polling_place import SectionRow, find_section
from br_elections_mcp.core.queries.search_places import PlaceRow, search_places
from br_elections_mcp.core.rounds import (
    RoundResolution,
    check_round_bound,
    highest_or_requested,
    resolve_list_round,
    resolve_place_round,
    resolve_profile_round,
)
from br_elections_mcp.domain import UF, Election, Office
from br_elections_mcp.domain import ElectionRound as DomainElectionRound
from br_elections_mcp.index_schema import TSE_TIMEZONE, DatasetKey

MAX_LIMIT = 50
"""The largest page any list answers (codebase-design 3.1)."""

STALE_AFTER_HOURS = 48
"""Above this age the data is stale, still served, with a warning (codebase-design 9)."""

SECTION_NOT_FOUND_GUIDANCE = (
    "Confira a zona e a seção no e-Título ou no título impresso. Sem o título, use o serviço "
    "Onde votar do TSE: https://www.tse.jus.br/servicos-eleitorais/autoatendimento-eleitoral"
    "#/atendimento-eleitor/onde-votar"
)

MUNICIPALITY_NOT_FOUND_GUIDANCE = (
    "Nenhum município com esse nome. Confira a grafia e a UF, ou use o código TSE do município."
)

MUNICIPALITY_AMBIGUOUS_GUIDANCE = (
    "Mais de um município casa com esse nome. Escolha um dos listados e repita a busca com o "
    "nome completo ou o código TSE."
)

SEARCH_PLACES_GUIDANCE = "Para saber a sua seção, consulte o e-Título."

CANDIDATE_NOT_FOUND_BY_NUMBER_GUIDANCE = (
    "Nenhum candidato com esse número está na urna para esse cargo nessa UF. Confira o número "
    "e o cargo, ou liste os candidatos do cargo com list_candidates."
)

CANDIDATE_NOT_FOUND_BY_SQ_GUIDANCE = (
    "Nenhuma candidatura com esse sq_candidato. Confira o número sequencial, ou procure o "
    "candidato por UF, cargo e número de urna."
)

SEARCH_PLACES_DEFAULT_LIMIT = 20
RESOLVE_MUNICIPALITY_DEFAULT_LIMIT = 10


# A point the client already has; the server never geocodes (codebase-design 8.2). The
# schema description is PT-BR because it reaches the MCP inputSchema.
class Near(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_schema_extra={"description": "Latitude e longitude do eleitor, em graus decimais"},
    )

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


def aggregated_section_warning(main_section: int, elsewhere_place_name: str | None) -> str:
    """``elsewhere_place_name`` is the voting place's name when it is not the place the
    aggregated section is registered at, ``None`` when both are the same place."""
    if elsewhere_place_name is None:
        where = "no mesmo local"
    else:
        where = f"em outro local: {elsewhere_place_name}"
    return f"Sua seção é agregada: a votação acontece na seção {main_section}, {where}."


def place_changed_warning(previous: PreviousPlace) -> str:
    return f"O local de votação mudou. Antes era {previous.name}, endereço {previous.address}."


def stale_data_warning(generated_at: dt.datetime, age_hours: float) -> str:
    local = generated_at.astimezone(ZoneInfo(TSE_TIMEZONE))
    return (
        f"Os dados do TSE usados nesta resposta foram gerados em "
        f"{local.strftime('%d/%m/%Y')} às {local.strftime('%H:%M')} (há {round(age_hours)} "
        "horas). Confira no e-Título se algo mudou."
    )


class Core:
    """Constructing a Core opens nothing; ``open_index()`` or ``start()`` does."""

    def __init__(
        self, index_source: IndexSource, elections_file: Path, clock: Clock = system_clock
    ) -> None:
        self._calendar = Calendar.from_file(elections_file)
        self._clock = clock
        self._index_manager = IndexManager(index_source, clock)

    # Lifecycle

    def open_index(self) -> None:
        """The initial, synchronous open, without the check task: the one call to
        ``IndexSource.current()`` outside ``refresh()``. Shared by ``start()`` and by tests."""
        self._index_manager.open()

    def start(self) -> None:
        """Called by the ASGI lifespan: the initial open, then the check task."""
        self._index_manager.start()

    def close(self) -> None:
        """Called by the ASGI lifespan: stop the check task and close the index."""
        self._index_manager.close()

    def refresh(self) -> None:
        """Swap to the ``IndexSource``'s current version when it differs from the open one.

        What the check task runs; tests call it directly. Never raises: a failing
        check is logged and the open version keeps being served.
        """
        self._index_manager.refresh()

    # Queries

    def find_polling_place(
        self, uf: object, zone: object, section: object, round: object = None
    ) -> PollingPlaceAnswer:
        """Where a voter with UF, zone and section on their title votes.

        Input is normalized here ("009" is 9, "ac" is AC). Raises ``InvalidQuery``
        for an unknown UF, a non-numeric zone or section or a round outside the
        calendar; "not found" is an answer, never an exception. ``round`` follows
        lines T1-T7 of codebase-design 3.4 (``core/rounds.py``): without it, the
        next round of the current election when published.
        """
        uf_value = normalize_polling_uf(uf)
        zone_number = normalize_number(zone, "zona inválida")
        section_number = normalize_number(section, "seção inválida")
        requested_round = None if round is None else normalize_number(round, "turno inválido")

        with self._index_manager.query() as (index, cursor):
            today = self._today()
            election = self._calendar.coincident_election(today, index.manifest)
            resolution = _resolve_place_round(index, requested_round, election, today)
            election_info = _election_info(election, resolution.round)
            source = self._source(index, "polling_places")
            row = find_section(cursor, uf_value, zone_number, section_number, resolution.round)
        # The query is done with the index; whether to check for a new version is the
        # task's O(1) decision, never a wait for this query.
        self._index_manager.signal()
        if row is None:
            return PollingPlaceAnswer(
                data=None,
                not_found=NotFound(
                    reason="secao_nao_encontrada", guidance=SECTION_NOT_FOUND_GUIDANCE
                ),
                warnings=self._staleness_warnings(source),
                election=election_info,
                source=source,
            )

        data = _polling_place_data(row)
        warnings: list[str] = []
        if row.section_kind == "agregada":
            warnings.append(
                aggregated_section_warning(
                    data.votes_at_section, row.place_name if row.votes_elsewhere else None
                )
            )
        if data.previous_place is not None:
            warnings.append(place_changed_warning(data.previous_place))
        warnings.extend(_round_warnings(resolution))
        warnings.extend(self._staleness_warnings(source))
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
        calendar; an empty list is an answer, never ``not_found``. ``round``
        follows lines C1-C4 of codebase-design 3.4 (``core/rounds.py``): without
        it, the highest round the office has in the UF; a requested round the
        office does not have answers that one with a warning.
        """
        uf_value = normalize_candidate_uf(uf)
        office_value = normalize_ballot_office(office)
        check_office_for_uf(office_value, uf_value)
        limit_value = normalize_limit(limit, MAX_LIMIT, MAX_LIMIT)
        offset_value = normalize_offset(offset)
        requested_round = None if round is None else normalize_number(round, "turno inválido")
        party_number, party_acronym = _party_filter(party)
        name_filter = search_text(name) if name is not None and str(name).strip() else None

        with self._index_manager.query() as (index, cursor):
            today = self._today()
            election = self._calendar.coincident_election(today, index.manifest)
            check_round_bound(requested_round, election)
            source = self._source(index, "candidates")

            published = _published_candidate_rounds(cursor)
            resolution = resolve_list_round(
                office_rounds=_office_rounds(cursor, uf_value, office_value.value, published),
                published=published,
                requested=requested_round,
                office=office_value,
                uf=uf_value,
            )
            answered_round = resolution.round
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
        # The query is done with the index; whether to check for a new version is the
        # task's O(1) decision, never a wait for this query.
        self._index_manager.signal()

        return CandidatesAnswer(
            data=CandidatesData(
                round=answered_round,
                candidates=[_candidate_list_item(row) for row in rows],
                total=total,
                limit=limit_value,
                offset=offset_value,
            ),
            not_found=None,
            warnings=[*_round_warnings(resolution), *self._staleness_warnings(source)],
            election=_election_info(election, answered_round),
            source=source,
        )

    def get_candidate(
        self,
        sq_candidato: object = None,
        *,
        uf: object = None,
        office: object = None,
        number: object = None,
        round: object = None,
    ) -> CandidateAnswer:
        """The profile of one candidate, by ``sq_candidato`` or by UF, office and number.

        Exactly one of the two lookups: ``sq_candidato`` alone, or the whole trio.
        By ``sq_candidato`` the rounds of the candidacy are the ones it appears in;
        by the trio only on-ballot candidacies count, at most one per round, so a
        number held only off the ballot is ``candidato_nao_encontrado``. The
        profile carries the ticket (vice or substitutes with the same number), the
        social links declared to the TSE and the DivulgaCandContas link, derived and
        never fetched. Raises ``InvalidQuery`` for a malformed lookup or a round
        outside the calendar. ``round`` follows lines F1-F5 of codebase-design 3.4
        (``core/rounds.py``): without it, the highest round of the candidacy; a
        requested round the candidacy is not in answers the profile of its highest
        round with a warning, never ``not_found``.
        """
        lookup = _candidate_lookup(sq_candidato, uf, office, number)
        requested_round = None if round is None else normalize_number(round, "turno inválido")

        with self._index_manager.query() as (index, cursor):
            today = self._today()
            election = self._calendar.coincident_election(today, index.manifest)
            check_round_bound(requested_round, election)
            source = self._source(index, "candidates")

            # The set of rounds of the candidacy comes first, then the round table
            # (codebase-design 3.4): by sq_candidato, the rounds it appears in; by the
            # trio, the rounds with an on-ballot candidacy of that number.
            published = _published_candidate_rounds(cursor)
            candidacy = _candidacy(cursor, lookup)
            resolution: RoundResolution | None = None
            if candidacy is None:
                # Not found: the answer still names the round the office (or the index)
                # is at, so `election` is filled as in every other answer.
                answered_round = highest_or_requested(
                    _rounds_for_not_found(cursor, lookup, published), requested_round
                )
                profile = None
            else:
                resolution = resolve_profile_round(
                    candidacy_rounds=candidacy.rounds,
                    office_rounds=_office_rounds(cursor, candidacy.uf, candidacy.office, published),
                    published=published,
                    requested=requested_round,
                    office=Office(candidacy.office),
                    uf=candidacy.uf,
                )
                answered_round = resolution.round
                profile = _fetch_profile(cursor, lookup, answered_round)
            mates: list[RunningMateRow] = []
            links: list[str] = []
            if profile is not None:
                mates = candidate_queries.running_mates(
                    cursor, profile, _ticket_offices(Office(profile.office))
                )
                links = candidate_queries.social_links(cursor, profile.sq_candidato)
        # The query is done with the index; whether to check for a new version is the
        # task's O(1) decision, never a wait for this query.
        self._index_manager.signal()

        election_info = _election_info(election, answered_round)
        if profile is None:
            guidance = (
                CANDIDATE_NOT_FOUND_BY_SQ_GUIDANCE
                if isinstance(lookup, int)
                else CANDIDATE_NOT_FOUND_BY_NUMBER_GUIDANCE
            )
            return CandidateAnswer(
                data=None,
                not_found=NotFound(reason="candidato_nao_encontrado", guidance=guidance),
                warnings=self._staleness_warnings(source),
                election=election_info,
                source=source,
            )
        page_url = candidate_page_url(
            self._calendar.divulgacandcontas_election_id(profile.election_year),
            UF(profile.uf),
            profile.sq_candidato,
            profile.election_year,
        )
        return CandidateAnswer(
            data=CandidateData(candidate=_candidate_profile(profile, mates, links, page_url)),
            not_found=None,
            warnings=[*_round_warnings(resolution), *self._staleness_warnings(source)],
            election=election_info,
            source=source,
        )

    def resolve_municipality(
        self, name: object, uf: object = None, limit: object = None
    ) -> MunicipalitiesAnswer:
        """The TSE code of a municipality from its name, accent- and case-insensitive.

        Candidates come best ``score`` first (1.0 for the exact name). ``uf`` narrows,
        ``limit`` is 1..50 (default 10). No candidate is ``not_found``; ``election`` is
        always null because the list refers to no round. ``source`` is the TSE/IBGE
        crosswalk, even for the municipalities abroad that only the polling-place file lists.
        """
        text = normalize_text(name, "nome inválido")
        uf_value = None if uf is None else normalize_polling_uf(uf)
        limit_value = normalize_limit(limit, MAX_LIMIT, RESOLVE_MUNICIPALITY_DEFAULT_LIMIT)

        with self._index_manager.query() as (index, cursor):
            source = self._source(index, "municipalities")
            rows = search_municipalities(cursor, text, uf_value, limit_value)
        # The query is done with the index; whether to check for a new version is the
        # task's O(1) decision, never a wait for this query.
        self._index_manager.signal()
        if not rows:
            return MunicipalitiesAnswer(
                data=None,
                not_found=NotFound(
                    reason="municipio_nao_encontrado", guidance=MUNICIPALITY_NOT_FOUND_GUIDANCE
                ),
                warnings=self._staleness_warnings(source),
                election=None,
                source=source,
            )
        return MunicipalitiesAnswer(
            data=MunicipalitiesData(municipalities=[_municipality_match(row) for row in rows]),
            not_found=None,
            warnings=self._staleness_warnings(source),
            election=None,
            source=source,
        )

    def search_polling_places(
        self,
        uf: object,
        municipality: object,
        neighborhood: object = None,
        query: object = None,
        near: object = None,
        limit: object = None,
        round: object = None,
    ) -> PollingPlacesAnswer:
        """The polling places of a municipality, for a voter without zone and section.

        ``municipality`` is a name (resolved as ``resolve_municipality`` does, within
        ``uf``) or a TSE code. ``neighborhood`` and ``query`` (place name or address) are
        accent- and case-insensitive substrings. With ``near`` (``{latitude, longitude}``)
        the places come by distance, the ones without coordinates last, each with
        ``distance_km``; without it the field is absent. ``limit`` is 1..50 (default 20).
        A municipality that matches nothing is ``municipio_nao_encontrado``; one name
        that matches several municipalities is ``municipio_ambiguo`` with the options.
        A municipality with no matching place is an empty list, never ``not_found``.
        """
        uf_value = normalize_polling_uf(uf)
        municipality_text = normalize_text(municipality, "município inválido")
        neighborhood_text = (
            None if neighborhood is None else normalize_text(neighborhood, "bairro inválido")
        )
        query_text = None if query is None else normalize_text(query, "busca inválida")
        near_point = _normalize_near(near)
        limit_value = normalize_limit(limit, MAX_LIMIT, SEARCH_PLACES_DEFAULT_LIMIT)
        requested_round = None if round is None else normalize_number(round, "turno inválido")

        with self._index_manager.query() as (index, cursor):
            today = self._today()
            election = self._calendar.coincident_election(today, index.manifest)
            resolution = _resolve_place_round(index, requested_round, election, today)
            answered_round = resolution.round
            election_info = _election_info(election, answered_round)
            source = self._source(index, "polling_places")
            resolved, options = _resolve_municipality_in_uf(cursor, municipality_text, uf_value)
            if resolved is not None:
                rows, total = search_places(
                    cursor,
                    uf_value,
                    resolved.tse_code,
                    answered_round,
                    neighborhood=neighborhood_text,
                    query=query_text,
                    near=near_point,
                    limit=limit_value,
                )
        # The query is done with the index; whether to check for a new version is the
        # task's O(1) decision, never a wait for this query.
        self._index_manager.signal()
        if resolved is None:
            return PollingPlacesAnswer(
                data=None,
                not_found=_municipality_not_found(options),
                warnings=self._staleness_warnings(source),
                election=election_info,
                source=source,
            )
        return PollingPlacesAnswer(
            data=PollingPlacesData(
                round=answered_round,
                municipality=Municipality(
                    tse_code=resolved.tse_code,
                    ibge_code=resolved.ibge_code,
                    name=resolved.name,
                    uf=resolved.uf,
                ),
                places=[
                    _place_list_item(row, with_distance=near_point is not None) for row in rows
                ],
                total=total,
                guidance=SEARCH_PLACES_GUIDANCE,
            ),
            not_found=None,
            warnings=[*_round_warnings(resolution), *self._staleness_warnings(source)],
            election=election_info,
            source=source,
        )

    def health(self) -> IndexHealth:
        """Freshness of the open index, for the operator, before a voter sees any warning.

        Never ages by itself: every field reflects the open index and the check task as
        they are right now. Raises ``IndexUnavailable`` when nothing is open.
        """
        index = self._index_manager.current()
        now = self._clock()
        datasets = {
            key: _dataset_health(origin.generated_at, now)
            for key, origin in index.manifest.datasets.items()
        }
        last_error = self._index_manager.last_check_error
        return IndexHealth(
            datasets=datasets,
            index_built_at=index.manifest.index_built_at,
            stale=any(health.stale for health in datasets.values()),
            index_version=index.version,
            last_index_check_at=self._index_manager.last_check_at,
            last_index_check_error=(
                None
                if last_error is None
                else IndexHealthCheckError(at=last_error.at, message=last_error.message)
            ),
        )

    # Helpers

    def _today(self) -> dt.date:
        return self._clock().astimezone(ZoneInfo(TSE_TIMEZONE)).date()

    def _source(self, index: Index, dataset: DatasetKey) -> Source:
        origin = index.manifest.datasets[dataset]
        age_hours = _age_hours(origin.generated_at, self._clock())
        return Source(
            dataset=origin.dataset,
            dataset_url=origin.dataset_url,
            file=origin.file,
            generated_at=origin.generated_at,
            index_built_at=index.manifest.index_built_at,
            age_hours=age_hours,
            stale=age_hours > STALE_AFTER_HOURS,
        )

    @staticmethod
    def _staleness_warnings(source: Source) -> list[str]:
        if not source.stale:
            return []
        return [stale_data_warning(source.generated_at, source.age_hours)]


def _age_hours(generated_at: dt.datetime, now: dt.datetime) -> float:
    return (now - generated_at).total_seconds() / 3600


def _dataset_health(generated_at: dt.datetime, now: dt.datetime) -> DatasetHealth:
    age_hours = _age_hours(generated_at, now)
    return DatasetHealth(
        generated_at=generated_at, age_hours=age_hours, stale=age_hours > STALE_AFTER_HOURS
    )


def _resolve_place_round(
    index: Index, requested: int | None, election: Election | None, today: dt.date
) -> RoundResolution:
    """Lines T1-T7 of codebase-design 3.4 over the rounds with a section in the index."""
    published = index.published_rounds
    if not published:
        raise IndexUnavailable("the index has no polling sections in any round")
    return resolve_place_round(
        published=published, requested=requested, election=election, today=today
    )


def _published_candidate_rounds(cursor: duckdb.DuckDBPyConnection) -> tuple[int, ...]:
    """The rounds with any candidate row: "published" for lines C1-F5."""
    rounds = candidate_queries.candidate_rounds(cursor)
    if not rounds:
        raise IndexUnavailable("the index has no candidates in any round")
    return rounds


def _office_rounds(
    cursor: duckdb.DuckDBPyConnection, uf: str, office: str, published: tuple[int, ...]
) -> tuple[int, ...]:
    """The rounds in which (``uf``, ``office``) has a row; an office with no row at all
    (an empty list in every round) falls back to the published rounds, never empty."""
    return candidate_queries.office_rounds(cursor, uf, office) or published


def _candidacy(
    cursor: duckdb.DuckDBPyConnection, lookup: int | tuple[str, str, int]
) -> candidate_queries.Candidacy | None:
    """The candidacy the lookup names, with the rounds of codebase-design 3.4: by
    ``sq_candidato`` the rounds it appears in, by the trio the rounds with an on-ballot
    candidacy of that number. Null when there is none (a number held only off the ballot
    included)."""
    if isinstance(lookup, int):
        return candidate_queries.candidacy(cursor, lookup)
    uf, office, number = lookup
    rounds = candidate_queries.on_ballot_rounds_by_number(cursor, uf, office, number)
    if not rounds:
        return None
    return candidate_queries.Candidacy(uf, office, rounds)


def _round_warnings(resolution: RoundResolution | None) -> list[str]:
    if resolution is None or resolution.warning is None:
        return []
    return [resolution.warning]


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
        photo_url=row.photo_url,
    )


def _candidate_lookup(
    sq_candidato: object, uf: object, office: object, number: object
) -> int | tuple[str, str, int]:
    """Either the ``sq_candidato`` or the normalized trio (``uf``, ``office``, ``number``);
    both, neither or a partial trio are ``InvalidQuery``."""
    trio_given = [value is not None for value in (uf, office, number)]
    if sq_candidato is not None:
        if any(trio_given):
            raise InvalidQuery("informe sq_candidato ou o trio uf, office e number, não os dois")
        return normalize_number(sq_candidato, "sq_candidato inválido")
    if not all(trio_given):
        raise InvalidQuery("informe sq_candidato ou o trio completo: uf, office e number")
    uf_value = normalize_candidate_uf(uf)
    office_value = normalize_ballot_office(office)
    check_office_for_uf(office_value, uf_value)
    return uf_value.value, office_value.value, normalize_number(number, "número inválido")


def _fetch_profile(
    cursor: duckdb.DuckDBPyConnection, lookup: int | tuple[str, str, int], round: int
) -> CandidateProfileRow | None:
    if isinstance(lookup, int):
        return candidate_queries.get_candidate(cursor, lookup, round)
    return candidate_queries.get_candidate_by_number(cursor, *lookup, round)


def _rounds_for_not_found(
    cursor: duckdb.DuckDBPyConnection,
    lookup: int | tuple[str, str, int],
    published: tuple[int, ...],
) -> tuple[int, ...]:
    """The rounds a not-found answer refers to: the office's by the trio, the published
    ones otherwise. Never empty."""
    if isinstance(lookup, tuple):
        return _office_rounds(cursor, lookup[0], lookup[1], published)
    return published


def _ticket_offices(office: Office) -> tuple[str, ...]:
    """The offices of the ticket ``office`` belongs to, head first: a ballot office and the
    ones whose ``ticket_head`` it is. Empty for an office that has no ticket (deputies)."""
    head = office.ticket_head
    members = [head, *(o for o in Office if o.ticket_head is head and o is not head)]
    if len(members) == 1:
        return ()
    return tuple(o.value for o in members)


def _candidate_profile(
    row: CandidateProfileRow, mates: list[RunningMateRow], links: list[str], page_url: str | None
) -> CandidateProfile:
    federation = None
    if row.federation_acronym is not None:
        federation = FederationDetail(
            acronym=row.federation_acronym,
            name=row.federation_name or "",
            composition=row.federation_composition,
        )
    coalition = None
    if row.coalition_name is not None:
        coalition = CoalitionDetail(name=row.coalition_name, composition=row.coalition_composition)
    return CandidateProfile(
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
        photo_url=row.photo_url,
        round=row.round,
        social_name=row.social_name,
        nomination_kind=row.nomination_kind,  # type: ignore[arg-type]
        gender=row.gender,
        race_color=row.race_color,
        marital_status=row.marital_status,
        education=row.education,
        running_mates=[
            RunningMate(
                sq_candidato=mate.sq_candidato,
                office=mate.office,  # type: ignore[arg-type]
                ballot_name=mate.ballot_name,
                name=mate.name,
                party=Party(
                    number=mate.party_number, acronym=mate.party_acronym, name=mate.party_name
                ),
            )
            for mate in mates
        ],
        social_links=links,
        divulgacandcontas_url=page_url,
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


def _normalize_near(value: object) -> tuple[float, float] | None:
    if value is None:
        return None
    try:
        point = value if isinstance(value, Near) else Near.model_validate(value)
    except ValidationError as exc:
        raise InvalidQuery(
            "coordenadas inválidas: near precisa de latitude (-90 a 90) e longitude (-180 a 180)"
        ) from exc
    return point.latitude, point.longitude


def _resolve_municipality_in_uf(
    cursor: duckdb.DuckDBPyConnection, text: str, uf: str
) -> tuple[MunicipalityRow | None, list[MunicipalityRow]]:
    """One municipality of ``uf`` from a TSE code or a name, or the candidates when ambiguous.

    A code is digits only. A name resolves when it matches exactly once, or when it
    matches a single candidate at all; several candidates without an exact match are
    the ambiguity the caller reports with ``options``.
    """
    if text.isdigit():
        return get_municipality(cursor, text.zfill(5), uf), []
    candidates = search_municipalities(cursor, text, uf, MAX_LIMIT)
    exact = [row for row in candidates if row.score == 1.0]
    if len(exact) == 1:
        return exact[0], []
    if len(candidates) == 1:
        return candidates[0], []
    return None, candidates


def _municipality_not_found(options: list[MunicipalityRow]) -> NotFound:
    if not options:
        return NotFound(reason="municipio_nao_encontrado", guidance=MUNICIPALITY_NOT_FOUND_GUIDANCE)
    return NotFound(
        reason="municipio_ambiguo",
        guidance=MUNICIPALITY_AMBIGUOUS_GUIDANCE,
        options=[_municipality_match(row) for row in options],
    )


def _municipality_match(row: MunicipalityRow) -> MunicipalityMatch:
    return MunicipalityMatch(
        tse_code=row.tse_code, ibge_code=row.ibge_code, name=row.name, uf=row.uf, score=row.score
    )


def _place_list_item(row: PlaceRow, *, with_distance: bool) -> PollingPlaceListItem:
    fields: dict[str, object] = dict(
        number=row.number,
        zone=row.zone,
        name=row.name,
        kind=row.kind,
        address=row.address,
        neighborhood=row.neighborhood,
        postal_code=row.postal_code,
        phone=row.phone,
        latitude=row.latitude,
        longitude=row.longitude,
        status=row.status,
        section_count=row.section_count,
        accessible_section_count=row.accessible_section_count,
        voters=row.voters,
    )
    if with_distance:
        # Set explicitly, even when null, so the field is serialized only with `near`.
        fields["distance_km"] = row.distance_km
    return PollingPlaceListItem(**fields)  # type: ignore[arg-type]
