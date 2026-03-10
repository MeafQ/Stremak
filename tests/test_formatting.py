from streaming.base import Stream
from streaming.parsing.catalog import default_profile
from streaming.parsing.core import Track
from streaming.parsing.formatting import MESSAGES
from streaming.parsing.specs import DEFAULT_PARSING_SPECS

LANG = default_profile.track.lang
VOICE_TYPE = default_profile.track.voice_type
OFFICIAL = default_profile.track.official
EDITION = default_profile.media.edition


def _specs_with_lang_scores(scores: dict[str, int]):
    return DEFAULT_PARSING_SPECS.overlay({
            "attrs": {
                "lang": {
                    "values": {
                        lang: {"score": score}
                        for lang, score in scores.items()
                    },
                },
            },
        })


def test_stream_format_uses_default_russian_labels():
    stream = Stream(
        url="http://test",
        tracks=(Track(lang=LANG["ru"], voice_type=VOICE_TYPE["DUB"], official=OFFICIAL["official"]),),
        edition=EDITION["directors_cut"],
    )

    formatted = stream.format(specs=_specs_with_lang_scores({"ru": 3000, "uk": 2000, "en": 1000}))

    assert MESSAGES["ru"]["official.official"] in formatted
    assert MESSAGES["ru"]["edition.directors_cut"] in formatted


def test_stream_format_translates_known_labels_to_english():
    stream = Stream(
        url="http://test",
        tracks=(Track(lang=LANG["ru"], voice_type=VOICE_TYPE["DUB"], official=OFFICIAL["official"]),),
        edition=EDITION["directors_cut"],
    )

    formatted = stream.format(specs=_specs_with_lang_scores({"en": 3000, "ru": 2000, "uk": 1000}))

    assert MESSAGES["ru"]["official.official"] in formatted
    assert MESSAGES["en"]["edition.directors_cut"] in formatted


def test_stream_format_translates_known_labels_to_ukrainian():
    stream = Stream(
        url="http://test",
        tracks=(Track(lang=LANG["uk"], voice_type=VOICE_TYPE["DUB"], official=OFFICIAL["official"]),),
        edition=EDITION["directors_cut"],
    )

    formatted = stream.format(specs=_specs_with_lang_scores({"uk": 3000, "ru": 2000, "en": 1000}))

    assert MESSAGES["uk"]["official.official"] in formatted
    assert MESSAGES["uk"]["edition.directors_cut"] in formatted


def test_stream_format_handles_missing_language():
    stream = Stream(
        url="http://test",
        tracks=(Track(voice_type=VOICE_TYPE["DUB"], official=OFFICIAL["official"]),),
    )

    formatted = stream.format(specs=_specs_with_lang_scores({"ru": 3000, "uk": 2000, "en": 1000}))

    assert "❓" in formatted


def test_messages_fallback_to_default_locale():
    assert MESSAGES["uk"]["track.unknown"] == "Невідомо"
    assert MESSAGES["pl"]["track.unknown"] == "Неизвестно"
