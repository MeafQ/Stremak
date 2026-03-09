from collections import ChainMap
from collections.abc import Mapping

from languages import language_to_flag

from .constants import DEFAULT_LOCALE, TRANSLATIONS
from .models import Media
from .values import AttrVal


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


def format_stream(media: Media, locale: str = DEFAULT_LOCALE) -> str:
    locale = locale or DEFAULT_LOCALE
    messages = MESSAGES[locale]
    sections: list[str] = []

    if media.tracks:
        for track in media.tracks:
            if track.lang is None:
                flag = "❓"
            else:
                try:
                    flag = language_to_flag(track.lang.id)
                except ValueError:
                    flag = "❓"

            details: list[str] = []
            if track.voice_type and (value := MESSAGES.display(track.voice_type, messages)):
                details.append(value)

            org_values = [value for org in track.orgs if (value := MESSAGES.display(org, messages))]
            if org_values:
                details.append(f"[{' / '.join(org_values)}]")
            elif track.official and (value := MESSAGES.display(track.official, messages)):
                details.append(f"[{value}]")

            if not details:
                details.append(messages["track.unknown"])

            sections.append(f'{flag} · {" ".join(details)}')

            tags = [
                value
                for attr in (track.audio_note, track.audio_format, track.ads, track.mature)
                if (value := MESSAGES.display(attr, messages))
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
