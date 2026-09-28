"""``extract``: the one CSV ``build`` reads, taken out of a TSE ZIP.

Not a stage of its own but the glue between ``fetch`` and ``build`` in the
refresh workflow. A TSE ZIP carries one CSV per UF plus a ``_BRASIL`` file,
or a single CSV (the municipality crosswalk), plus ``leiame.pdf``; ``build``
ingests the national file, so this picks the ``_BRASIL`` member when there is
one, the only CSV otherwise, and refuses to guess between several per-UF files.
The member is written under its base name only, inside ``output_dir``, which
in the workflow is the runner's temporary directory (ADR 0004).
"""

from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath

BRASIL_SUFFIX = "_BRASIL.csv"


class ExtractError(RuntimeError):
    """The ZIP does not yield exactly one CSV for ``build``; nothing was written."""


def extract_csv(zip_path: Path, output_dir: Path) -> Path:
    """Extract the ``_BRASIL`` CSV (or the only CSV) of ``zip_path`` into ``output_dir``."""
    if not zip_path.is_file():
        raise ExtractError(f"ZIP not found: {zip_path}")
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise ExtractError(f"{zip_path} is not a ZIP file: {exc}") from exc
    with archive:
        members = [
            name
            for name in archive.namelist()
            if not name.endswith("/") and name.lower().endswith(".csv")
        ]
        member = _choose(zip_path, members)
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / PurePosixPath(member).name
        tmp = target.with_name(f".{target.name}.tmp")
        with archive.open(member) as source, tmp.open("wb") as sink:
            while chunk := source.read(1 << 20):
                sink.write(chunk)
        tmp.replace(target)
    return target


def _choose(zip_path: Path, members: list[str]) -> str:
    if not members:
        raise ExtractError(f"{zip_path.name} carries no CSV")
    national = [name for name in members if name.upper().endswith(BRASIL_SUFFIX.upper())]
    if len(national) == 1:
        return national[0]
    if len(members) == 1:
        return members[0]
    raise ExtractError(
        f"{zip_path.name} carries several CSVs and no single {BRASIL_SUFFIX} file: "
        f"{sorted(PurePosixPath(name).name for name in members)}"
    )
