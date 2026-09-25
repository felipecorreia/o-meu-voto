# web-next: the comparison page (React + Astryx, CDE 2026 identity)

The next shell of the public page, comparison first: choose UF and office, mark 2 to 4
candidacies, read them side by side; then the candidate profile, the FAQ and, as an appendix,
the where-to-vote searches (my polling place, places by city, election dates). Built with Vite,
React 19 and `@astryxdesign/core` (Astryx, beta) on the TSE "CDE 2026" colour pattern, and
reviewed by the captain on 2026-09-25 (design review report:
`[private]`). It lands as reviewed; `web/` stays the deployed
static page until this one replaces it (ADR 0005 keeps the page on Cloudflare Pages).

Identifiers are English, UI copy is PT-BR.

## Run it

Node 22 or newer (the Astryx CLI's floor).

```sh
cd web-next
npm ci
npm run dev          # http://localhost:5199
npm run build        # tsc -b && vite build -> dist/
```

The page calls the API on the same origin (`<meta name="br-elections-api-base"
content="/api/v1">` in `index.html`, read by `src/api.ts`). In dev, Vite proxies `/api/v1` to
`BR_ELECTIONS_API_ORIGIN`, read from the environment or from `web-next/.env` (git-ignored),
default `http://127.0.0.1:8000`, the local run of `docs/local-run.md`:

```sh
BR_ELECTIONS_API_ORIGIN=http://127.0.0.1:8080 npm run dev   # e.g. the compose.yaml container
```

In production nothing is proxied: Cloudflare Pages serves `dist/` and routes `/api/*` to the
service (`docs/deploy-runbook.md`), so `wrangler pages deploy web-next/dist` is the deploy step.
`_redirects` or `_headers` belong in `public/` so Vite copies them into `dist/`.

## Routes (hash router, `src/router.ts`)

| Route | Page | Notes |
|---|---|---|
| `#/` | Compare (home) | UF + office selectors, name and party filters, "incluir fora da urna", add by ballot number; the marked set lives in the URL (`sq=`), so a comparison is a link |
| `#/?uf=&office=&sq=a,b,c` | Comparison | `CompareGrid`, tabs layout (below) |
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
placeholder when absent).

## What is not real yet

`src/mock.ts` fills three rows the API does not serve: the vote destination (derived from the
registration status), the declared assets of 2026 and their evolution (static figures from the
comparator research, presidente only). Every such cell carries the "simulado" tag, the
destination wording also "texto provisório". Follow-up: wire the page to the
`compare_candidates` API (branch `fm/bre-comparador-v1`) and delete `mock.ts`; the row renderers
stay.

Review switches still in the code, as query parameters: `?theme=matcha|butter` (outside the
hash; Butter + CDE is the default), `layout=pair|columns|stacked` (tabs is the default),
`dest=badge|sentence|both`, `growth=line|timeline`, `status=neutral`, `photos=demo`
(`public/photo-sample.svg`, a labelled sample). Follow-up: drop the losing options, the Matcha
theme and the switcher in the top nav.

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

## Astryx 0.6.3 notes (pinned exactly; beta)

- `Theme` and `defineTheme` come from `@astryxdesign/core/theme`; overriding `--color-accent`
  does not re-point `--color-on-accent` (set explicitly).
- The theme is injected at runtime (Astryx warns about it in dev). For production, build it once
  with `npx astryx theme build src/themes/cde.ts -o <file>` and import the CSS (follow-up).
- Content components emit hashed StyleX classes only; page CSS that must reach inside one
  (`src/styles.css`) targets a wrapper the page owns. Layout components do carry stable classes
  (`.astryx-app-shell-header`).
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

1. Wire `compare_candidates` and remove `mock.ts`.
2. Drop the review switches and the Matcha theme; ship one pre-built theme.
3. CI: a Node 22 job running `npm ci`, `npx tsc -p tsconfig.json` and `npm run build`; a
   counterpart of `tests/test_web.py` for the built page.
4. Self-host Inter (`public/fonts/`) instead of Google Fonts.
5. Candidate photos once the R2 mirror exists (`photo_url`).
6. An ARIA pass on the grid roles; occupation casing at index build (`_CASED_COLUMNS`).
7. Bundle: 824 KB minified / 240 KB gzip of JS today (react-dom, Astryx i18n and theme engine
   are the bulk); lazy chunks for the appendix pages and the pre-built theme bring it down.
