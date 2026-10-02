// Copied from SECTION_NOT_FOUND_GUIDANCE in core/core.py; never parse service guidance.
export const TSE_ONDE_VOTAR_URL = 'https://www.tse.jus.br/servicos-eleitorais/autoatendimento-eleitoral#/atendimento-eleitor/onde-votar';
// The TSE site, for the calendar and the results (Tela 6 spec, exception 2).
export const TSE_SITE_URL = 'https://www.tse.jus.br/';

/** Coordinates take precedence. With no coordinates, use the address and municipality. */
export function mapsUrl(place: {latitude: number | null; longitude: number | null; address: string; neighborhood: string; municipality?: {name: string; uf: string}}): string {
  const query = place.latitude != null && place.longitude != null
    ? `${place.latitude},${place.longitude}`
    : [place.address, place.neighborhood, place.municipality ? `${place.municipality.name} - ${place.municipality.uf}` : ''].filter(Boolean).join(', ');
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

/** The public mirror of this repository: the footer's "Código aberto" and the menu item. */
export const REPO_URL: string | null = 'https://github.com/felipecorreia/o-meu-voto';
/** The author's GitHub profile, linked from the footer credit. */
export const AUTHOR_URL = 'https://github.com/felipecorreia';
