# How it was built

O meu voto was built by AI coding agents working for one human owner. The owner decided what
the product is and made the calls that carry cost or risk; agents wrote the design documents,
the code, the tests and the reviews. This page names the tools, shows the chain from
a glossary to a merged pull request, walks through one real decision end to end, and lists
three things that went wrong in production and how each was fixed.

Issue and pull request numbers below refer to the private source repository, which keeps the
issue tracker; this public repository is a filtered mirror of its `main` branch.

**Glossary.** The *captain* is the human owner who makes the product calls; agents implement.
The word comes from Firstmate and appears throughout the design documents.

## The tools

- [Claude Code](https://code.claude.com/docs/en/overview), Anthropic's coding agent, and
  [Codex](https://github.com/openai/codex), OpenAI's. Both read the same agent instructions:
  [`AGENTS.md`](../AGENTS.md), which `CLAUDE.md` imports, and the skill configuration in
  [`docs/agents/`](agents/).
- [Firstmate](https://github.com/kunchenguid/firstmate), which turns one agent session into a
  crew: the captain talks to a single "first mate" agent, which writes a brief for each task,
  launches a worker agent ("crewmate") in its own git worktree, supervises it and brings back a
  pull request or a report. Product decisions a worker hits are escalated to the captain, never
  taken by the worker.
- [no-mistakes](https://github.com/kunchenguid/no-mistakes), a gate in front of `git push`.
  Every change goes through its pipeline: intent check, rebase, an automated code review that
  fixes what it finds, tests, documentation, lint, push, pull request, and CI monitoring. Each
  pull request body carries the pipeline's record of those steps. In the current
  configuration its agent steps run on Codex, with Claude as the fallback.
- Matt Pocock's [skills](https://github.com/mattpocock/skills) for the design work, above all
  [grilling](https://github.com/mattpocock/skills/tree/main/skills/productivity/grilling)
  (the agent interviews the captain in rounds of numbered questions, each with its recommended
  answer, until no decision is left assumed) and
  [domain-modeling](https://github.com/mattpocock/skills/tree/main/skills/engineering/domain-modeling)
  (challenge the terms and write the glossary and the decisions down as they settle), plus
  `to-spec` and `to-tickets` for turning the design into a spec and slices.

## The chain

Each link below is a file or a GitHub object that the next one cites, so any line of code can be
traced back to the decision that asked for it.

1. **Glossary.** [`CONTEXT.md`](../CONTEXT.md) fixes the ubiquitous language: the English
   identifier used in code, the Portuguese term the voter and the TSE use, and the synonyms to
   avoid.
2. **Domain model.** [`domain-model.md`](domain-model.md) holds the entities, the invariants,
   the mapping of every TSE CSV column used, and the columns discarded for privacy.
3. **ADRs.** [`adr/`](adr/) records each decision that is hard to reverse, would surprise a
   reader and came from a real trade-off. The first six are dated 2026-09-17, the day of a
   grilling with the captain; ADR 0004 says the list of discarded personal fields was decided
   in that grilling. [`codebase-design.md`](codebase-design.md) turns them into module
   boundaries and tool contracts. The glossary, the domain model, the codebase
   design and ADRs 0001 to 0006 landed together in PR #1 on 2026-09-18.
4. **Spec.** Issue #3, "Spec: MVP do br-elections-mcp", synthesized on 2026-09-18 from those
   documents, which it names as its source: where they disagree, the design document wins and
   the spec is corrected.
5. **Sliced issues.** The spec was cut into tracer-bullet tickets, each a GitHub sub-issue of
   the spec, labelled `ready-for-agent`, with native "blocked by" dependencies
   ([`agents/issue-tracker.md`](agents/issue-tracker.md)). The first, #4 "Where do I vote, end
   to end with Acre (tracer bullet)", crossed every layer for one question and one state.
6. **Pull requests through automated review.** Each ticket became a pull request opened by
   the no-mistakes pipeline and merged by the owner. The pipeline's review does catch real defects:
   on PR #116 it found that a timeout during the photo step could leave the index file changed
   under a manifest that still carried the old hash, which would have blocked publication again,
   and fixed it before the pull request opened.

## One decision end to end: the candidate comparator (ADR 0008)

**Grilling.** ADR 0007 had already recorded that the TSE's own candidate comparison is financial
only. A research round on 2026-09-25 then found that the existing public comparators rank or
flag candidates, or summarize plans with AI, and that none shows side by side whether a vote for
each candidate will count. The agent turned the open questions into a grilling list with a
recommendation for each: show whether a vote for the candidate will count, compare 2 to 4
candidacies, cover all six ballot offices, order columns by ballot number, show declared assets
as declared, no percentages, no "atypical value" flag. The captain answered in one line:
"grilling do comparador: ok, para tudo com suas sugestões, porém apenas um ajuste queria as
fotos dos candidatos isso será possível?" ("ok to everything as you suggest, with one
adjustment: I wanted the candidates' photos, will that be possible?"), then "avance" ("go
ahead").

**Decision.** [ADR 0008](adr/0008-candidate-comparator-v1-scope.md) records the answer: the
scope (2 to 4 on-ballot candidacies of one state, office and round), the content (with the
official photo as the captain's adjustment) and the neutrality rules:

> Entries always come in ballot-number order, never by any value. No percentages, no scores, no
> colour for up or down, no "atypical value" flag

A second decision, ADR 0009, settled the privacy question the research raised: the free text of
declared assets carries addresses and plates, so it is dropped at the first read.

**Contract.** [`codebase-design.md`](codebase-design.md), section 8.7, turns the rules into
the `compare_candidates` tool: its description tells the assistant the comparison "não ordena
por valor, não pontua e não recomenda voto" (does not sort by value, score or recommend a
vote), the entries always come in ballot-number order, and the text content says it is neither a
ranking nor a vote recommendation. Tests pin each of those (`tests/test_core_compare.py`,
`tests/test_mcp_server.py`), and `AGENTS.md` repeats the rule as a guardrail for every future
agent session. The decision, the contract and the implementation shipped together in PR #59,
merged on 2026-09-25, five days before the public launch.

## What went wrong, and the fix

### A frozen index after a refresh (PR #118)

**What happened.** Production kept answering from the index loaded when the instance started,
on 2026-09-29, while reporting the metadata of every newer manifest. Photos and every candidacy
and polling-place update published after that never reached users, and the answers still said
the data was fresh.

**Cause.** The production index source stored each new version at the same local path and
swapped it in by rename. DuckDB keeps one database instance per path, so reopening that path
while the previous connection was still open handed back the old instance, still reading the
old, unlinked file.

**Fix.** A restart cleared it at once, but only until the next refresh. The fix caches every
version at its own path, writes the cached manifest only after the index is in place, and makes
opening an index compare each table's row count with the manifest, refusing a mismatch and
keeping the open version serving. The new tests change data between versions and assert a
queried value; run against the code before the fix, five of them failed.

### Photo mirroring blocked the index refresh (PR #116)

**What happened.** After content-addressed photo mirroring was merged, every scheduled refresh
died in the photo step, which ran before publication. The first full load of the candidate
photos could not finish inside the job's 60-minute limit, so runs were cancelled before
`publish`, and no new index was published from the evening of 2026-09-29.

**Fix.** Photo mirroring can no longer block the index
([ADR 0014](adr/0014-photo-refresh-independent-of-index-publication.md)): the photo stages are
time-bounded and allowed to fail, the validated index is published either way, and a photo
failure then fails the run after publication, so it stays visible. The first full load moved to
a separate, manually started workflow with a six-hour budget that writes a verified completion
marker; later refreshes mirror incrementally. The integrity rules of
[ADR 0013](adr/0013-content-addressed-photo-mirror.md) still hold: a previous photo URL is
carried into a new index only when it is verified against both the TSE file and the stored
object.

### ChatGPT could not use the site (issue #115)

**What happened.** On 2026-09-30 the captain reported that ChatGPT could not read the setup
instructions and that Claude, asked about São Paulo's Senate candidates, fetched the Acre
example from the instructions instead. Reproducing it took several tries. The agent's own
automated browser was first stopped by a Cloudflare human-verification challenge on the chat
sites themselves, so the checks had to run in the captain's signed-in sessions; and a Cloudflare
quick tunnel tried for testing answered the ChatGPT and Claude page readers with 403.

**Cause.** Once reproduced, the causes were in the assistants' fetch tools, not in the service:
ChatGPT refused the `text/markdown` content type, and it only opens URLs that appear as links on
a page it read or that the user sent. Claude's page reader answered a new URL with an
already-seen URL of the same path. A reported 422 could only be reproduced with a literal
`&amp;` as the query separator.

**Fix.** PR #119 serves the setup text as `text/plain` and as an HTML page where every URL is a
link (`/prompt-llm`, now the link voters paste), replaces full example URLs with a route table,
reads a literal `&amp;` as `&`, and adds an allow-all `robots.txt`. Gemini still cannot fetch
the site: its fetcher reports a Google-side opt-out even for hosts it can reach, which the
captain accepted as a known limitation.
