# web-next: the comparison page (React + Astryx, CDE 2026 identity)

The public page, comparison first: choose UF and office, mark 2 to 4
candidacies, read them side by side; then the candidate profile, the FAQ, where to vote (my
polling place), places by city and election dates. Built with Vite,
React 19 and `@astryxdesign/core` (Astryx, beta) on the TSE "CDE 2026" colour pattern, and
reviewed by the captain on 2026-09-25 (design review report kept outside the repository). It is
the page Cloudflare Pages publishes (ADR 0005), with the edge function next to it (below).

Identifiers are English, UI copy is PT-BR.

## Run it

Node 22 or newer (the Astryx CLI's floor).

```sh
cd web-next
npm ci
npm run dev          # http://localhost:5199
npm run build        # tsc -b && vite build -> dist/
npm test             # vitest: marking, slots, pairs, comparison, profile, polling-place, places, election-date, FAQ and shell contracts
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

Three files make the Pages edge (ADR 0005, [`docs/architecture.md`](../docs/architecture.md)), one copy each:

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

The assistant setup instructions (issue #115) are static too, authored once in
`public/prompt-llm.md`. `npm run build` ends with `scripts/build-assistant-resources.mjs`, which
writes `dist/prompt-llm.txt` (the same text) and `dist/prompt-llm.html`, served at `/prompt-llm`:
the same text with every URL as a link, plus ready candidate-list links per UF and office,
because ChatGPT opens only URLs that appear as links on a page it read or in the user's message,
never URLs it builds. The text writes no full URL for a route the assistant must build
(`compare`, `by-number`, `polling-place(s)`, `municipalities`), only the route and its
parameters: Claude's reader answers a new URL with an already seen URL of the same path, even
one seen as plain text, and keeps one value per parameter name, hence `number=180,400` for a
comparison. `public/_headers` serves the `.md` and `.txt` as `text/plain` (ChatGPT
rejects `text/markdown`), and `public/robots.txt` replaces the rule-less content-signals file
Cloudflare serves when a site has none. `tests/test_assistant_resources.py` checks all of it.

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

`tests/test_web.py` checks the edge function is committed, the route list and the 404 page,
and runs the function under Node with a stub `fetch`. CI (`.github/workflows/ci.yml`, job
`web-next`) runs `npm ci`, `npm run build` and `npm test` on Node 22, so a type error, a broken
build or a failing utility test fails the PR, and checks that `_routes.json` and `404.html`
reach `dist/`.

## Routes (hash router, `src/router.ts`)

| Route | Page | Notes |
|---|---|---|
| `#/` | Compare (home), choice mode | State pill (the Astryx Selector, bottom sheet on phones), office tabs with a sliding highlight, one search field (name, party acronym or ballot number: 2 to 5 digits go to `by-number` and head the list, a short text with no name match is retried as `party`), the "Incluir fora da urna" chip, whole-card buttons, the floating tray; the marked set lives in the URL (`sq=`, in the order of marking), so a comparison is a link. Tela 1 of the redesign (spec kept outside the repository): the reusable pieces in `src/components/cv/` and `src/lib/` (below), the page-only ones in `src/components/Picker.tsx` |
| `#/?uf=&office=&sq=a,b,c` | Comparison | one `GET /api/v1/candidates/compare?sq=a&sq=b&sq=c`; `ComparisonBody`, reusable headers and rows (below) |
| `#/?uf=&office=&marcar=a,b,c` | Choice with preselection | loads available profiles in the written order, keeps successful results if another load fails, and preserves marks changed while loading; "Escolher outras" uses this route |
| `#/candidato/:sq` | Profile | Tela 3: direct links are neutral; `cmp` plus `uf`, `office`, `pair` and `tab` preserves comparison context and slot colour. Personal fields appear only in the collapsed panel |
| `#/duvidas` | FAQ | Tela 7: fixed content from `src/content/faq.ts` in four theme groups; `?abrir=<id>` opens one item, scrolls to it, flashes it and focuses it; chips scroll to the themes; each open answer has a copy-link button; draft copy, marked as such while `FAQ_DRAFT` is true |
| `#/onde-voto?uf=&zone=&section=[&round=1\|2]` | Where to vote | Tela 4: shared search/detail pieces, automatic search from valid links, form editing, client validation and safe problem states |
| `#/quando` | When | Tela 6: the election calendar with a hero driven by the Brasília civil day (countdown, voting day, closed, over), round tiles, hours strip, office chips, link sections and safe no-data/error states |
| `#/locais?uf=&mun=<tse_code>[&bairro=][&q=]` | Places by city | Tela 5: municipality suggestions, optional filters, alphabetic or nearby order, place cards and links to Onde voto and Maps |

The place-status badge is hidden on both polling-place routes until the TSE field's meaning is
understood (issue #45). Section and accessibility chips remain visible.

The comparison (Tela 2 spec, kept outside the repository) uses the page-only pieces in
`src/components/Comparison.tsx` and reusable headers, pair picker, rows and icon buttons
in `src/components/cv/`. Below 640 px, three or four candidacies show as a pair: "Trazer"
replaces the candidacy changed least recently, and a column's swap picks the next candidacy
off screen in ballot-number order, wrapping at the end. The pair is then put in ballot-number
order, as the spec requires; the untouched candidacy remains the older one even when it moves
columns. From 640 px every candidacy appears, with removal buttons when there are more than
two. Removing a candidacy from the pair recalculates `pair` for the two now shown. From
1024 px a 220 px label column precedes the values, within a 1120 px page.

The action bar and the column headers with `SlidingTabs` stay sticky; the shell header's
height (`useTopNavOffset`, 60 px at every width) puts them below it. The three tabs are Chapa,
Patrimônio and Ocupação (`tab=chapa|patrimonio|ocupacao`). `sq` retains marking order for slot
colours, while displayed columns always follow ballot numbers; `sq`, `pair` and `tab` update
with `replaceState`. Names link to the profile with the marking order in `cmp`, the race, pair
and current tab. "Escolher outras" keeps the state, office
and marked set through `marcar`; sharing uses `navigator.share`, with WhatsApp as fallback.
Registration badges are neutral. Assets show a compact total and its exact declared value;
photos occupy the shared circular `CvAvatar`, with initials when absent or when loading fails.
No ranking, party colours, bars, percentages or profile-only demographics.

## Where the data comes from

Every value is the API's (codebase-design 8.7 for the comparison): the vote destination and its
one-line note, the 2026 declared-asset total (`assets.state`, `assets.total`), the photo, the
candidacies the service left out (`missing[]`, named in a notice) and both sources (candidates
and assets file) in the footer. The page owns labels and explanatory texts: the assets caveat
(the service's `assets_note` names an API field for MCP clients) and the wording of
`candidaturas_insuficientes`. The picker uses `GET /candidates` and `GET /candidates/by-number`,
the profile `GET /candidates/{sq}` (no assets). The profile answer has neither a UF nor a
destination explanation: `src/lib/profile.ts` reads the electoral unit from the service-generated
DivulgaCandContas URL (the last fragment segment, per `core/divulgacandcontas.py`), falling back
to valid route context, and holds the exact `VOTE_DESTINATION_NOTES` explanations from
`core/core.py`. An unknown destination gets no invented explanation. A direct state profile
with neither an official URL nor route context still has no UF to recover; the current 2026
calendar provides the official URL.

Not served yet, and shown as such: the evolution of the declared assets (ADR 0009), a row
tagged "Em preparação" with a neutral panel across the values and nothing invented; the FAQ
says the same. Loading shows two column skeletons and four grey rows. Comparison errors and
not-found answers use only the exact Tela 2 phrases, never HTTP details, technical reason
codes or service guidance. Warnings retain the service's text. When a missing candidacy has no
profile name or number, its notice reads `Candidatura {sq}: não foi encontrada neste cargo e estado.`

The comparison's `layout` and `dest` review variants are removed; `status` and `photos` have
no effect on it. The header's theme switch is gone; Butter + CDE is the only theme. Choice and
profile use the shared cv status badges; the legacy `status=neutral` parameter no longer
changes them.

## Theme

`src/themes/cde.ts` defines one theme with `defineTheme({extends})` over the scaffolded
`butter` example theme (`npx astryx theme add <slug>`), overriding tokens and
component targets, never component source. Identity tokens: navy #1B305A as accent and body
text, the portal's neutral backgrounds, success #1F7F47 (the CTA green darkened for small
text), warning #FFDA59 / #061937, error #CD201F, the four CDE hues as categorical tints with
darkened text, Inter with headings at weight 500. Rules of the palette's accessibility section:
gold and CDE blue never as text on white; colours never mapped to parties; no TSE logo, name or
seal; "não oficial" in the header of every screen and the "Projeto independente e não oficial"
card once, in the shell footer (no screen repeats it). Contrast pairs are listed in the design review report.

The redesigned screens (Telas 1 to 7 and the shell) add their own layer on top, the `cv` scope
(`.cv-page` on each screen, `.cv-shell` on the frame): the `--cv-*` tokens of the spec's section 4.1 (`cvTokens` in
`src/themes/cde.ts`, set as CSS variables on the `.cv-page` container and read by the `.cv-page`,
`cv-*` and `.pick` blocks of `src/styles.css`, never as a loose hex in a component), Plus Jakarta
Sans loaded in `index.html` and applied only in that scope (the Astryx font tokens are re-pointed
there so Banner, EmptyState and the Selector follow), green for choice and action, yellow for the
highlight, petrol blue as support, `--cv-surface-2` for empty states and neutral notes.

The pieces the next screens reuse are separate components and utilities, not page code:

| Piece | Where | What |
|---|---|---|
| `StatePill` | `src/components/cv/StatePill.tsx` | the Astryx Selector restyled as the 64 px pill; optional icon, trailing glyph, label and options preserve defaults for choice mode |
| `SlidingTabs` | `src/components/cv/SlidingTabs.tsx` | a radiogroup with a sliding highlight; `fill` uses equal-width options below 1024 px; opt-in tab semantics, an associated label for the round selector and an optional per-option icon |
| `CandidateCard` | `src/components/cv/CandidateCard.tsx` | the whole-card `<button aria-pressed>` |
| `CvAvatar` | `src/components/cv/CvAvatar.tsx` | initials or photo; `size`, `slot` (1 to 4) paints it with the slot colour, `ring` for the tray |
| `NumberPill` | `src/components/cv/NumberPill.tsx` | the yellow ballot-number pill |
| `CompareTray` | `src/components/cv/CompareTray.tsx` | the floating tray, using the shared `FloatingBar` container |
| `toTitleCase` | `src/lib/titleCase.ts` | ballot name in title case, particles lower-cased |
| `slotColor(i)` | `src/lib/slotColor.ts` | `{bg, fg, tint}` of marking slot `i`, as `var(--cv-*)` references |
| `compareParams`, `MIN_MARKED`, `MAX_MARKED` | `src/lib/marking.ts` | the exit link (`sq` in the order of marking) and the 2..4 rule |
| `CompareColumnHeader` | `src/components/cv/CompareColumnHeader.tsx` | slot-tinted card, avatar, profile link, number and party, optional swap or removal |
| `PairPicker` | `src/components/cv/PairPicker.tsx` | "Na tela: 2 de N", one card per candidacy, column labels and pressed state |
| `CompareRow` | `src/components/cv/CompareRow.tsx` | labelled group, hints, named cells, neutral badges, link pills or a full-width note |
| `IconButton` | `src/components/cv/IconButton.tsx` | round 44 px button or link with an accessible name |
| `resolvePair`, `bringIn`, `swapNext` | `src/lib/pair.ts` | pair membership, oldest replacement, cycling and ballot order |
| `ProfileHero`, `StatusBadge` | `src/components/cv/` | slot-tinted or neutral profile hero; icon and exact registration term with shared status tokens, also used in choice mode |
| `DetailRow`, `LinkCard`, `FloatingBar` | `src/components/cv/` | labelled details, external link cards and the original tray container including safe area |
| `PrivateDataPanel` | `src/components/cv/PrivateDataPanel.tsx` | closed on every new profile; personal values mounted only when expanded in an associated region |
| `profileUf`, `profileNavigation`, `profileShare` | `src/lib/profile.ts` | race recovery, comparison return, `marcar` action and a direct share link without `cmp` |
| `InsetField`, `SearchSummaryPill` | `src/components/cv/` | labelled field with associated error, an optional "(opcional)" suffix and a numeric or text `inputMode`; search summary button (numeric or free-text summary) that reopens the form |
| `PlaceHero`, `CvEmptyState`, `NoticeBanner`, `LoadingState` | `src/components/cv/` | polling-place hero, safe empty/error cards, service notices (`role`, optional icon overriding the tone glyph) and announced loading skeleton |
| `pollingSearchFromUrl`, `pollingMapsUrl`, `pollingVotingDate` | `src/lib/pollingPlace.ts` | validated route defaults, coordinate/address directions and the existing envelope's date, formatted by the election-date helpers below |
| `TSE_ONDE_VOTAR_URL`, `TSE_SITE_URL` | `src/lib/links.ts` | fixed official links (the where-to-vote service, copied once from the service contract; the TSE site for the calendar and the results) |
| `CountdownHero` | `src/components/cv/CountdownHero.tsx` | the Quando hero: `count` (number, round, date and hours, read as one sentence), `today` (green check and the "Ver onde eu voto" CTA), `closed` (the day's voting is over) and `after` (the election is over, with the TSE results link) |
| `RoundTile` | `src/components/cv/RoundTile.tsx` | one round as an `<li>` named with its tag: pill, date, weekday and tag, green when it is the next or current round, "Data a confirmar" without a date |
| `InfoStrip` | `src/components/cv/InfoStrip.tsx` | icon in a white circle, title and subtitle, no link (the voting hours) |
| `CvChip` | `src/components/cv/CvChip.tsx` | a grey non-interactive 36 px `<li>` chip inside a `ul.cv-chips` (the offices) |
| `electionPhase`, `daysUntil`, `roundTags`, `formatRoundDate`, `formatWeekday`, `formatVotingHours`, `formatHour`, `formatShortDate`, `calendarDay` | `src/lib/electionDates.ts` | the phase and the countdown on the Brasília civil day (`Intl.DateTimeFormat` with `timeZone`, never the device zone), the tags per phase and the pt-BR formatting the pages share |
| `officeChips` | `src/labels.ts` | the office chips in the service's order, state and district deputies merged into one |
| `ComboField` | `src/components/cv/ComboField.tsx` | debounced municipality combobox with keyboard selection and loading/empty/error status |
| `PlaceCard` | `src/components/cv/PlaceCard.tsx` | one polling place: section and accessibility chips, Onde voto and Maps links |
| `LoadMore` | `src/components/cv/LoadMore.tsx` | "Mostrando X de Y" with an offset-page button, announcing how many places were added |
| `appendPlacesPage`, `PLACES_PAGE_SIZE` | `src/lib/placePages.ts` | fetches the next 20-place offset page and de-duplicates by zone/number before appending |
| `mapsUrl` | `src/lib/links.ts` | Google Maps search link from a place's coordinates, falling back to its address and municipality |
| `AccordionGroup`, `AccordionItem` | `src/components/cv/Accordion.tsx` | a `<section id>` with a script-focusable H2 and a card of questions; each item is a button in an H3 with `aria-expanded` and `aria-controls` and a region labelled by it; open state is the parent's, so several stay open |
| `ChipNav` | `src/components/cv/ChipNav.tsx` | a `<nav aria-label>` row of `<button>` chips that scroll to same-page anchors (never `<a href="#…">`: the router is hash-based); `activeId` marks one with `aria-current` |
| `TermList` | `src/components/cv/TermList.tsx` | terms and explanations as a `<dl>` of blocks |
| `CopyLinkButton` | `src/components/cv/CopyLinkButton.tsx` | copies the page's origin, path and the given hash; "Link copiado" for 1.8 s with a polite announcement; without a clipboard it `replaceState`s the hash and says so below the button |
| `scrollToId`, `HIGHLIGHT_CLASS` | `src/lib/scroll.ts` | smooth scroll to an element (instant under reduced motion) honouring its `scroll-margin-top`; the optional 2.4 s flash, ended earlier by a pointer or key on the element and kept until then under reduced motion |
| `FAQ`, `FAQ_DRAFT` | `src/content/faq.ts` | the Dúvidas copy (plain text, paragraphs, optional terms and action link) and the draft flag |
| `SiteHeader`, `NavMenu`, `NavLinks`, `SiteFooter`, `SkipLink`, `BrandDots` | `src/components/cv/` | the shell of every screen (Tela 8, below): sticky header, the modal side menu, the five destinations as drawer cards or inline pills, the global footer, the skip link and the three CDE dots |
| `NAV_ITEMS`, `currentNavId`, `routeTitle` | `src/lib/routes.ts` | the menu destinations, the current one per path and the tab title per route |
| `useFocusTrap` | `src/lib/useFocusTrap.ts` | Tab and Shift+Tab kept inside an open dialog |
| `markFloatingBar`, `FLOATING_BAR_CLASS` | `src/lib/floatingBar.ts` | the `html.cv-has-floating-bar` mark a mounted `FloatingBar` leaves for the footer's clearance |
| `REPO_URL` | `src/lib/links.ts` | the public mirror: the footer's "Código aberto" links, the menu item and the wide header icon; null hides them |

The slot colours (and so the tray avatars, and the comparison screen when it reuses them) follow
the order of marking, never the candidacy or the party (ADR 0008); `sq` in the exit URL keeps
that order so the next screen can repeat the colours. The choice screen words every error, empty
and not-found state with the phrases of the spec's section 5.11 and never shows
`not_found.reason`, the service's `guidance` or an HTTP detail; `warnings[]` keep the service
text. Layout: one column under 640 px (the prints), two columns and a 32 px gutter from 640 px,
and from 1024 px a 1120 px content width, the pill and the tabs on one line, the search with the
chip beside it, three columns of cards that keep their own height, the tray 560 px wide and 24 px
from the bottom, and a hover border (fine pointers only) on unmarked cards.

## The shell (Tela 8)

`src/App.tsx` is the frame of every screen (package 8, `casca-spec.md`): `SkipLink`, the
sticky `SiteHeader` (60 px at every width: the three dots, "O meu voto", the "não oficial"
pill, a 44 px menu button below 1024 px and the inline `NavLinks` pills and a repository icon link from 1024 px), the
screen inside `<main id="conteudo" tabIndex={-1}>`, the `SiteFooter` and the `NavMenu`. The
menu is a modal dialog in a portal on `body`: it opens from the right with focus on the current
item (`useFocusTrap` keeps Tab inside). The close button, scrim, Esc, a chosen item or a route
change closes it with the reverse animation (disabled for reduced motion) and returns focus to
the menu button unless the page moved focus. At 1024 px the drawer closes immediately and
focus moves to the current inline link, falling back to `<main>`. Its state never reaches the
URL. `lib/routes.ts` holds
`NAV_ITEMS`, `currentNavId` (`candidato/*` and unknown paths count as Comparar) and
`routeTitle`, which sets `document.title` as "{título} · O meu voto"; a change of path focuses
`<main>` without scrolling and announces the title in a polite live region, unless the screen
moves focus afterwards (Telas 4, 5, 7).
The footer says "Projeto independente e não oficial" once for the whole site, with "Dúvidas",
the licences line, a credit line ("Feito por Felipe Correia · Código aberto no GitHub") and the
signature; "Código aberto", the menu item "Código no GitHub" and the header icon (same label, outside `nav[aria-label=Principal]`) render only with a real
`REPO_URL` (`lib/links.ts`, the public mirror). `FloatingBar` marks
`html.cv-has-floating-bar` while mounted (`lib/floatingBar.ts`), and the footer gets 120 px of
bottom padding plus the bottom safe area, so the end of the page stays above the bar. The skip link handles
its own click because the router is hash-based: `#conteudo` would be read as a route. The
router is unchanged; path routes are issue #99.

## Candidate profile (Tela 3)

`src/pages/Candidate.tsx` owns the sticky back/share bar, details, declared networks, source,
problem states and responsive composition. It imports the prior screens' `CvAvatar`,
`NumberPill` and `IconButton` through the shared pieces. A profile opened from comparison
returns the complete `cmp` as `sq`, preserving `pair` and `tab`; a direct profile returns to
choice in its race. "Comparar com outras" opens choice with `marcar`, keeping either the
comparison's marking order or this single candidacy. Native sharing has a WhatsApp fallback;
both share the exact profile text and the direct URL. State is never persisted in storage.

Below 640 px the hero stacks above the details with a floating action bar; from 640 px the
hero is horizontal in a page up to 720 px. From 1024 px the page is up to 1120 px, with a
360 px vertical hero sticky 84 px below the shell header (24 px under the back bar) with its
action inside, details on the right and no floating bar. Networks preview four links (eight on desktop), then expand; personal fields stay in the
closed-by-default two-column panel. Loading, error and not-found use the exact Tela 3 copy,
with no service guidance or technical codes. Source and warning text are preserved. Assets
remain exclusively in comparison. Reduced motion disables hero and panel animations.

The six `--cv-status-{ok,bad,wait}-{fg,bg}` tokens live only in `cvTokens`. Choice and profile
use them with an icon and the registration term; comparison stays neutral. The extraction of
`FloatingBar` retains all of the choice tray's geometry, shadows and responsive placement.

## Where to vote (Tela 4)

`src/pages/WhereToVote.tsx` owns the five states: form, loading, result, not found and error.
It keeps the existing `GET /polling-place` mapping, using the shared cv tokens and pieces.
Searches replace the hash query, preserve leading zeros, omit `round` for the next round,
and run automatically when a direct link has valid zone and section values. A link from Places
with a zone but no section opens the form with that zone and focuses Section without searching. Invalid numeric
input stays visible with "Use só números."; an invalid or absent UF defaults to SP. The state
selector offers the 27 UFs and ZZ, without the candidate-only BR option. Editing a summary
keeps the URL until the next search and focuses the zone field. Superseded calls cannot
overwrite a later search or reopen a result after editing.

Below 1024 px the submitted form becomes a summary pill; the floating bar provides search
or directions. At 640 px the content is at most 560 px wide and not-found alternatives sit
side by side. From 1024 px a sticky 380 px form stays beside the response in a 1080 px grid,
with its search button inside and directions in the hero, without a floating bar. Empty
detail rows disappear; previous-place notices and warnings retain the service text. The date
card uses the response's election and voting hours without another call and disappears when
the date is absent. Maps uses coordinates or the original full address as fallback.

The default shared component styles remain unchanged. `StatusBadge` accepts an explicit
`tone`, preserving supplied text for these non-candidate badges; its existing candidate
mapping and sentence casing remain the defaults. `LinkCard` adds the accent tone and follows
hash links in the current tab; external links retain the original new-tab behavior.
Loading is announced, completion focuses its heading, keyboard arrows change the round,
and reduced motion removes entry/pulse/sliding while slowing the spinner to 2.4 s. Error
and not-found cards use the approved copy, with no reason, guidance or HTTP detail in the DOM.
No storage, extra tokens, shell changes or Pages deployment.

## Places by city (Tela 5)

`src/pages/Places.tsx` uses the existing `/municipalities` and `/polling-places` calls. A
municipality must be picked from the debounced suggestion list. The URL records the UF, TSE
municipality code and optional filters; a direct link searches automatically. After a search,
the phone view shows a summary pill, while desktop keeps a sticky form beside the results.
Cards expose zone links to Onde voto and Google Maps links from `lib/links.ts`. Geolocation is
requested only on choosing the nearby tab, used for that search and its pages, and never
written to the URL or browser storage. Errors and not-found states use page copy without
service reason, guidance or HTTP detail. The page footer shows only the source and its stale
badge; the independent-project disclaimer lives in the shell footer.

The client requests the next page with `limit=20&offset=<loaded>` and appends new places.
Backend support for `offset` is live; it was verified in production on 2026-09-28.

## Election dates (Tela 6)

`src/pages/When.tsx` owns the four states (loading, ok, no data, error) and the composition;
`WhenScreen` renders a given envelope and instant, which is how the tests cover every phase
without a network. One `GET /election` on open; "Tentar de novo" repeats it through the loading
state. The field mapping is the service's: rounds (number and date), voting hours, offices, notes
and the calendar source. Everything the hero says comes from `src/lib/electionDates.ts`, which
compares civil days in `America/Sao_Paulo` only: before the first round the hero counts the days
(never below 1, recounted on `visibilitychange`, never on a timer); on a round day it is the
voting day until the service's closing time, then "A votação de hoje terminou"; between the
rounds it counts to the second one under the "Só onde houver 2º turno" notice; after the last
dated round it is over, with the TSE results link; without the first round's date there is no
hero. A round without a date reads "Data a confirmar" and is ignored by the phase; without
voting hours the strip and the hero's "· horário" disappear; empty offices, notes or source hide
their block; the second round's long service note never shows (the tile tag replaces it).

`data: null` or `not_found` is the no-data state ("O calendário não carregou", retry, and the
"Enquanto isso" links to the TSE calendar and Onde voto); network or 5xx errors use the common
copy. `warnings[]` keep the service text. No `reason`, `guidance` or technical code reaches the
DOM: an unknown office code is spelled out, never printed as is. The Onde voto "Quando votar" card
formats its date and hours with the same helpers, with unchanged text.

Layout: one column under 640 px, 560 px centred from 640 px, and from 1024 px two 520 px columns
in a 1080 px grid (hero, notice, warnings, rounds and hours on the left; offices and "Antes de
sair de casa" on the right; head and footer full width); the no-data state stays one column. The
countdown number pops in and the hero enters like Tela 4's result; reduced motion turns both off.
Contrast of the spec's pairs (navy on the yellow tint 12.2:1, `--cv-ink-2` on `--cv-surface-2`
7.4:1, white on `--cv-green-strong` 5.8:1) is above 4.5:1.

## FAQ (Tela 7)

`src/pages/Faq.tsx` renders `src/content/faq.ts`: four theme groups (`tema-comparacao`,
`tema-bens`, `tema-privacidade`, `tema-votar`) holding the eleven stable item ids other screens
link to (`destino`, `porque`, `campos`, `evolucao`, `patrimonio`, `fonte`, `cpf`, `candidatos`,
`oficial`, `zona`, `mudou`). No API call. The copy is plain text (no HTML or markdown), still a
draft: the "Texto em rascunho" notice shows while `FAQ_DRAFT` is true.

`#/duvidas?abrir=<id>` opens that item and, two frames after mount (after the router's scroll to
the top), scrolls to it below the sticky top plus 12 px (`scroll-margin-top` on the item, from
`--cv-topnav`), flashes it yellow for 2.4 s and puts focus on its button; when the page ends
first the item stays whole in the viewport, as in the prototype. Opening or closing items never
changes the URL. An unknown id is ignored. The theme chips are buttons that scroll to the group
and focus its H2. Each open answer ends with an action link where the copy has one ("Ver locais
da cidade" to `#/locais`, "Consultar onde voto" to `#/onde-voto`) and "Copiar link", which copies
`origin + pathname + #/duvidas?abrir=<id>`. The page has no footer of its own: the
independent-project disclaimer lives in the shell footer.

Layout: one column under 640 px with the chip row bleeding to the edges; 640 px centred from
640 px; from 1024 px a `240px minmax(0, 720px)` grid with a 48 px gap, the chips stacked in a
sticky left column that marks the group under the reading line (the sticky top plus 12 px),
through an IntersectionObserver with that line as its top margin. Two rules keep the mark where
the person looks on a page too short to scroll every group up to the line: the last group takes
it once it is whole in the viewport or the page is scrolled to its end, and a group chosen by a
chip (or holding the `?abrir=` item) keeps it, ahead of that rule, until it scrolls out of the
viewport, or out of full view once it was whole in it. Reduced motion turns off the chevron
rotation, the answer entry and the smooth scroll, and makes the flash a fixed `--cv-slot-3-tint`
background until the person touches the item. Contrast of the spec's pairs is above 4.5:1
(`--cv-ink-2` on the yellow tint 6.95:1, on `--cv-surface-2` 7.38:1, the notice icon on the tint
7.11:1).

## Astryx 0.6.3 notes (pinned exactly; beta)

- `Theme` and `defineTheme` come from `@astryxdesign/core/theme`; overriding `--color-accent`
  does not re-point `--color-on-accent` (set explicitly).
- The theme is injected at runtime (Astryx warns about it in dev). For production, build it once
  with `npx astryx theme build src/themes/cde.ts -o <file>` and import the CSS (follow-up).
- Content components emit hashed StyleX classes only; page CSS that must reach inside one
  (`src/styles.css`) targets a wrapper the page owns.
- The Selector's trigger container does carry a stable class (`.astryx-selector`, with
  `.astryx-icon` on its chevron and `.astryx-field` around it), and Astryx CSS sits in
  `@layer astryx-base`/`astryx-theme`, so unlayered page CSS restyles it without `!important`:
  the state pill of the choice mode is the Selector itself (`renderValue` draws the pill's
  content, `aria-label` reaches the trigger button), not a rewrite of the bottom sheet.
- `TabList`/`Tab`: `label` is a string and doubles as the accessible name; three tabs with icons
  need the phone's shorter labels to fit 390 px.
- pt-BR component strings: `InternationalizationProvider` with `locales/pt-BR.json` (about
  210 KB minified of message formatting in the bundle).
- lucide-react no longer ships brand glyphs; the social icons are inline SVGs
  (`src/components/brandIcons.tsx`).
- The Astryx CLI's generated `AGENTS.md` is not kept: its rules (no `div`, no hex or px) do not
  match how this page is built; this README is the guide.

## Follow-ups after landing

1. Ship one pre-built theme.
2. The asset evolution row, once the service serves it.
3. Self-host Inter (`public/fonts/`) instead of Google Fonts.
4. Candidate photos once the R2 mirror exists (`photo_url`).
5. Occupation casing at index build (`_CASED_COLUMNS`). Comparison rows already name each cell
   and announce pair changes through a polite live region.
6. Bundle: 802 KB minified / 235 KB gzip of JS today (react-dom, Astryx i18n and theme engine
   are the bulk); lazy chunks for the places-by-city and election-dates routes and the
   pre-built theme bring it down.
7. Add UF and vote-destination explanation to the profile response so the page no longer
   needs to recover the electoral unit from its official URL or mirror the service copy.
