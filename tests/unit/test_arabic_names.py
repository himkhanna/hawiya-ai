"""Unit tests for Arabic name normalisation and phonetic keys."""

from __future__ import annotations

import pytest

from hawiya.matching.arabic_names import (
    is_arabic_script,
    normalize_alef,
    normalize_taa_marbuta,
    normalize_yaa,
    phonetic_key,
    strip_diacritics,
    strip_prefixes,
    to_canonical,
    to_matching_form,
)


def test_strip_diacritics_removes_tashkeel() -> None:
    # مُحَمَّد with explicit damma + fatha + shadda + fatha
    assert strip_diacritics("مُحَمَّد") == "محمد"


def test_strip_diacritics_handles_superscript_alef() -> None:
    # هَٰذَا (with U+0670)
    assert strip_diacritics("هَٰذَا") == "هذا"


def test_normalize_alef_variants() -> None:
    assert normalize_alef("أحمد") == "احمد"
    assert normalize_alef("إبراهيم") == "ابراهيم"
    assert normalize_alef("آدم") == "ادم"


def test_normalize_yaa_alef_maksura() -> None:
    # على (with alef maksura) → علي
    assert normalize_yaa("على") == "علي"


def test_normalize_taa_marbuta() -> None:
    # فاطمة → فاطمه
    assert normalize_taa_marbuta("فاطمة") == "فاطمه"


def test_to_canonical_strips_diacritics_and_unifies_variants() -> None:
    # إِبْرَاهِيم → ابراهيم
    assert to_canonical("إِبْرَاهِيم") == "ابراهيم"


def test_to_canonical_preserves_taa_marbuta() -> None:
    assert to_canonical("فاطمة") == "فاطمة"


def test_to_canonical_collapses_whitespace() -> None:
    assert to_canonical("  محمد   علي  ") == "محمد علي"


def test_to_matching_form_folds_taa_marbuta_and_casefolds() -> None:
    assert to_matching_form("فاطمة") == "فاطمه"
    assert to_matching_form("Mohamed") == "mohamed"


def test_strip_prefixes_latin() -> None:
    assert strip_prefixes("Al-Mansoori") == "Mansoori"
    assert strip_prefixes("AL MANSOORI") == "MANSOORI"
    assert strip_prefixes("El-Sayed") == "Sayed"
    assert strip_prefixes("Bin Salman") == "Salman"
    assert strip_prefixes("Bint Khalid") == "Khalid"
    assert strip_prefixes("Ibn Sina") == "Sina"
    assert strip_prefixes("Abdul Rahman") == "Rahman"
    assert strip_prefixes("Abdul-Rahman") == "Rahman"


def test_strip_prefixes_arabic_definite_article() -> None:
    # المنصوري → منصوري
    assert strip_prefixes("المنصوري") == "منصوري"


def test_strip_prefixes_no_prefix_unchanged() -> None:
    assert strip_prefixes("Mohamed") == "Mohamed"
    assert strip_prefixes("فاطمة") == "فاطمة"


def test_is_arabic_script_detection() -> None:
    assert is_arabic_script("محمد") is True
    assert is_arabic_script("Mohamed") is False
    assert is_arabic_script("Mohamed محمد") is True  # mixed → Arabic


def test_phonetic_key_arabic_diacritic_invariance() -> None:
    # Same word with and without tashkeel must produce the same key.
    plain = "محمد"  # محمد
    with_marks = "مُحَمَّد"  # مُحَمَّد
    assert phonetic_key(plain) == phonetic_key(with_marks)


def test_phonetic_key_latin_mohamed_variants() -> None:
    # Common transliteration variants of "Mohamed" must collide.
    base = phonetic_key("Mohamed")
    assert base == phonetic_key("Mohammed")
    assert base == phonetic_key("Mohammad")
    assert base == phonetic_key("Muhammad")


def test_phonetic_key_latin_strips_prefixes() -> None:
    assert phonetic_key("Al-Mansoori") == phonetic_key("Mansoori")


def test_phonetic_key_empty_returns_empty() -> None:
    assert phonetic_key("") == ""
    assert phonetic_key("   ") == ""


def test_phonetic_key_bounded_length() -> None:
    long_name = "Abdulrahman Mohammed Al-Khalifa"
    key = phonetic_key(long_name)
    assert len(key) <= 6


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("على", "علي"),  # على ≡ علي
        ("فاطمة", "فاطمه"),  # فاطمة ≡ فاطمه
        ("أحمد", "احمد"),  # أحمد ≡ احمد
    ],
)
def test_matching_form_collapses_arabic_variants(a: str, b: str) -> None:
    assert to_matching_form(a) == to_matching_form(b)
