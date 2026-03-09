from typing import TYPE_CHECKING, Annotated, Literal, NewType, cast

from annotated_types import MaxLen, MinLen
from langcodes import Language

if TYPE_CHECKING:
    LangCode = Literal[
        "ru", "uk", "en",
        "de", "fr", "es", "it", "pt",
        "nl", "el",
        "sv", "no", "da", "fi",
        "pl", "cs", "hu", "ro",
        "zh", "ja", "ko", "hi", "th",
        "id", "vi", "ms",
    ]
    LangCode3 = Literal[
        "rus", "ukr", "eng",
        "deu", "ger", "fra", "fre", "spa", "ita", "por",
        "nld", "dut", "ell", "gre",
        "swe", "nor", "dan", "fin",
        "pol", "ces", "cze", "hun", "ron", "rum",
        "zho", "chi", "jpn", "kor", "hin", "tha",
        "ind", "vie", "msa", "may",
    ]
else:
    LangCode = Annotated[str, MinLen(2), MaxLen(2)]
    LangCode3 = Annotated[str, MinLen(3), MaxLen(3)]

if TYPE_CHECKING:
    CountryCode = Literal[
        "RU", "UA", "US", "GB", "DE", "FR", "ES", "IT", "PT",
        "BR", "NL", "GR", "SE", "NO", "DK", "FI",
        "PL", "CZ", "HU", "RO",
        "CN", "JP", "KR", "IN", "TH", "ID", "VN", "MY",
    ]
else:
    CountryCode = Annotated[str, MinLen(2), MaxLen(2)]

FlagEmoji = NewType("FlagEmoji", str)
def language_to_country(code: LangCode) -> CountryCode:
    lang = Language.get(code)
    territory = lang.maximize().territory
    if not lang.is_valid() or territory is None:
        raise ValueError(f"Cannot determine country for language: {lang}")
    return cast(CountryCode, territory)

def country_to_lang(code: CountryCode) -> LangCode:
    language = Language.get(f"und-{code}").maximize().language
    if language is None:
        raise ValueError(f"Cannot determine language for country: {code}")
    return cast(LangCode, language)

def language_to_flag(code: LangCode) -> FlagEmoji:
    country = language_to_country(code)
    return FlagEmoji("".join(chr(ord(c) + 127397) for c in country.upper()))

def to_alpha2(code: LangCode3) -> LangCode | None:
    lang = Language.get(code)
    if not lang.is_valid() or not lang.language:
        return None
    alpha2 = lang.language
    if len(alpha2) != 2:
        return None
    return cast(LangCode, alpha2)

def to_alpha3(code: LangCode) -> LangCode3 | None:
    lang = Language.get(code)
    if not lang.is_valid():
        return None
    return cast(LangCode3, lang.to_alpha3())
