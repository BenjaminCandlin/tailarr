"""Turning language codes such as "eng", "fre" or "pt-BR" into names such as "English".

The list of codes comes from MKVToolNix itself (``languages.tsv``), so every
language mkvmerge can write has a name here.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

_DATA = Path(__file__).with_name("languages.tsv")

# Shorter or friendlier names than the official ones.
_NAME_OVERRIDES = {
    "und": "Unknown language",
    "zxx": "No language",
    "mul": "Several languages",
    "mis": "Other language",
    "gre": "Greek",
    "grc": "Ancient Greek",
}

# ISO 639-2 has two codes for some languages ("fre" and "fra"); mkvmerge uses the first.
_TERMINOLOGY_CODES = {
    "sqi": "alb",
    "hye": "arm",
    "eus": "baq",
    "mya": "bur",
    "zho": "chi",
    "ces": "cze",
    "nld": "dut",
    "fra": "fre",
    "kat": "geo",
    "deu": "ger",
    "ell": "gre",
    "isl": "ice",
    "mkd": "mac",
    "mri": "mao",
    "msa": "may",
    "fas": "per",
    "ron": "rum",
    "slk": "slo",
    "bod": "tib",
    "cym": "wel",
}

# Country/script parts of codes like "pt-BR", "es-419" or "zh-Hant".
_REGIONS = {
    "419": "Latin America",
    "AR": "Argentina",
    "AT": "Austria",
    "AU": "Australia",
    "BE": "Belgium",
    "BR": "Brazil",
    "CA": "Canada",
    "CH": "Switzerland",
    "CN": "China",
    "DE": "Germany",
    "ES": "Spain",
    "FR": "France",
    "GB": "UK",
    "HK": "Hong Kong",
    "IE": "Ireland",
    "IN": "India",
    "MX": "Mexico",
    "NZ": "New Zealand",
    "PT": "Portugal",
    "SG": "Singapore",
    "TW": "Taiwan",
    "US": "US",
    "Hans": "Simplified",
    "Hant": "Traditional",
    "Latn": "Latin script",
    "Cyrl": "Cyrillic script",
}


@cache
def _names() -> dict[str, str]:
    names: dict[str, str] = {}
    for line in _DATA.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        code2, code1, name = line.split("\t")
        name = name.removesuffix(" (macrolanguage)")
        name = _NAME_OVERRIDES.get(code2, name)
        names[code2] = name
        if code1:
            names.setdefault(code1, name)
    for terminology, bibliographic in _TERMINOLOGY_CODES.items():
        names.setdefault(terminology, names[bibliographic])
    return names


def language_name(code: str | None, ietf: str | None = None) -> str:
    """'eng' -> 'English'; 'por' + 'pt-BR' -> 'Portuguese (Brazil)'; unknown codes as given."""
    names = _names()
    base = (code or "").strip().lower()
    region = None
    if ietf and ietf.lower() != "und":
        parts = ietf.replace("_", "-").split("-")
        if not base or base == "und":
            base = parts[0].lower()
        for part in parts[1:]:
            label = _REGIONS.get(part) or _REGIONS.get(part.upper()) or _REGIONS.get(part.title())
            if label:
                region = label
                break
    if not base:
        base = "und"
    name = names.get(base, base)
    return f"{name} ({region})" if region else name


@cache
def _two_letter() -> dict[str, str]:
    codes: dict[str, str] = {}
    for line in _DATA.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        code2, code1, _ = line.split("\t")
        if code1:
            codes.setdefault(code1, code2)
    return codes


def normalize_language(code: str | None) -> str:
    """One code per language, so "fra", "fre" and "fr" all match: 'fra' -> 'fre', 'en' -> 'eng'.

    Region parts are ignored ('pt-BR' -> 'por'); empty codes become 'und' (unknown).
    """
    base = (code or "").strip().lower().replace("_", "-").split("-")[0]
    if not base:
        return "und"
    if len(base) == 2:
        base = _two_letter().get(base, base)
    return _TERMINOLOGY_CODES.get(base, base)


# Shown first when choosing languages (the rest follow alphabetically).
COMMON_LANGUAGES = (
    "eng", "fre", "ger", "spa", "ita", "por", "dut", "swe", "nor", "dan", "fin", "pol",
    "rus", "jpn", "kor", "chi", "hin", "ara", "tur", "gre", "heb", "cze", "hun", "tha",
)  # fmt: skip


def language_choices() -> list[tuple[str, str]]:
    """(code, name) pairs for language pickers: common languages first, then all others."""
    names = _names()
    common = [(code, names[code]) for code in COMMON_LANGUAGES]
    seen = set(COMMON_LANGUAGES) | set(_TERMINOLOGY_CODES) | {"und", "zxx", "mul", "mis"}
    others = sorted(
        ((code, name) for code, name in names.items() if len(code) == 3 and code not in seen),
        key=lambda pair: pair[1].casefold(),
    )
    return common + others
