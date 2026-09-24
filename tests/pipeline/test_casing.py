"""``title_case_pt``: the casing rule for names, addresses and civil names
(docs/codebase-design.md, section 7). Ballot names are never passed through it."""

from __future__ import annotations

from br_elections_mcp.pipeline.casing import ACRONYMS, title_case_pt


def test_plain_words_are_capitalized():
    assert title_case_pt("ESCOLA MUNICIPAL SÃO JOSÉ") == "Escola Municipal São José"


def test_connectives_stay_lower_case_except_as_the_first_word():
    assert title_case_pt("RIO BRANCO DO IVAÍ") == "Rio Branco do Ivaí"
    assert title_case_pt("INSTITUTO FEDERAL DO ACRE") == "Instituto Federal do Acre"
    assert title_case_pt("TEREZINHA DE JESUS MELO") == "Terezinha de Jesus Melo"
    # A connective as the very first word of the string is still capitalized.
    assert title_case_pt("DOS SANTOS") == "Dos Santos"


def test_acronyms_stay_upper_case_wherever_they_appear():
    assert (
        title_case_pt("IEPTEC - ANTIGO INSTITUTO FEDERAL DO ACRE - IFAC -  BAIXADA")
        == "IEPTEC - Antigo Instituto Federal do Acre - IFAC - Baixada"
    )
    # Real UF codes glued to a municipality name by a slash or hyphen (issue #48 evidence).
    assert title_case_pt("ALHANDRA/PB") == "Alhandra/PB"
    assert title_case_pt("NATAL-RN") == "Natal-RN"


def test_roman_numerals_stay_upper_case():
    assert title_case_pt("RUA XV DE NOVEMBRO") == "Rua XV de Novembro"
    assert title_case_pt("DOM PEDRO II") == "Dom Pedro II"
    assert title_case_pt("PAPA JOAO XXIII") == "Papa Joao XXIII"


def test_ordinary_words_spelled_only_with_roman_letters_are_not_mistaken_for_numerals():
    # "MIL" (thousand) and "DIA" (day) are ordinary Portuguese words, not roman numerals.
    assert title_case_pt("MIL") == "Mil"
    assert title_case_pt("UM DIA") == "Um Dia"


def test_apostrophe_word_capitalizes_each_side():
    assert title_case_pt("SANT'ANA DO LIVRAMENTO") == "Sant'Ana do Livramento"
    assert title_case_pt("IGREJA N. SRA. D'AJUDA") == "Igreja N. Sra. D'Ajuda"


def test_hyphenated_and_slash_separated_tokens_case_each_side():
    assert title_case_pt("CENTRO ESCOLAR MÉRITO-LC-PTC") == "Centro Escolar Mérito-LC-PTC"
    assert title_case_pt("COLÉGIO ESTADUAL ALFREDO NASSER - UE-EST") == (
        "Colégio Estadual Alfredo Nasser - UE-Est"
    )


def test_sem_numero_with_and_without_the_slash_is_untouched():
    assert title_case_pt("AV. PALMEIRAS, SN") == "Av. Palmeiras, SN"
    assert title_case_pt("RUA FORTUNATO BITTENCOURT S/N") == "Rua Fortunato Bittencourt S/N"


def test_ordinal_indicators_are_untouched():
    assert title_case_pt("AVENIDA 1º DE MAIO") == "Avenida 1º de Maio"
    assert title_case_pt("RUA 2ª TRAVESSA") == "Rua 2ª Travessa"


def test_inner_whitespace_collapses_like_normalize_text():
    assert title_case_pt("IFAC -  BAIXADA") == "IFAC - Baixada"
    assert title_case_pt("  RIO   BRANCO ") == "Rio Branco"


def test_civil_name_with_common_surname_suffixes():
    assert title_case_pt("PEDRO HENRIQUE ALVES") == "Pedro Henrique Alves"
    assert title_case_pt("JOSÉ ANTÔNIO DOS SANTOS") == "José Antônio dos Santos"


def test_all_uf_codes_are_in_the_acronym_set():
    from br_elections_mcp.domain import UF

    assert {uf.value for uf in UF} <= ACRONYMS


def test_custom_acronym_set_overrides_the_default():
    assert title_case_pt("CASA DA CULTURA", acronyms=frozenset({"CASA"})) == "CASA da Cultura"


def test_a_trailing_one_letter_word_is_a_letter_designation_not_a_connective():
    # Real Brasília satellite-city zoning ("Setor A"/"Setor O") and "Freguesia do Ó" and
    # "Nossa Senhora do Ó" with the accent lost by the source: a name never trails off on a
    # bare preposition, so the last word is exempt from the connective rule like the first.
    assert title_case_pt("SETOR A") == "Setor A"
    assert title_case_pt("EMEF TAUARY SETOR A") == "EMEF Tauary Setor A"
    assert title_case_pt("FREGUESIA DO O") == "Freguesia do O"
    assert title_case_pt("NOSSA SENHORA DO O") == "Nossa Senhora do O"
