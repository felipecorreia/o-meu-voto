# 0014. Bound photo mirroring independently of index publication

Status: accepted, 2026-09-30. Amends ADR 0005 and ADR 0013 for production refreshes.

## Context

The first content-addressed load of 20,984 TSE photos did not finish inside the refresh
job's 60-minute limit. Runs 36713057795 and 36742218406 reached the mirror and were
cancelled about 56 minutes later, before `publish`. Their logs include no per-object progress,
so they do not establish an upload rate or the R2 object count. The mirror lists R2 first and
skips keys whose ETag matches the current TSE bytes, so a rerun rechecks all source photos but
does not upload verified keys again.

## Decision

- A manually dispatched `photo-full-load.yml` has a six-hour job budget, fetches all 28 ZIPs,
  verifies the currently published index against its manifest, and mirrors into R2 without
  publishing an index. It reports upload progress every 500 objects and writes a checksum-
  verified R2 completion marker only after the mirror and index photo chain both pass. It
  refuses a second completed load. Scheduled refreshes skip mirroring until that marker is
  present, so a long initial load cannot race with incremental writes. The next normal refresh
  adds verified photo URLs to the published index.
- A normal refresh gives mirroring 15 minutes. Photo fetch, carry-forward and mirror errors do
  not prevent `publish`; after publication they fail the job so an integrity alarm stays
  visible. A missing full-load marker skips the photo stages; a failed marker query also fails
  the job after publication. The full photo load has independent workflow concurrency, so it
  cannot queue index publication behind its long run.
- Before mirroring, the refresh carries a prior `photo_url` only when its previous index pair
  is hash-verified, its URL and digest pass the photo-chain check, the current TSE JPEG has
  the same SHA-256, and the R2 ETag matches that JPEG's MD5. A partial upload never gains a URL
  from this fallback. Carry-forward and mirroring edit separate copies of the validated pair;
  publication selects a copy only after its photo stage succeeds. The final index passes the
  photo-chain check before publication.
- Production mirroring retains old content-addressed objects. Deleting them before an index
  publish could break the live index when the mirror or publication fails. A future cleanup
  must first prove no published or rollback version still refers to an object.

## Consequences

Photo failures can leave the current index with fewer URLs when there is no verified previous
photo for a candidacy, while election data still advances. The bucket may retain superseded
objects. The first load's actual throughput is measurable from its progress logs; 15 minutes
is a containment budget for later incremental runs, not an estimate inferred from the two
cancelled full runs.
