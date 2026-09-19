# Issue tracker: GitHub

Issues, specs and tickets for this repo live as GitHub Issues in
`felipecorreia/br-elections-mcp` (remote `origin`). Use the `gh` CLI for all operations; it
infers the repo from the clone.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body-file <path>` (heredoc or file for
  multi-line bodies).
- **Read an issue**: `gh issue view <number> --comments`, fetching labels as well.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`
  with `--label` and `--state` filters as needed.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`. A PR that implements a ticket closes it
  with `Closes #<number>` in the PR body.

## Specs and tickets

- A **spec** (from `/to-spec`) is one issue labelled `spec` and `ready-for-agent`.
- A **ticket** (from `/to-tickets`) is one issue per tracer-bullet slice, labelled
  `ready-for-agent`, citing its spec (`Parent: #<spec>`) and linked to it as a GitHub sub-issue.
- **Blocking** uses GitHub's **native issue dependencies**, the UI-visible representation.
  Add an edge with
  `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`,
  where `<blocker-db-id>` is the blocker's numeric **database id**
  (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, not the `#number` or `node_id`).
  The ticket body also carries a `## Blocked by` list for readers without the UI.
  A ticket is unblocked when every blocker is closed.
- **Frontier query**: open tickets with no open blocker
  (`issue_dependencies_summary.blocked_by == 0`) and no assignee, in dependency order.
- **Claim**: `gh issue edit <n> --add-assignee @me` is the session's first write.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature
requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr`
equivalents (`gh pr view --comments`, `gh pr diff`, `gh pr list --json ...authorAssociation`
keeping only `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR` or `NONE`, `gh pr comment`,
`gh pr edit --add-label`, `gh pr close`). GitHub shares one number space across issues and
PRs: resolve a bare `#42` with `gh pr view 42`, falling back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog
  body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue. Labels:
  `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is
  assigned to the driving dev.
- **Blocking**, **frontier query** and **claim**: as in "Specs and tickets" above.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append
  a context pointer (gist + link) to the map's Decisions-so-far.
