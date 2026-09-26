# web-next: the comparison page (React + Astryx, CDE 2026 identity)

The next shell of the public page, comparison first: choose UF and office, mark 2 to 4
candidacies, read them side by side; then the candidate profile, the FAQ and, as an appendix,
the where-to-vote searches (my polling place, places by city, election dates). Built with Vite,
React 19 and `@astryxdesign/core` (Astryx, beta) on the TSE "CDE 2026" colour pattern, and
reviewed by the captain on 2026-09-25 (design review report:
`[private]`). It is the page Cloudflare Pages publishes (ADR
0005), with the edge function next to it (below); `web/`, the old six-card page, is no longer
deployed and waits for its removal.

Identifiers are English, UI copy is PT-BR.

## Run it

Node 22 or newer (the Astryx CLI's floor).

```sh
cd web-next
npm ci
npm run dev          # http://localhost:5199
npm run build        # tsc -b && vite build -> dist/
npm test             # vitest: src/lib/*.test.ts (title case, slot colours, exit-link order)
```

The page calls the API on the same origin (`<meta name="br-elections-api-base"
content="/api/v1">` in `index.html`, read by `src/api.ts`). In dev, Vite proxies `/api/v1` to
`BR_ELECTIONS_API_ORIGIN`, read from the environment or from `web-next/.env` (git-ignored),
default `http://127.0.0.1:8000`, the local run of `docs/local-run.md`:

```sh
BR_ELECTIONS_API_ORIGIN=http://127.0.0.1:8080 npm run dev   # e.g. the compose.yaml container
```

In production nothing is proxied by Vite: Cloudflare Pages serves `dist/` and its function
routes `/api/*` and `/mcp` to the service (next section).

## Deploy and the Pages edge

Three files make the Pages edge (ADR 0005, `docs/deploy-runbook.md` step D0), one copy each:

- `functions/[[path]].js`: a Pages Function that proxies `/api/*` and `/mcp` to the Cloud Run
  service, so the page and the API share one origin. It reads two Pages secrets: `ORIGIN_URL`
  (the `run.app` URL) and `EDGE_SECRET` (optional, sent to the service as `x-edge-secret`). It
  answers `GET /mcp` itself with `405`, so an idle MCP event stream never holds a Cloud Run
  instance, and asks the edge for a 60 s cache on REST `GET`s except those carrying `lat` or
  `lon` (ADR 0004).
- `public/_routes.json`: only `/api/*` and `/mcp` invoke the function; every other request is a
  static asset, free on Pages. `/healthz` is not routed, so it answers only on `run.app`. A
  future function (the Jev box of ADR 0006) needs its path added here.
- `public/404.html`: without it Pages treats the site as a single-page app and answers every
  unknown path, the MCP OAuth discovery probes (`/.well-known/oauth-*`) included, with `200`
  and `index.html`. The page's own routes are in the hash, so it needs no fallback.

Vite copies `public/` into `dist/`; wrangler reads `functions/` from the directory it runs in.
So the deploy is the build plus one command, from this directory (step D3 of the runbook):

```sh
npm ci && npm run build
npx wrangler pages deploy dist --project-name="$PAGES_PROJECT" --branch=main
```

The same edge runs locally in front of a local service, no Cloudflare account needed:

```sh
uv run python -m br_elections_mcp.app --index-dir data/index --port 8791   # repo root
npm run build && npx wrangler pages dev dist --port 8788 --binding ORIGIN_URL=http://127.0.0.1:8791
scripts/smoke.sh http://localhost:8788 http://localhost:8791                # repo root
```

`tests/test_web.py` checks the route list, the 404 page and that `web/` holds no second copy,
and runs the function under Node with a stub `fetch`. CI (`.github/workflows/ci.yml`, job
`web-next`) runs `npm ci`, `npm run build` and `npm test` on Node 22, so a type error, a broken
build or a failing utility test fails the PR, and checks that `_routes.json` and `404.html`
reach `dist/`.

## Routes (hash router, `src/router.ts`)

| Route | Page | Notes |
|---|---|---|
| `#/` | Compare (home), choice mode | State pill (the Astryx Selector, bottom sheet on phones), office tabs with a sliding highlight, one search field (name, party acronym or ballot number: 2 to 5 digits go to `by-number` and head the list, a short text with no name match is retried as `party`), the "Incluir fora da urna" chip, whole-card buttons, the floating tray; the marked set lives in the URL (`sq=`, in the order of marking), so a comparison is a link. Tela 1 of the redesign (spec in `[private]`): the reusable pieces in `src/components/cv/` and `src/lib/` (below), the page-only ones in `src/components/Picker.tsx` |
| `#/?uf=&office=&sq=a,b,c` | Comparison | one `GET /api/v1/candidates/compare?sq=a&sq=b&sq=c`; `CompareGrid`, tabs layout (below) |
| `#/candidato/:sq` | Profile | ADR 0004 fields only here, collapsed |
| `#/duvidas` | FAQ | `?abrir=<id>` opens one item; draft copy, marked as such |
| `#/onde-voto`, `#/locais`, `#/quando` | Appendix | polling place by zone and section, places by city, election dates |

The comparison (`src/components/CompareGrid.tsx`, captain's choices of 2026-09-25): columns
ordered by ballot number, never ranked, no party colours, no bars or percentages; on phones
exactly two columns chosen from the marked set through a chip row and a per-column swap
(`pair=` in the URL), every column on wider screens; three sections as Astryx tabs with lucide
icons, Chapa e registro, Patrimônio (2026 total, evolution row collapsed behind "Ver
evolução"), Ocupação e transparência (`tab=` in the URL); registration badges neutral in the
comparison and coloured in the picker and the profile; vote destination as a neutral badge plus
one explanatory line; a 3:4 photo slot of one size in every column (`photo_url`, neutral
placeholder when absent or when the image fails to load).

## Where the data comes from

Every value is the API's (codebase-design 8.7 for the comparison): the vote destination and its
one-line note, the 2026 declared-asset total (`assets.state`, `assets.total`), the photo, the
candidacies the service left out (`missing[]`, named in a notice) and both sources (candidates
and assets file) in the footer. The page owns only labels and two texts: the assets caveat
(the service's `assets_note` names an API field for MCP clients) and the wording of
`candidaturas_insuficientes`. The picker uses `GET /candidates` and `GET /candidates/by-number`,
the profile `GET /candidates/{sq}` (destination without its note, no assets: see the comparison).

Not served yet, and shown as such: the evolution of the declared assets (ADR 0009), a row
tagged "em preparação" with one line across the columns and nothing invented; the FAQ says the
same. When it lands, the captain's choice is to collapse it behind "Ver evolução".

Review switches still in the code, as query parameters: `?theme=matcha|butter` (outside the
hash; Butter + CDE is the default), `layout=pair|columns|stacked` (tabs is the default),
`dest=badge|sentence|both`, `status=neutral`, `photos=demo` (`public/photo-sample.svg`, a
labelled sample). Follow-up: drop the losing options, the Matcha theme and the switcher in the
top nav, which is still visible.

## Theme

`src/themes/cde.ts` defines two themes with `defineTheme({extends})` over the scaffolded
`butter` and `matcha` example themes (`npx astryx theme add <slug>`), overriding tokens and
component targets, never component source. Identity tokens: navy #1B305A as accent and body
text, the portal's neutral backgrounds, success #1F7F47 (the CTA green darkened for small
text), warning #FFDA59 / #061937, error #CD201F, the four CDE hues as categorical tints with
darkened text, Inter with headings at weight 500. Rules of the palette's accessibility section:
gold and CDE blue never as text on white; colours never mapped to parties; no TSE logo, name or
seal; the "projeto independente, não oficial, com dados abertos do TSE" notice in the header,
the footer and the FAQ. Contrast pairs are listed in the design review report.

The redesigned screens (Tela 1, the choice mode of the Comparar page, today) add their own
layer on top, the `cv` scope: the `--cv-*` tokens of the spec's section 4.1 (`cvTokens` in
`src/themes/cde.ts`, set as CSS variables on the `.cv-page` container and read by the `.cv-page`,
`cv-*` and `.pick` blocks of `src/styles.css`, never as a loose hex in a component), Plus Jakarta
Sans loaded in `index.html` and applied only in that scope (the Astryx font tokens are re-pointed
there so Banner, EmptyState and the Selector follow), green for choice and action, yellow for the
highlight, petrol blue as support, `--cv-surface-2` for empty states and neutral notes.

The pieces the next screens reuse are separate components and utilities, not page code:

| Piece | Where | What |
|---|---|---|
| `StatePill` | `src/components/cv/StatePill.tsx` | the Astryx Selector restyled as the 64 px pill; sheet title "Escolha o estado" |
| `SlidingTabs` | `src/components/cv/SlidingTabs.tsx` | a radiogroup on a rail with the sliding highlight; `options`, `value`, `onChange`, `ariaLabel` |
| `CandidateCard` | `src/components/cv/CandidateCard.tsx` | the whole-card `<button aria-pressed>` |
| `CvAvatar` | `src/components/cv/CvAvatar.tsx` | initials or photo; `size`, `slot` (1 to 4) paints it with the slot colour, `ring` for the tray |
| `NumberPill` | `src/components/cv/NumberPill.tsx` | the yellow ballot-number pill |
| `CompareTray` | `src/components/cv/CompareTray.tsx` | the floating tray |
| `toTitleCase` | `src/lib/titleCase.ts` | ballot name in title case, particles lower-cased |
| `slotColor(i)` | `src/lib/slotColor.ts` | `{bg, fg, tint}` of marking slot `i`, as `var(--cv-*)` references |
| `compareParams`, `MIN_MARKED`, `MAX_MARKED` | `src/lib/marking.ts` | the exit link (`sq` in the order of marking) and the 2..4 rule |

The slot colours (and so the tray avatars, and the comparison screen when it reuses them) follow
the order of marking, never the candidacy or the party (ADR 0008); `sq` in the exit URL keeps
that order so the next screen can repeat the colours. The choice screen words every error, empty
and not-found state with the phrases of the spec's section 5.11 and never shows
`not_found.reason`, the service's `guidance` or an HTTP detail; `warnings[]` keep the service
text. Layout: one column under 640 px (the prints), two columns and a 32 px gutter from 640 px,
and from 1024 px a 1120 px content width, the pill and the tabs on one line, the search with the
chip beside it, three columns of cards that keep their own height, the tray 560 px wide and 24 px
from the bottom, and a hover border (fine pointers only) on unmarked cards.

## Astryx 0.6.3 notes (pinned exactly; beta)

- `Theme` and `defineTheme` come from `@astryxdesign/core/theme`; overriding `--color-accent`
  does not re-point `--color-on-accent` (set explicitly).
- The theme is injected at runtime (Astryx warns about it in dev). For production, build it once
  with `npx astryx theme build src/themes/cde.ts -o <file>` and import the CSS (follow-up).
- Content components emit hashed StyleX classes only; page CSS that must reach inside one
  (`src/styles.css`) targets a wrapper the page owns. Layout components do carry stable classes
  (`.astryx-app-shell-header`).
- The Selector's trigger container does carry a stable class (`.astryx-selector`, with
  `.astryx-icon` on its chevron and `.astryx-field` around it), and Astryx CSS sits in
  `@layer astryx-base`/`astryx-theme`, so unlayered page CSS restyles it without `!important`:
  the state pill of the choice mode is the Selector itself (`renderValue` draws the pill's
  content, `aria-label` reaches the trigger button), not a rewrite of the bottom sheet.
- `AppShell height="auto"` so the document scrolls (the default is an inner scroll container).
- `TabList`/`Tab`: `label` is a string and doubles as the accessible name; three tabs with icons
  need the phone's shorter labels to fit 390 px.
- pt-BR component strings: `InternationalizationProvider` with `locales/pt-BR.json` (about
  210 KB minified of message formatting in the bundle).
- lucide-react no longer ships brand glyphs; the social icons are inline SVGs
  (`src/components/brandIcons.tsx`).
- The Astryx CLI's generated `AGENTS.md` is not kept: its rules (no `div`, no hex or px) do not
  match how this page is built; this README is the guide.

## Follow-ups after landing

1. Remove `web/` (the old page, no longer deployed) and its `--web-dir` tests.
2. Drop the review switches and the Matcha theme; ship one pre-built theme.
3. The asset evolution row, once the service serves it.
4. Self-host Inter (`public/fonts/`) instead of Google Fonts.
5. Candidate photos once the R2 mirror exists (`photo_url`).
6. An ARIA pass on the grid roles; occupation casing at index build (`_CASED_COLUMNS`).
7. Bundle: 821 KB minified / 239 KB gzip of JS today (react-dom, Astryx i18n and theme engine
   are the bulk); lazy chunks for the appendix pages and the pre-built theme bring it down.
8. The profile's "Comparar com outras" link carries no UF for a state race (the profile answer
   has no `uf`), so the picker opens on the default UF.
