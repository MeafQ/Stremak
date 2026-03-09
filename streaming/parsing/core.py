import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any, cast

from languages import LangCode

from .models import Media, MediaMarker, Track, TrackMarker
from .registry import Marker
from .schema import MediaSchema, TrackSchema
from .values import AttrVal, Org, OrgKind, OrgList, TrackAttrVal, ValueT

_DELIMITERS = re.compile(r"[,;/\\|]+")
_BRACKETS = re.compile(r"[\[\]()+•\s]+")
_FORMATTING = re.compile(r"^[-_=~*.\s]+|[-_=~*.\s]+$")
_LANG_HINTS: dict[LangCode, re.Pattern[str]] = {
    "uk": re.compile(r"[іїєґ]", re.I),
    "ru": re.compile(r"[ыэъё]", re.I),
    "de": re.compile(r"[äöüß]", re.I),
    "fr": re.compile(r"(?:œ|æ|[àâçéèêëîïôùûüÿ])", re.I),
    "es": re.compile(r"[ñ¡¿]", re.I),
    "pt": re.compile(r"[ãõ]", re.I),
    "el": re.compile(r"[α-ωάέήίόύώϊϋΐΰ]", re.I),
    "ro": re.compile(r"[ăâîșț]", re.I),
    "pl": re.compile(r"[ąćęłńóśźż]", re.I),
    "cs": re.compile(r"[čďěňřšťůž]", re.I),
    "hu": re.compile(r"[őű]", re.I),
    "ja": re.compile(r"[ぁ-ゖァ-ヺ]", re.I),
    "ko": re.compile(r"[가-힣]", re.I),
    "th": re.compile(r"[ก-๙]", re.I),
}


@dataclass(frozen=True, slots=True)
class ParserRules:
    track_markers: tuple[TrackMarker, ...]
    media_markers: tuple[MediaMarker, ...]
    ignored_patterns: tuple[re.Pattern[str], ...] = ()

    def extend_track(self, extra: Iterable[TrackMarker]) -> "ParserRules":
        return replace(self, track_markers=(*self.track_markers, *tuple(extra)))


@dataclass(frozen=True, slots=True)
class ParserProfile:
    media: MediaSchema
    rules: ParserRules

    @property
    def track(self) -> TrackSchema:
        return self.media.track

    def clone(self) -> "ParserProfile":
        return replace(self, media=self.media.clone())

    def extend_track(self, extra: Iterable[TrackMarker], *, isolate: bool = False) -> "ParserProfile":
        profile = self.clone() if isolate else self
        return replace(profile, rules=profile.rules.extend_track(extra))

    def build_parser(self) -> "Parser":
        return Parser(self)


class Parser:
    __slots__ = (
        "profile",
        "track_markers",
        "media_markers",
        "ignored_patterns",
        "_markers_by_group",
    )

    def __init__(self, profile: ParserProfile) -> None:
        self.profile = profile
        self.track_markers = profile.rules.track_markers
        self.media_markers = profile.rules.media_markers
        self.ignored_patterns = profile.rules.ignored_patterns

        markers_by_group: dict[str, list[Marker[Any]]] = {}
        for marker in (*self.track_markers, *self.media_markers):
            for group in marker.attrs:
                markers_by_group.setdefault(group, []).append(marker)
        self._markers_by_group = markers_by_group

    @staticmethod
    def _find_matches(text: str, markers: Iterable[Marker[ValueT]]) -> list[tuple[Marker[ValueT] | None, str]]:
        matches: list[tuple[int, int, Marker[ValueT]]] = []
        for marker in markers:
            for match in marker.compiled.finditer(text):
                matches.append((match.start(), match.end(), marker))

        matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))

        tokens: list[tuple[Marker[ValueT] | None, str]] = []
        pos = 0
        for start, end, marker in matches:
            if start < pos:
                continue
            if pos < start:
                tokens.append((None, text[pos:start]))
            tokens.append((marker, text[start:end]))
            pos = end

        if pos < len(text):
            tokens.append((None, text[pos:]))

        return tokens

    def _try_merge(
        self,
        track_fields: dict[str, TrackAttrVal[Any]],
        orgs: list[Org],
        anchored: set[str],
        blocked_orgs: set[OrgKind],
        marker: TrackMarker,
        *,
        split_on_conflict: bool = True,
    ) -> bool:
        plain_attrs: list[tuple[str, TrackAttrVal[Any]]] = []
        marker_orgs: list[Org] = []

        for name, attr in marker.attrs.items():
            if org_attr := self.profile.track.orgs.attr(name):
                marker_orgs.append(org_attr.to_org(cast(TrackAttrVal[str], attr), hidden=False))
            elif self.profile.track.attr(name) is not None:
                plain_attrs.append((name, cast(TrackAttrVal[Any], attr)))

        blocked_fields = {name for name in marker.blocked if self.profile.track.attr(name) is not None}
        blocked_plain = {name for name in blocked_fields if self.profile.track.orgs.attr(name) is None}
        marker_blocked_orgs = {
            org_attr.kind
            for name in blocked_fields
            if (org_attr := self.profile.track.orgs.attr(name)) is not None
        }

        if split_on_conflict:
            for name, attr in plain_attrs:
                existing = track_fields.get(name)
                if not (attr.anchored and existing is not None and name in anchored):
                    continue
                if existing.id != attr.id or marker.blocked:
                    return False
            for name in blocked_plain:
                if track_fields.get(name) is not None and name in anchored:
                    return False
            if marker_blocked_orgs and any(org.anchored and org.kind in marker_blocked_orgs for org in orgs):
                return False
            if blocked_orgs and any(org.kind in blocked_orgs for org in marker_orgs):
                return False

        for name, attr in plain_attrs:
            existing = track_fields.get(name)
            if attr.anchored:
                if existing is None or existing.id != attr.id or attr.confidence > existing.confidence:
                    track_fields[name] = attr
                anchored.add(name)
            elif existing is None or attr.confidence > existing.confidence:
                track_fields[name] = attr

        if marker_orgs:
            merged_orgs = OrgList(tuple(orgs)).merged(marker_orgs)
            orgs[:] = list(merged_orgs)

        anchored.update(blocked_plain)
        blocked_orgs.update(marker_blocked_orgs)
        return True

    def _infer_lang_from_text(self, text: str) -> TrackAttrVal[LangCode] | None:
        matched: list[LangCode] = [code for code, pattern in _LANG_HINTS.items() if pattern.search(text)]
        if len(matched) != 1:
            return None
        return replace(self.profile.track.lang[matched[0]], confidence=-10)

    def normalize(self, group: str, value: str) -> AttrVal[Any] | None:
        return next(
            (marker.attrs[group] for marker in self._markers_by_group.get(group, []) if marker.compiled.search(value)),
            None,
        )

    def _build_tracks(self, text: str, confidence_offset: int = 0, *, expected_tracks: int | None = None) -> list[Track]:
        groups: list[TrackMarker | str] = []
        for marker, matched_text in self._find_matches(text, self.track_markers):
            if marker is None:
                for part in _DELIMITERS.split(matched_text):
                    cleaned = _BRACKETS.sub(" ", part).strip()
                    cleaned = _FORMATTING.sub("", cleaned)
                    if cleaned:
                        groups.append(cleaned)
            else:
                groups.append(marker)

        tracks: list[Track] = []
        current_fields: dict[str, TrackAttrVal[Any]] = {}
        current_orgs: list[Org] = []
        current_anchored: set[str] = set()
        current_blocked_orgs: set[OrgKind] = set()

        def flush_current() -> None:
            if current_fields or current_orgs:
                tracks.append(Track(orgs=OrgList(tuple(current_orgs)), **cast(Any, current_fields)))

        for group in groups:
            if isinstance(group, str):
                org = Org(id=group, label=group, confidence=-10, anchored=True, kind=OrgKind.UNKNOWN)
                should_split = any(existing.kind == OrgKind.UNKNOWN and existing.anchored for existing in current_orgs)
                if should_split and (expected_tracks is None or len(tracks) < expected_tracks - 1):
                    flush_current()
                    current_fields = {}
                    current_orgs = [org]
                    current_anchored = set()
                    current_blocked_orgs = set()
                else:
                    current_orgs = list(OrgList(tuple(current_orgs)).merged((org,)))
            else:
                allow_split = expected_tracks is None or len(tracks) < expected_tracks - 1
                if not self._try_merge(
                    current_fields,
                    current_orgs,
                    current_anchored,
                    current_blocked_orgs,
                    group,
                    split_on_conflict=allow_split,
                ):
                    flush_current()
                    current_fields = {}
                    current_orgs = []
                    current_anchored = set()
                    current_blocked_orgs = set()
                    self._try_merge(
                        current_fields,
                        current_orgs,
                        current_anchored,
                        current_blocked_orgs,
                        group,
                        split_on_conflict=False,
                    )

        flush_current()

        if not tracks:
            tracks.append(Track())

        tracks = [
            self.profile.track.resolve_unknown_orgs(
                track,
                normalize=self.normalize,
                infer_lang=self._infer_lang_from_text,
            )
            for track in tracks
        ]
        if confidence_offset:
            tracks = [track.with_confidence(confidence_offset) for track in tracks]
        return tracks

    def parse_track(self, text: str) -> Track:
        for pattern in self.ignored_patterns:
            text = pattern.sub("", text)
        return self._build_tracks(text, expected_tracks=1)[0]

    def parse_label(
        self,
        text: str,
        *,
        confidence_offset: int = 0,
        expected_tracks: int | None = None,
    ) -> Media:
        for pattern in self.ignored_patterns:
            text = pattern.sub("", text)

        media: dict[str, AttrVal[Any]] = {}
        remaining_parts: list[str] = []
        for marker, matched_text in self._find_matches(text, self.media_markers):
            if marker is None:
                remaining_parts.append(matched_text)
            else:
                for name in marker.attrs:
                    media.setdefault(name, marker.attrs[name])

        remaining = "".join(remaining_parts)
        tracks = self._build_tracks(remaining, confidence_offset, expected_tracks=expected_tracks)
        return Media(tracks=tuple(tracks), **media)
