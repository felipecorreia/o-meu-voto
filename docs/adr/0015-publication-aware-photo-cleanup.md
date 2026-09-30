# 0015. Remove unreferenced photos after publication, with a 48-hour grace

Status: accepted, 2026-09-30. Amends ADR 0004 (when photos leave R2) and ADR 0014 (old
objects retained).

## Context

ADR 0004 treats candidate photos as public personal data in the project's custody: the
pipeline removes from R2 the photos the TSE stops publishing. ADR 0014 made production
mirroring pass `--retain-old-photos`, because the mirror deleted before `publish`, and a failed
mirror or publish could leave the live index pointing at a deleted key. Since then nothing is
removed, and ADR 0014 asked that a future cleanup first prove no served index still refers to
an object.

"Served" is wider than "the pair published before this one". The service loads the index as
`core/index.py` describes: it has no timer; a finished query signals a check task that asks the
index bucket at most once every 60 seconds and swaps in the background, so the query that
triggers the check, and every query while the new index downloads, is answered from the old
version. A warm instance with no traffic (`--min-instances=1` is the plan for election week,
runbook step C4) keeps its version until the first query after it wakes, however many refreshes
published in between. A failed check keeps the open version for as long as the bucket stays
unreachable. Refreshes run up to five times a day, so an instance idle overnight can be more
than one publication behind.

## Decision

- A new stage, `clean-photos`, runs in `refresh.yml` right after `publish`, and only when the
  photo-load status query, photo fetch, previous-index download, carry-forward and mirror all
  succeeded. It never runs in `photo-full-load.yml`, which keeps `--retain-old-photos`, and
  the mirror itself keeps retaining in production.
- It verifies both pairs before reading them: the pair just published against its manifest
  and against the live manifest in the index bucket (so nothing was published over it), and
  the pair it superseded against its manifest. Both must pass the photo-chain check for the
  configured public domain.
- **Grace rule.** An object is deleted only after it went unreferenced by every index that was
  current in the last 48 hours. A ledger in the index bucket
  (`photo-cleanup/unreferenced.json`, under the publish prefix) records, for each photo object
  that neither the published nor the previous pair references, when a run first saw it so.
  The ledger names the pair its run published. When the next run's previous pair is another
  one (a refresh that published without cleaning up, a cleanup refused before it wrote the
  ledger, a manual publish or a rollback), a pair was current without being evaluated, so
  every clock restarts. An object past the grace was therefore absent from every pair
  current at any moment of the last 48 hours.
- 48 hours equals `STALE_AFTER_HOURS`, the service's staleness threshold. An instance still
  serving a pair superseded more than 48 hours ago has not completed an index check for that
  long, and its answers already warn that the data is stale. A test keeps the two equal.
- **Refusals**, all before any deletion, and they fail the job: a pair that does not verify, a
  live manifest that is not the pair just published, an R2 listing that lacks an object the
  published index references (wrong bucket or partial listing), and more due deletions than
  10% of the photo objects in the bucket (`--max-delete-fraction`). The first three write no
  ledger, so the clocks restart on the next run. A run refused by the bound writes the
  ledger first, with the clocks carried, and deletes nothing: the chain stays intact and the
  objects stay due, so the job keeps failing on every refresh until the cause is understood
  (a legitimate mass removal is cleared by running the stage once by hand with a higher
  `--max-delete-fraction`). The refresh run summary shows the stage's output, refusal
  included. Only content-addressed photo keys are candidates; the full-load marker and any
  other key are never deleted.
- **Rollout.** The repository variable `PHOTO_CLEANUP_MODE` selects `delete`; unset or any
  other value is a dry run that lists R2, writes the ledger so the grace clock runs, prints
  the counts and a sample of what it would delete, and deletes nothing. Merging therefore
  deletes no object: after at least 48 hours of dry runs, review the counts in the run
  summary and enable deletion with `gh variable set PHOTO_CLEANUP_MODE --body delete`. To go
  back to dry runs, `gh variable delete PHOTO_CLEANUP_MODE` (or set it to anything but
  `delete`); the ledger keeps running either way.
- No credential changes. The ledger uses the publisher's existing `roles/storage.objectUser`
  on the index bucket; deletion uses the existing R2 token, which must allow `DeleteObject`.

## Consequences

- A photo the TSE stops publishing leaves R2 48 hours after the first refresh that publishes an
  index without it, plus up to one refresh interval, instead of immediately (ADR 0004 before
  ADR 0014) or never (ADR 0014).
- Rolling back to a version superseded more than 48 hours ago can point to deleted photos
  until the next refresh: carry-forward drops a URL whose object R2 no longer holds and the
  mirror uploads every photo the TSE still publishes. `versions/` is not treated as a set of
  rollback targets to protect, since that would keep every photo forever.
- The index bucket holds one more object, never read by the service.
- A concurrent manual publish between the run's `current-index` download and its `publish`
  would put a pair on air that no evaluation saw. Refreshes are serialized and the full load
  never publishes, so only a hand publish at that moment could cause it; the live-manifest
  check catches a publish that lands after the run's own.
