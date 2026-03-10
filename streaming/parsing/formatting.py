from collections import ChainMap
from collections.abc import Mapping

from languages import language_to_flag

from .models import Media
from .specs import DEFAULT_PARSING_SPECS, ParsingSpecs
from .values import AttrVal

DEFAULT_LOCALE = "ru"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ru": {
        "track.unknown": "Неизвестно",
        "official.official": "Офиц.",
        "official.unofficial": "Неофиц.",
        "audio_note.clean": "🔇 Чист. звук",
        "commentary.commentary": "💬 Комментарии",
        "ads.ads": "📣 Реклама",
        "edition.directors_cut": "🎬 Реж. версия",
        "edition.extended": "🎬 Расш. версия",
        "edition.uncut": "🎬 Полная версия",
        "edition.theatrical": "Театр. версия",
        "edition.combined": "⚠️ Все серии",
    },
    "en": {
        "track.unknown": "Unknown",
        "official.official": "Official",
        "official.unofficial": "Unofficial",
        "audio_note.clean": "🔇 Clean audio",
        "commentary.commentary": "💬 Commentary",
        "ads.ads": "📣 Ads",
        "edition.directors_cut": "🎬 Director's Cut",
        "edition.extended": "🎬 Extended Edition",
        "edition.uncut": "🎬 Uncut",
        "edition.theatrical": "Theatrical",
        "edition.combined": "⚠️ All episodes",
    },
    "uk": {
        "track.unknown": "Невідомо",
        "official.official": "Офіц.",
        "official.unofficial": "Неофіц.",
        "audio_note.clean": "🔇 Чист. звук",
        "commentary.commentary": "💬 Коментарі",
        "ads.ads": "📣 Реклама",
        "edition.directors_cut": "🎬 Реж. версія",
        "edition.extended": "🎬 Розш. версія",
        "edition.uncut": "🎬 Повна версія",
        "edition.theatrical": "Театр. версія",
        "edition.combined": "⚠️ Усі серії",
    },
}


class TranslationCatalog:
    __slots__ = ("default_locale", "_messages")

    def __init__(self, messages: dict[str, dict[str, str]], *, default_locale: str) -> None:
        self.default_locale = default_locale
        self._messages = messages

    def __getitem__(self, locale: str) -> Mapping[str, str]:
        locale = locale or self.default_locale
        return ChainMap(self._messages.get(locale, {}), self._messages[self.default_locale])

    def display(self, value: AttrVal[str] | None, messages: Mapping[str, str]) -> str | None:
        if value is None or value.hidden:
            return None
        if value.msgid:
            return messages[value.msgid]
        return value.display or value.id


MESSAGES = TranslationCatalog(TRANSLATIONS, default_locale=DEFAULT_LOCALE)


def _track_messages(locale: str, track_lang: str | None) -> Mapping[str, str]:
    if track_lang and track_lang in TRANSLATIONS:
        return MESSAGES[track_lang]
    return MESSAGES[locale]


def _fallback_locale(
    specs: ParsingSpecs = DEFAULT_PARSING_SPECS,
) -> str:
    lang_spec = specs.attr("lang")
    ordered_langs = tuple(lang_spec.ui_values)
    return max(
        ordered_langs,
        key=lambda lang: (lang_spec[lang].score, -ordered_langs.index(lang)),
    )


def format_stream(
    media: Media,
    *,
    specs: ParsingSpecs = DEFAULT_PARSING_SPECS,
) -> str:
    fallback_locale = _fallback_locale(specs=specs)
    messages = MESSAGES[fallback_locale]
    sections: list[str] = []

    if media.tracks:
        for track in media.tracks:
            track_messages = _track_messages(fallback_locale, track.lang.id if track.lang else None)
            if track.lang is None:
                flag = "❓"
            else:
                try:
                    flag = language_to_flag(track.lang.id)
                except ValueError:
                    flag = "❓"

            details: list[str] = []
            if track.voice_type and (value := MESSAGES.display(track.voice_type, track_messages)):
                details.append(value)

            org_values = [value for org in track.orgs if (value := MESSAGES.display(org, track_messages))]
            if org_values:
                details.append(f"[{' / '.join(org_values)}]")
            elif track.official and (value := MESSAGES.display(track.official, track_messages)):
                details.append(f"[{value}]")

            if not details:
                details.append(track_messages["track.unknown"])

            sections.append(f'{flag} · {" ".join(details)}')

            tags = [
                value
                for attr in (track.audio_note, track.audio_format, track.ads, track.mature)
                if (value := MESSAGES.display(attr, track_messages))
            ]
            if tags:
                sections.append(f" ┝  {', '.join(tags)}")

    tech_parts = [
        value
        for attr in (media.quality, media.hdr, media.edition)
        if (value := MESSAGES.display(attr, messages))
    ]
    if tech_parts:
        sections.append(f" ┕  {', '.join(tech_parts)}")

    return "\n".join(sections)
