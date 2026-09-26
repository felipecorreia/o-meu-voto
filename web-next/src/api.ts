// The REST envelope of the service (codebase-design section 8) and typed fetchers. Read only.
const META = document.querySelector('meta[name="br-elections-api-base"]') as HTMLMetaElement | null;
export const API_BASE = (META?.content || '/api/v1').replace(/\/$/, '');

export interface Party { number: number; acronym: string; name: string }
export interface Federation { acronym: string; name: string; composition?: string | null }
export interface Coalition { name: string; composition?: string | null }
export interface CandidateListItem {
  sq_candidato: number; number: number; ballot_name: string; name: string; office: string; party: Party;
  federation: Federation | null; coalition: Coalition | null; adjudication_status: string; on_ballot: boolean;
  occupation: string | null; photo_url: string | null;
  /** NM_TIPO_DESTINACAO_VOTOS as the TSE publishes it ('Válido', 'Anulado sub judice', ...); null when not informed. */
  vote_destination: string | null;
}
export interface RunningMate { sq_candidato: number; office: string; ballot_name: string; name: string; party: Party }
export interface CandidateProfile extends CandidateListItem {
  round: number; social_name: string | null; nomination_kind: string;
  gender: string | null; race_color: string | null; marital_status: string | null; education: string | null;
  running_mates: RunningMate[]; social_links: string[]; divulgacandcontas_url: string | null;
}
export interface Source {
  kind: string; dataset?: string; dataset_url?: string; file?: string; generated_at?: string; index_built_at?: string;
  age_hours?: number; stale?: boolean; license: string; attribution: string; calendar_source?: string; verified_at?: string;
}
export interface ElectionInfo { id: string; name: string; round: {number: number; date: string}; voting_hours: {start: string; end: string; timezone: string; label: string} }
export interface MunicipalityMatch { tse_code: string; ibge_code: number | null; name: string; uf: string; score: number }
export interface NotFound { reason: string; guidance: string; options?: MunicipalityMatch[] | null }
export interface Envelope<T> { data: T | null; not_found: NotFound | null; warnings: string[]; election: ElectionInfo | null; source: Source }

export interface CandidatesData { round: number; candidates: CandidateListItem[]; total: number; limit: number; offset: number }
export interface CandidateData { candidate: CandidateProfile }

/** compare_candidates (codebase-design 8.7): the list fields plus the alliance, the ticket, the
 *  links and the 2026 declared-asset total, never gender, race/color, marital status or education. */
export interface ComparedAssets { state: 'declarados' | 'declarou_nao_possuir' | 'sem_informacao'; total: number | null }
export interface ComparedCandidate extends CandidateListItem {
  social_name: string | null; nomination_kind: string; vote_destination_note: string | null;
  running_mates: RunningMate[]; social_links: string[]; divulgacandcontas_url: string | null; assets: ComparedAssets;
}
export interface MissingCandidacy { requested: number; reason: 'nao_encontrado' | 'fora_da_urna' | 'fora_do_turno' }
export interface ComparisonData {
  round: number; uf: string; office: string;
  /** Always in ballot-number order, as the service answers them. */
  candidates: ComparedCandidate[]; missing: MissingCandidacy[]; assets_note: string; assets_source: Source;
}
export interface PollingPlace {
  number: number; name: string; kind: string; address: string; neighborhood: string; postal_code: string; phone: string | null;
  latitude: number | null; longitude: number | null; status: string; section_count: number; accessible_section_count: number;
  zone?: number; voters?: number; distance_km?: number | null;
}
export interface PollingPlaceData {
  municipality: {tse_code: string; ibge_code: number | null; name: string; uf: string}; round: number; zone: number; section: number;
  section_kind: string; votes_at_section: number; voters_in_section: number; accessibility: string; place: PollingPlace;
  previous_place: {number: number; name: string; address: string} | null;
}
export interface PollingPlacesData { round: number; municipality: PollingPlaceData['municipality']; places: PollingPlace[]; total: number; guidance?: string | null }
export interface MunicipalitiesData { municipalities: MunicipalityMatch[] }
export interface ElectionData {
  id: string; name: string; rounds: Array<{number: number; date: string; note: string | null}>;
  voting_hours: {start: string; end: string; timezone: string; label: string};
  next_round: {number: number; date: string; note: string | null} | null; days_until_next_round: number | null;
  offices: string[]; notes: string[]; calendar_source: {title: string; url: string; verified_at: string};
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

type Param = string | number | boolean | null | undefined;

/** An array value repeats the parameter (`sq=1&sq=2`), as the compare endpoint expects. */
export async function callApi<T>(path: string, params: Record<string, Param | Param[]> = {}): Promise<Envelope<T>> {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    for (const item of Array.isArray(v) ? v : [v]) if (item !== undefined && item !== null && item !== '') q.append(k, String(item));
  }
  const url = `${API_BASE}${path}${q.toString() ? `?${q}` : ''}`;
  const res = await fetch(url, {headers: {Accept: 'application/json'}});
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const j = await res.json(); if (typeof j.detail === 'string') detail = j.detail; else if (Array.isArray(j.detail)) detail = j.detail.map((d: {msg: string}) => d.msg).join('; '); } catch { /* keep detail */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<Envelope<T>>;
}

export const api = {
  election: (on?: string) => callApi<ElectionData>('/election', {on}),
  candidates: (p: {uf: string; office: string; name?: string; party?: string; on_ballot_only?: boolean; limit?: number; offset?: number; round?: string}) =>
    callApi<CandidatesData>('/candidates', {...p, on_ballot_only: p.on_ballot_only === false ? 'false' : undefined}),
  candidate: (sq: number, round?: string) => callApi<CandidateData>(`/candidates/${sq}`, {round}),
  candidateByNumber: (p: {uf: string; office: string; number: string; round?: string}) => callApi<CandidateData>('/candidates/by-number', p),
  compare: (p: {uf: string; office: string; sq: number[]; round?: string}) => callApi<ComparisonData>('/candidates/compare', p),
  pollingPlace: (p: {uf: string; zone: string; section: string; round?: string}) => callApi<PollingPlaceData>('/polling-place', p),
  pollingPlaces: (p: {uf: string; municipality: string; neighborhood?: string; query?: string; lat?: string; lon?: string; limit?: number}) =>
    callApi<PollingPlacesData>('/polling-places', p),
  municipalities: (name: string, uf?: string, limit = 8) => callApi<MunicipalitiesData>('/municipalities', {name, uf, limit}),
};
