// Formatting the page owns. Data values are rendered as the API returns them (casing is the
// service's job); here we only join, normalise URLs and format dates and codes.

/** Joins address parts with ", " skipping empty ones: no double commas (local-review finding). */
export function joinAddress(...parts: Array<string | null | undefined>): string {
  return parts.map(p => (p ?? '').trim()).filter(Boolean).join(', ');
}

export function cep(s: string | null | undefined): string {
  return s && /^\d{8}$/.test(s) ? `${s.slice(0, 5)}-${s.slice(5)}` : (s ?? '');
}

/** The TSE ships social URLs in upper case ("HTTPS://WWW.INSTAGRAM.COM/FULANO/"). Lower-case the
 *  scheme and host, keep the path's case (handles are case-insensitive on every network we link
 *  to, but the path may carry a mixed-case slug), add https:// when the scheme is missing.
 *  Only http(s) URLs become links (local-review finding). */
/** The TSE ships social URLs in upper case ("HTTPS://WWW.INSTAGRAM.COM/FULANO/"). Lower-case the
 *  scheme and host, decode and lower-case the path (handles are case-insensitive on every network
 *  we link to), add https:// when the scheme is missing, and only turn http(s) URLs into links
 *  (local-review finding). A bare "@handle.bsky.social" stays text: no host to link to. */
const PATH_PREFIXES = new Set(['user', 'channel', 'c', 'u', 'people', 'pages', 'profile', 'profile.php', 'es', 'en', 'pt', 'pt-br', 'photos', 'p', 'show', 'hashtag', 'in', 'company', 'groups', 'watch', 'playlist', 'video', 'videos', 'home', 'r', 'id']);
export function normalizeSocialUrl(raw: string): {href: string | null; label: string} {
  let s = String(raw ?? '').trim();
  if (!s) return {href: null, label: ''};
  if (!/^https?:\/\//i.test(s)) {
    if (/^(www\.)?[a-z0-9.-]+\.[a-z]{2,}(\/|$)/i.test(s)) s = `https://${s}`;
    else return {href: null, label: s.toLowerCase()};
  }
  try {
    const u = new URL(s);
    u.protocol = u.protocol.toLowerCase();
    u.hostname = u.hostname.toLowerCase();
    let path = u.pathname;
    try { path = decodeURIComponent(path); } catch { /* keep as is */ }
    path = path.toLowerCase();
    u.pathname = path;
    const host = u.hostname.replace(/^www\./, '');
    const segs = path.replace(/\/+$/, '').split('/').filter(Boolean);
    // The handle is the first "@x" segment, else the segment after a known prefix, else the first one.
    let handle = segs.find(x => x.startsWith('@'));
    if (!handle) {
      const i = segs.findIndex(x => !PATH_PREFIXES.has(x));
      handle = i >= 0 ? segs[i] : undefined;
    }
    const label = handle ? `${handle.startsWith('@') ? '' : '@'}${handle}` : host;
    return {href: u.toString(), label};
  } catch {
    return {href: null, label: s};
  }
}

export function socialNetwork(href: string): 'instagram' | 'facebook' | 'x' | 'youtube' | 'tiktok' | 'kwai' | 'threads' | 'site' {
  const h = href.toLowerCase();
  if (h.includes('instagram.com')) return 'instagram';
  if (h.includes('facebook.com') || h.includes('fb.com')) return 'facebook';
  if (h.includes('twitter.com') || /https?:\/\/(www\.)?x\.com/.test(h)) return 'x';
  if (h.includes('youtube.com') || h.includes('youtu.be')) return 'youtube';
  if (h.includes('tiktok.com')) return 'tiktok';
  if (h.includes('kwai.com')) return 'kwai';
  if (h.includes('threads.')) return 'threads';
  return 'site';
}

const dateOf = (iso: string) => { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d); };
export const fmtDateLong = (iso: string) =>
  new Intl.DateTimeFormat('pt-BR', {day: 'numeric', month: 'long', year: 'numeric'}).format(dateOf(iso));
export const fmtWeekday = (iso: string) => new Intl.DateTimeFormat('pt-BR', {weekday: 'long'}).format(dateOf(iso));
export const fmtDateShort = (iso: string) => { const [y, m, d] = iso.split('-'); return `${d}/${m}/${y}`; };
export const fmtStamp = (iso: string) =>
  new Intl.DateTimeFormat('pt-BR', {dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo'}).format(new Date(iso)) + ' (Brasília)';
export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
export const gmapsUrl = (lat: number, lon: number) => `https://www.google.com/maps/search/?api=1&query=${lat}%2C${lon}`;
export const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase();
