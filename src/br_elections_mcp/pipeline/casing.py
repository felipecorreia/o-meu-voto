"""Title case for names, addresses and civil names, which the TSE mostly publishes in upper
case (real crosswalk file mixes both, issue #48). Applied once, when the pipeline builds the
index: the display value the index stores is already the one the service answers with, so a
warning that quotes a name (``core``) gets the same casing for free, with no rule duplicated
there (docs/codebase-design.md, section 7, the captain's Q2 casing decision).

Ballot names (``NM_URNA_CANDIDATO``) are never passed through this: the same decision keeps
them exactly as the TSE publishes them.
"""

from __future__ import annotations

import re

from br_elections_mcp.domain import UF

# Portuguese prepositions, articles and conjunctions that stay lower case except as the
# first word of a name (captain's Q2 review, docs/codebase-design.md section 7).
CONNECTIVES: frozenset[str] = frozenset(
    [
        "a",
        "o",
        "as",
        "os",
        "um",
        "uma",
        "uns",
        "umas",
        "de",
        "da",
        "do",
        "das",
        "dos",
        "e",
        "em",
        "na",
        "no",
        "nas",
        "nos",
        "para",
        "por",
        "com",
        "sem",
        "sob",
        "sobre",
    ]
)

# Acronyms mined from the real TSE index built on 2026-09-24 (all UFs plus ZZ: 95,601
# places, 5,757 municipalities, 20,986 candidacies). Candidates were distinct upper-case
# tokens from polling_places.name/address/neighborhood, municipalities.name and
# candidates.name, surfaced by three signals: a token with no vowel at all, a token
# immediately before or after " - ", and known Brazilian public-institution abbreviations
# (the EMEF/EE family, CRAS/CREAS/APAE/UBS, the Instituto Federal acronyms). Each surfaced
# token was checked against real example rows by hand; look-alikes that were actually a
# name (two hits of "IFANGER" and "IFIGENIA/IFIGÊNIA" matching the ``IF``-prefix pattern)
# were dropped, and single-word abbreviations that Portuguese also writes capitalized-only
# (Km, Qd, Lt, Dr, Jr, ...) were left to the default rule instead of forced upper case.
# UF codes are not mined: they come from the domain's own ``UF`` enum.
_INSTITUTIONAL_ACRONYMS: frozenset[str] = frozenset(
    {
        # The place from the tool contract example (issue #48, the captain: "esse Ieptec
        # realmente está estranho... quero maiúsculo") and one Instituto Federal per UF.
        "IEPTEC",
        "IFAC",
        "IFAL",
        "IFAM",
        "IFAP",
        "IFB",
        "IFBA",
        "IFBAIANO",
        "IFC",
        "IFCE",
        "IFES",
        "IFET",
        "IFF",
        "IFFAR",
        "IFG",
        "IFGO",
        "IFGOIANO",
        "IFMA",
        "IFMG",
        "IFMS",
        "IFMT",
        "IFNMG",
        "IFPA",
        "IFPB",
        "IFPE",
        "IFPI",
        "IFPR",
        "IFRJ",
        "IFRN",
        "IFRO",
        "IFRR",
        "IFRS",
        "IFS",
        "IFSC",
        "IFSP",
        "IFSUL",
        "IFTO",
        # School and social-assistance institution acronyms.
        "AE",
        "APAE",
        "BNH",
        "CAIC",
        "CDP",
        "CEI",
        "CEMEI",
        "CIEP",
        "CL",
        "CMEI",
        "CRAS",
        "CREAS",
        "CTG",
        "EE",
        "EEB",
        "EEEF",
        "EEEFM",
        "EEF",
        "EMEB",
        "EMEF",
        "EMEI",
        "EMEIEF",
        "EMEIF",
        "LC",
        "PSF",
        "PTC",
        "UBS",
        "UE",
        "UME",
        # Brasília's superquadra addressing codes and the RS state highway prefix.
        "QN",
        "QR",
        "QS",
        "RST",
        "SQN",
        "SQS",
        # A president's initials, kept upper case in street names ("Avenida JK").
        "JK",
        # "sem número" written without the slash (with the slash, S/N is untouched: each
        # single letter around the "/" already stays as-is under the default rule).
        "SN",
    }
)

ACRONYMS: frozenset[str] = _INSTITUTIONAL_ACRONYMS | {uf.value for uf in UF}

# Standard validating pattern for a well-formed Roman numeral (1-3999), grouped by
# thousands/hundreds/tens/units so "MIL" or "DIA" (ordinary Portuguese words that happen to
# use only M/C/D/X/L/V/I) do not match, while "XV" (as in "Rua XV de Novembro") and "II" do.
_ROMAN_NUMERAL_RE = re.compile(r"^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")

# A run of letters (Unicode-aware, so accents count), used to walk a chunk that has
# punctuation glued to it (D'ÁGUA, S/N, SANT'ANA) one run at a time.
_LETTER_RUN_RE = re.compile(r"[^\W\d_]+")


def title_case_pt(text: str, *, acronyms: frozenset[str] = ACRONYMS) -> str:
    """Title case with Portuguese connectives lower case (except first or last word) and
    members of ``acronyms`` kept upper case; inner whitespace collapses like
    ``normalize_text``.

    A chunk that is a single word is cased as a whole (so the connective rule applies to
    it). A chunk with punctuation glued to it, such as ``D'AGUA`` or ``S/N``, is cased one
    letter run at a time instead, since a connective is only ever a whole word on its own.

    The last word is also exempt from the connective rule, alongside the first: a name never
    trails off on a bare preposition, so a one-letter last word is a letter designation
    instead (Brasília's "Setor A"/"Setor O", real data), not the article/preposition it
    happens to spell.
    """
    words = text.split()
    last = len(words) - 1
    return " ".join(
        _case_chunk(word, acronyms, is_edge=index in (0, last)) for index, word in enumerate(words)
    )


def _case_chunk(chunk: str, acronyms: frozenset[str], *, is_edge: bool) -> str:
    if _LETTER_RUN_RE.fullmatch(chunk):
        return _case_word(chunk, acronyms, is_edge=is_edge, is_whole_chunk=True)
    return _LETTER_RUN_RE.sub(
        lambda m: _case_word(
            m.group(0), acronyms, is_edge=is_edge and m.start() == 0, is_whole_chunk=False
        ),
        chunk,
    )


def _case_word(word: str, acronyms: frozenset[str], *, is_edge: bool, is_whole_chunk: bool) -> str:
    upper = word.upper()
    if upper in acronyms:
        return upper
    if is_whole_chunk and not is_edge and word.lower() in CONNECTIVES:
        return word.lower()
    if _ROMAN_NUMERAL_RE.fullmatch(upper):
        return upper
    return word.capitalize()
