# 0007. Product recorte: finish the MVP before round 1, candidate comparator as the first new scope

Status: accepted, 2026-09-24; amended by ADR 0008 (2026-09-25) on the launch order: the
comparator leads the public launch of 2026-09-30, where-to-vote is secondary.

## Context

The captain paused the visual-page work to ask what the TSE does not already organize well
for a voter. Research against the TSE's own channels (Onde Votar, e-Título, DivulgaCandContas,
Open Data, Electoral Statistics) confirmed that the TSE and e-Título already own individual
voter-registration services (polling place by CPF/title, route handoff, certificates,
justification, and even a lookup on behalf of someone else on election day) and that the
TSE's own candidate comparison, on DivulgaCandContas, is **financial only**: "Comparativo entre
Candidatos - Possibilita realizar comparativo entre candidatos sobre o total de recursos
arrecadados e gastos de campanha." This project should not compete with those individual
services or ask for CPF or registration data (ADR 0004); it can add value by comparing public,
already-ingested registration facts side by side, over the page and over MCP.

This settles the "Escopo extra além das 4 perguntas do MVP" pendency that `wiki/index.md` and
the 2026-09-21 entry of `wiki/log.md` listed as open with the captain: whether to go beyond the
four MVP questions of `docs/domain-model.md` section 1 (where do I vote, which places are near
me, who is running, when is the election) before deploy.

## Decision

The captain answered on the research board, verbatim: "Recorte Onde Voto - 1 recorte: Terminar
e publicar o MVP; o comparador é o primeiro caso novo | 2 conteúdo: Só campos já no índice | 3
ordem: Publicar o MVP antes do 1º turno (#20, #22); comparador mirando o 2º turno | 4 público:
Eleitor do 2º turno na página, mesma tool no MCP."

In English: finish and publish the MVP before round 1 on 2026-10-04 — issues #20 (Cloud Run
deploy) and #22 (Cloudflare edge and domain) are the critical path and stay the captain's. The
**candidate comparator** is the first new scope beyond the four MVP questions. Its v1 content
is restricted to fields already in the index (`docs/domain-model.md` 3.5): ballot name,
number, party, federation or coalition with composition, adjudication status, `on_ballot`,
occupation, photo, social links, running mates, the DivulgaCandContas link, and `source`. It
never includes gender, race/colour, marital status or education — those exist only in the
individual candidate profile under ADR 0004's guardrail ("nunca em `list_candidates` nem em
agregados"), and a side-by-side comparator is a list-shaped answer, so including them would
need a new ADR; v1 leaves them out and reopens nothing. Declared assets, government proposals
and campaign finance are public but not yet ingested, and finance would duplicate the TSE's own
comparison; they are out of v1. The comparator targets round-2 voters (round 2 is 2026-10-25,
where it happens), exposed both on the voter page and as the same MCP tool used by other
clients.

Visual design is a separate, later decision and is not part of this recorte: the captain did
not adopt any of the three visual directions explored on the design board on 2026-09-24
("não gostei da UI vou re-desenhar com o claude design coletando diretamente o system design
de um bench que gostei"); he will redesign the page himself from a reference design system he
picks. The MVP publishes with the current UI in `web/`.

## Consequences

- The four MVP questions stay exactly as scoped in `docs/domain-model.md` section 1; the
  comparator is additive, not a redefinition of the MVP.
- The comparator needs its own spec before implementation: one core query plus one MCP tool and
  REST route, comparing two or more candidacies that share the same `(uf, office, round)`. No
  ranking, no vote recommendation, no ingestion changes for v1.
- Deploy (#20) and the Cloudflare edge and domain (#22) are unblocked to proceed as the
  critical path to a public MVP by round 1; the comparator's realistic target is round 2
  (2026-10-25), after the MVP is live.
- `docs/domain-model.md` section 1 and `docs/codebase-design.md` gain the comparator's contract
  once its spec lands; this ADR records the decision, not the design.
