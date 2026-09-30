# 0013. Content-addressed photo objects and a recorded digest

Status: accepted, 2026-09-29. Amends ADR 0005 (photos in R2) and the mirror_photos stage of
`docs/codebase-design.md`, section 5.

Production refresh sequencing and old-object deletion were amended by [ADR 0014](0014-photo-refresh-independent-of-index-publication.md) and [ADR 0015](0015-publication-aware-photo-cleanup.md).

## Context

The candidate photos are mirrored from the TSE ZIPs to a public R2 bucket, and the index carries
each candidacy's `photo_url`. A candidate's photo is the most recognisable thing on the page,
and it is served from a bucket the index does not control: whoever can write to the bucket (a
leaked R2 token, a compromised workflow) can replace a JPEG and every voter sees the new face
under the candidate's name. Until this change the object key was the TSE's own file name,
`F<UF><SQ>_div.jpg`, the sync overwrote whatever differed, and nothing in the index tied a URL
to the bytes the TSE published, so a swap looked exactly like a legitimate update.

## Decision

- **Content-addressed keys.** An object is named `F<UF><SQ>_div-<sha256>.jpg`, the SHA-256 of
  the JPEG bytes in the TSE ZIP. A key therefore has exactly one legitimate content. When the
  TSE publishes another photo for a candidacy, the URL changes; the old object is removed.
- **The digest is in the index.** `candidates.photo_sha256` (schema version 6) holds the same
  digest next to `photo_url`. It is not part of any answer; it exists so the chain can be
  checked.
- **The mirror never overwrites.** `mirror_photos` compares, for every key it expects, the
  bucket's checksum (R2's ETag, the MD5 of the bytes) with the MD5 of the ZIP's photo. A key
  that exists with other bytes, or with a checksum that cannot vouch for them (a multipart
  ETag), fails the run with `PhotoIntegrityError` before anything is uploaded or deleted. After
  uploading it lists the bucket again and requires every key of the run to be there with the
  expected checksum, and only then deletes the keys no ZIP explains.
- **The chain is checked at validation and mirroring.** `photo_url` must carry the recorded
  digest and candidacy's `sq_candidato` (`pipeline/photo_integrity.py`). The `photo_chain`
  gate rejects malformed URLs and mixed schemes or hosts even without a configured domain.
  With `--photo-public-domain`, it requires the exact configured base URL and key.
  `mirror-photos` applies that strict check before touching R2 and after writing the index.
  The key's UF must match `candidates.uf`; the mirror checks the ZIP UF against the index
  before uploading or deleting objects, then the chain rechecks the resulting key.
  The refresh workflow passes an empty strict base to `validate` while the new index still
  has null photo URLs; the mirror then checks against its configured public domain.
- A photo integrity failure stops before `publish` (ADR 0004). The deletion window for old
  photo objects is described below.

## What this does and does not cover

Covered: an overwrite or replacement of an object still expected from the current TSE ZIPs
is detected on the next refresh run, which then refuses to publish, and the mirror never
overwrites it; a `photo_url` that is edited, mismatched or half-written in the index is
rejected when checked against the configured public domain; the photo the index promises is,
byte for byte, the photo in the TSE ZIP at mirror time.

Not covered, and accepted for now (follow-ups in the PR that introduced this ADR):

- **Detection is not prevention.** Between a swap and the next refresh run (hours) voters get
  the swapped photo: a plain `<img>` cannot check a digest. Closing that window needs an
  audit of the public URLs against the index, and least-privilege R2 credentials.
- **Superseded or removed photos are not checked.** If an object is tampered with and the TSE
  changes or drops that photo before the next refresh, the old key is deleted without an alert:
  the new index no longer references it. The live index still points to that key until
  `publish`; if publishing fails, that reference remains until a later successful run.
- **An attacker who controls both the bucket and the index** (R2 token plus the GCS publisher)
  can rewrite both consistently. The two credentials live in different clouds; keep them so.
- **The TSE source.** A wrong photo published by the TSE, or served to us by a man in the
  middle of the CDN download, is mirrored faithfully. The digest proves what we took, not that
  the TSE meant it; the TSE signs nothing.
- **MD5 as the bucket-side check.** It is only compared against the MD5 of the file we hold;
  an attacker would need a second preimage of a specific JPEG, not a collision pair.
- **A window after a photo changes.** The old object is deleted before the new index is
  published, so a failed publish leaves the live index pointing at a deleted key until the
  next successful run (follow-up: prune after publish).

## Consequences

- Existing R2 objects under the old key format are not referenced any more and are removed by
  the first run of this version; there is no R2 bucket in production yet.
- A photo URL is immutable, so it can be cached forever.
- A tampered object still expected from the current TSE ZIPs stops refresh until someone
  deletes it and rotates the credential: the pipeline reports which key, and the fix is human.
