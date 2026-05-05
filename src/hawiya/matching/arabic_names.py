"""Arabic name normalisation and phonetic key generation.

Implements the rules in CLAUDE.md §7. Two normalisation forms:

- ``to_canonical(name)`` — display-form: strip tashkeel, unify alef/yaa
  variants, fold hamza variants. **Preserves taa marbuta.** This is what
  we store on ``Person.canonical_name_ar``.

- ``to_matching_form(name)`` — aggressive form for comparison/blocking:
  also substitutes taa marbuta with heh and applies casefolding. NOT
  stored — computed on demand at query time.

The phonetic key is a hand-rolled Soundex-style compression that maps
similar-sounding consonants to a single class. It's good-enough blocking
for Phase 2 fuzzy matching; it is NOT used for matching in Phase 1, but
``PersonNameVariant.phonetic_key`` is populated at write time so Phase 2
queries can use the existing index.
"""

from __future__ import annotations

import re
import unicodedata

# Diacritics: tashkeel (U+064B–U+065F) + superscript alef (U+0670) +
# the dagger alef and other rare marks (U+06D6–U+06ED).
_DIACRITIC_RE = re.compile(r"[ً-ٰٟۖ-ۭ]")

# Alef forms → bare alef.
_ALEF_TRANS = str.maketrans(
    {
        "أ": "ا",  # أ
        "إ": "ا",  # إ
        "آ": "ا",  # آ
        "ٱ": "ا",  # ٱ alef wasla
    }
)

# Yeh / alef-maksura / yeh-with-hamza → bare yeh.
_YAA_TRANS = str.maketrans(
    {
        "ى": "ي",  # ى
        "ئ": "ي",  # ئ
    }
)

# Hamza-on-waw → waw. (Common normalisation; preserves the consonant.)
_HAMZA_TRANS = str.maketrans(
    {
        "ؤ": "و",  # ؤ
    }
)

# Taa marbuta → heh. Matching-form only.
_TAA_MARBUTA_TRANS = str.maketrans({"ة": "ه"})

# Arabic-script range used to detect script.
_ARABIC_RANGE = re.compile(r"[؀-ۿ]")

# Latin prefixes commonly carried over in transliteration.
_LATIN_PREFIX_RE = re.compile(
    r"^(?:al|el|bin|bint|ibn|abdul|abd\s+al|abd\s+el)[-\s]+",
    re.IGNORECASE,
)

# Arabic prefix tokens stripped before phonetic keying.
_ARABIC_PREFIXES = ("ال",)  # ال


def strip_diacritics(name: str) -> str:
    """Remove tashkeel and other Arabic combining marks."""
    return _DIACRITIC_RE.sub("", name)


def normalize_alef(name: str) -> str:
    return name.translate(_ALEF_TRANS)


def normalize_yaa(name: str) -> str:
    return name.translate(_YAA_TRANS)


def normalize_hamza(name: str) -> str:
    return name.translate(_HAMZA_TRANS)


def normalize_taa_marbuta(name: str) -> str:
    return name.translate(_TAA_MARBUTA_TRANS)


def strip_prefixes(name: str) -> str:
    """Remove leading article / honorific tokens (Arabic and Latin)."""
    if not name:
        return name
    # Latin transliteration prefixes
    stripped = _LATIN_PREFIX_RE.sub("", name).strip()
    if stripped != name:
        return stripped
    # Arabic ال
    for prefix in _ARABIC_PREFIXES:
        if stripped.startswith(prefix) and len(stripped) > len(prefix):
            return stripped[len(prefix) :]
    return stripped


def to_canonical(name: str) -> str:
    """Display-form normalisation. Preserves taa marbuta and case."""
    if not name:
        return name
    out = unicodedata.normalize("NFC", name)
    out = strip_diacritics(out)
    out = normalize_alef(out)
    out = normalize_yaa(out)
    out = normalize_hamza(out)
    return " ".join(out.split())  # collapse internal whitespace


def to_matching_form(name: str) -> str:
    """Aggressive normalisation: canonical + taa marbuta fold + casefold."""
    if not name:
        return name
    out = to_canonical(name)
    out = normalize_taa_marbuta(out)
    return out.casefold()


def is_arabic_script(text: str) -> bool:
    return bool(_ARABIC_RANGE.search(text))


# ---------------------------------------------------------------------------
# Phonetic key — hand-rolled, good-enough blocking for Phase 2.
# ---------------------------------------------------------------------------

# Consonant equivalence classes for Arabic letters.
_AR_PHONETIC_MAP: dict[str, str] = {}
for letters, code in [
    ("ب", "B"),  # ب
    ("فو", "F"),  # ف و → F (waw can be vowel)
    ("دتطض", "T"),  # د ت ط ض → T
    ("سصثش", "S"),  # س ص ث ش → S
    ("زذظ", "Z"),  # ز ذ ظ → Z
    ("ج", "J"),  # ج → J
    ("حهخ", "H"),  # ح ه خ → H
    ("عغء", "A"),  # ع غ ء → A
    ("كق", "K"),  # ك ق → K
    ("ل", "L"),  # ل
    ("م", "M"),  # م
    ("ن", "N"),  # ن
    ("ر", "R"),  # ر
    ("يا", ""),  # ي ا → drop (vowels)
]:
    for ch in letters:
        _AR_PHONETIC_MAP[ch] = code

# Latin class map (operates on uppercased ASCII).
_LATIN_PHONETIC_MAP: dict[str, str] = {}
for letters, code in [
    ("BPV", "B"),
    ("F", "F"),
    ("CGJKQX", "K"),
    ("S", "S"),
    ("Z", "Z"),
    ("DT", "T"),
    ("L", "L"),
    ("MN", "N"),
    ("R", "R"),
    ("HW", ""),  # silent in transliteration
    ("AEIOUY", ""),  # vowels dropped
]:
    for ch in letters:
        _LATIN_PHONETIC_MAP[ch] = code

PHONETIC_KEY_LENGTH = 6


def _compress(codes: list[str]) -> str:
    """Drop empty codes and collapse adjacent duplicates."""
    out: list[str] = []
    for c in codes:
        if not c:
            continue
        if out and out[-1] == c:
            continue
        out.append(c)
    return "".join(out)


def _arabic_phonetic(name: str) -> str:
    body = strip_prefixes(to_matching_form(name))
    codes = [_AR_PHONETIC_MAP.get(ch, "") for ch in body if not ch.isspace()]
    return _compress(codes)[:PHONETIC_KEY_LENGTH]


def _latin_phonetic(name: str) -> str:
    body = strip_prefixes(name).upper()
    codes = [_LATIN_PHONETIC_MAP.get(ch, "") for ch in body if ch.isalpha()]
    return _compress(codes)[:PHONETIC_KEY_LENGTH]


def phonetic_key(name: str) -> str:
    """Return a compact phonetic key for blocking. Up to 6 chars."""
    if not name or not name.strip():
        return ""
    if is_arabic_script(name):
        return _arabic_phonetic(name)
    return _latin_phonetic(name)
