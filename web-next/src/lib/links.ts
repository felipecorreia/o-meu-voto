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

/**
 * The "Código aberto" link of the shell footer (casca spec, 5.5). The spec allows only a URL
 * the project already publishes (package.json `repository`, the web-next README or the old
 * footer) and forbids a provisional one; none exists while the repository is private, so the
 * button stays hidden until a public repository URL goes here.
 */
export const REPO_URL: string | null = null;
