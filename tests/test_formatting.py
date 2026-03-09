from streaming.base import Stream
from streaming.parsing.catalog import Edition, Lang, Official, VoiceType
from streaming.parsing.core import Track
from streaming.parsing.formatting import MESSAGES


def test_stream_format_uses_default_russian_labels():
    stream = Stream(
        url="http://test",
        tracks=(Track(lang=Lang["ru"], voice_type=VoiceType["DUB"], official=Official["official"]),),
        edition=Edition["directors_cut"],
    )

    formatted = stream.format()

    assert "Офиц." in formatted
    assert "Реж. версия" in formatted


def test_stream_format_translates_known_labels_to_english():
    stream = Stream(
        url="http://test",
        tracks=(Track(lang=Lang["ru"], voice_type=VoiceType["DUB"], official=Official["official"]),),
        edition=Edition["directors_cut"],
    )

    formatted = stream.format(locale="en")

    assert "Official" in formatted
    assert "Director's Cut" in formatted


def test_stream_format_translates_known_labels_to_ukrainian():
    stream = Stream(
        url="http://test",
        tracks=(Track(lang=Lang["uk"], voice_type=VoiceType["DUB"], official=Official["official"]),),
        edition=Edition["directors_cut"],
    )

    formatted = stream.format(locale="uk")

    assert "Офіц." in formatted
    assert "Реж. версія" in formatted


def test_stream_format_handles_missing_language():
    stream = Stream(
        url="http://test",
        tracks=(Track(voice_type=VoiceType["DUB"], official=Official["official"]),),
    )

    formatted = stream.format()

    assert "❓" in formatted


def test_messages_fallback_to_default_locale():
    assert MESSAGES["uk"]["track.unknown"] == "Невідомо"
    assert MESSAGES["pl"]["track.unknown"] == "Неизвестно"
