from collections.abc import Iterable
from dataclasses import dataclass, field, fields, replace
from functools import cache
from typing import Any, ClassVar, TypeVar, cast

from languages import LangCode

from .registry import Marker, TrackAttr
from .values import MIN_MATCH_WEIGHT, AttrVal, OrgKind, OrgList, TrackAttrVal

MediaT = TypeVar("MediaT", bound="Media")


@cache
def _attr_fields(owner: type[Any]) -> dict[str, str]:
    return {
        cast(str, field_info.metadata["attr_id"]): field_info.name
        for field_info in fields(owner)
        if "attr_id" in field_info.metadata
    }


@cache
def _marker_attr_kinds(owner: type[Any]) -> dict[str, OrgKind]:
    return {
        attr_id: OrgKind(kind)
        for field_info in fields(owner)
        for attr_id, kind in cast(dict[str, OrgKind | str], field_info.metadata.get("marker_attr_kinds", {})).items()
    }


@dataclass(frozen=True, slots=True)
class Track:
    PARSING_GROUP: ClassVar[str] = "track"

    lang: TrackAttrVal[LangCode] | None = field(default=None, metadata={"attr_id": "lang", "match_weight": 1})
    voice_type: TrackAttrVal[str] | None = field(default=None, metadata={"attr_id": "voice_type", "match_weight": 1})
    orgs: OrgList = field(
        default_factory=OrgList,
        metadata={
            "match_weight": 4,
            "marker_attr_kinds": {
                "studio": OrgKind.STUDIO,
                "network": OrgKind.NETWORK,
            },
        },
    )
    official: TrackAttrVal[str] | None = field(default=None, metadata={"attr_id": "official", "match_weight": 2})
    audio_format: TrackAttrVal[str] | None = field(default=None, metadata={"attr_id": "audio_format", "match_weight": 0})
    audio_note: TrackAttrVal[str] | None = field(default=None, metadata={"attr_id": "audio_note", "match_weight": 2})
    commentary: TrackAttrVal[str] | None = field(default=None, metadata={"attr_id": "commentary", "match_weight": 3})
    ads: TrackAttrVal[str] | None = field(default=None, metadata={"attr_id": "ads", "match_weight": 0})
    mature: TrackAttrVal[str] | None = field(default=None, metadata={"attr_id": "mature", "match_weight": 2})
    index: int | None = None

    @classmethod
    def attr_ids(cls) -> tuple[str, ...]:
        return tuple(cls.attr_fields())

    @classmethod
    def attr_fields(cls) -> dict[str, str]:
        return dict(_attr_fields(cls))

    @classmethod
    def attr_field_name(cls, attr_id: str) -> str | None:
        return _attr_fields(cls).get(attr_id)

    @classmethod
    def marker_attr_kinds(cls) -> dict[str, OrgKind]:
        return dict(_marker_attr_kinds(cls))

    @classmethod
    def marker_attr_ids(cls) -> tuple[str, ...]:
        return (*cls.attr_ids(), *cls.marker_attr_kinds())

    def score(self) -> int:
        total = 0
        for field_info in fields(type(self)):
            if "match_weight" not in field_info.metadata:
                continue
            value = cast(Any, getattr(self, field_info.name))
            if value:
                total += value.score
        return total

    def identity_weight(self) -> int:
        return sum(
            cast(int, field_info.metadata["match_weight"])
            for field_info in fields(type(self))
            if cast(int, field_info.metadata.get("match_weight", 0)) > 0
            and getattr(self, field_info.name)
        )

    def identity_tokens(self, min_weight: int = MIN_MATCH_WEIGHT) -> tuple[str, ...]:
        parts: list[str] = []
        weight = 0
        ordered_fields = sorted(
            (
                (index, field_info)
                for index, field_info in enumerate(fields(type(self)))
                if "match_weight" in field_info.metadata
            ),
            key=lambda item: (-cast(int, item[1].metadata.get("match_weight", 0)), item[0]),
        )
        for _, field_info in ordered_fields:
            match_weight = cast(int, field_info.metadata.get("match_weight", 0))
            if match_weight <= 0:
                continue
            if value := cast(Any, getattr(self, field_info.name)):
                parts.extend(value.identity_ids())
                weight += match_weight
            if weight >= min_weight:
                break
        if weight < min_weight and self.index is not None:
            parts.append(str(self.index))
        return tuple(parts)

    def with_language(self, lang: LangCode, *, lang_attr: TrackAttr[LangCode]) -> "Track":
        if value := lang_attr.get(lang):
            return replace(self, lang=value)
        return self

    def with_original(self, *, voice_type_attr: TrackAttr[str]) -> "Track":
        return replace(self, voice_type=voice_type_attr["OG"])

    def match_weight(self, other: "Track") -> int | None:
        agree = 0
        for field_info in fields(type(self)):
            match_weight = cast(int, field_info.metadata.get("match_weight", 0))
            if match_weight <= 0:
                continue
            mine = cast(Any, getattr(self, field_info.name))
            theirs = cast(Any, getattr(other, field_info.name))
            if not mine or not theirs:
                continue
            if not mine.matches(theirs):
                return None
            agree += match_weight
        return agree

    def matches(self, other: "Track", min_weight: int = MIN_MATCH_WEIGHT) -> bool:
        if (agree := self.match_weight(other)) is None:
            return False
        return agree >= min_weight

    def with_confidence(self, offset: int) -> "Track":
        changes: dict[str, Any] = {}
        for field_info in fields(type(self)):
            if "match_weight" not in field_info.metadata:
                continue
            value = cast(Any, getattr(self, field_info.name))
            if value:
                changes[field_info.name] = value.with_confidence(offset)
        return replace(self, **changes) if changes else self

    def enrich_from(self, source: "Track") -> "Track":
        changes: dict[str, Any] = {}
        for field_info in fields(type(self)):
            if "match_weight" not in field_info.metadata:
                continue
            mine = cast(Any, getattr(self, field_info.name))
            theirs = cast(Any, getattr(source, field_info.name))
            if not theirs:
                continue
            if not mine:
                changes[field_info.name] = theirs
                continue
            merged = mine.merged(theirs)
            if merged != mine:
                changes[field_info.name] = merged
        return replace(self, **changes) if changes else self


@dataclass(frozen=True, slots=True, kw_only=True)
class Media:
    PARSING_GROUP: ClassVar[str] = "media"

    tracks: tuple[Track, ...] = ()
    quality: AttrVal[str] | None = field(default=None, metadata={"attr_id": "quality"})
    codec: AttrVal[str] | None = field(default=None, metadata={"attr_id": "codec"})
    hdr: AttrVal[str] | None = field(default=None, metadata={"attr_id": "hdr"})
    edition: AttrVal[str] | None = field(default=None, metadata={"attr_id": "edition"})

    @classmethod
    def attr_ids(cls) -> tuple[str, ...]:
        return tuple(cls.attr_fields())

    @classmethod
    def attr_fields(cls) -> dict[str, str]:
        return dict(_attr_fields(cls))

    @classmethod
    def attr_field_name(cls, attr_id: str) -> str | None:
        return _attr_fields(cls).get(attr_id)

    @classmethod
    def marker_attr_kinds(cls) -> dict[str, OrgKind]:
        return {}

    @classmethod
    def marker_attr_ids(cls) -> tuple[str, ...]:
        return (*cls.attr_ids(), *cls.marker_attr_kinds())

    def attr_items(self) -> tuple[tuple[str, AttrVal[str]], ...]:
        return tuple(
            (field_name, cast(AttrVal[str], value))
            for field_name in type(self).attr_fields().values()
            if (value := getattr(self, field_name)) is not None
        )

    def score(self) -> int:
        total = sum(value.score for _, value in self.attr_items())
        if self.tracks:
            total += max(track.score() for track in self.tracks)
        return total

    def primary_track(self) -> Track | None:
        return self.tracks[0] if self.tracks else None

    def required_match_weight(self, min_weight: int = MIN_MATCH_WEIGHT) -> int:
        if primary := self.primary_track():
            return min(min_weight, primary.identity_weight())
        return 0

    def has_min_identity(self, min_weight: int = MIN_MATCH_WEIGHT) -> bool:
        if primary := self.primary_track():
            return primary.identity_weight() >= min_weight
        return False

    def identity(self) -> dict[str, object]:
        tracks: list[dict[str, Any]] = []
        if primary := self.primary_track():
            track_data: dict[str, Any] = {}
            for field_info in fields(Track):
                match_weight = cast(int, field_info.metadata.get("match_weight", 0))
                if match_weight <= 0:
                    continue
                if value := cast(Any, getattr(primary, field_info.name)):
                    track_data[field_info.name] = value.identity_value()
            tracks.append(track_data)

        identity: dict[str, object] = {"tracks": tracks}
        identity.update({
            field_name: value.identity_value()
            for field_name, value in self.attr_items()
        })
        return identity

    def group_tokens(self) -> tuple[str, ...]:
        parts: list[str] = []
        if primary := self.primary_track():
            parts.extend(primary.identity_tokens())
        parts.extend(value.id for _, value in self.attr_items())
        return tuple(parts)

    def match_score(self, other: "Media") -> tuple[int, int, int] | None:
        track_weight = 0
        track_exact = 0

        mine = self.primary_track()
        theirs = other.primary_track()
        if mine is not None:
            if theirs is None:
                return None
            if (track_weight := mine.match_weight(theirs)) is None:
                return None
            track_exact = sum(
                cast(Any, getattr(mine, field_info.name)).shared_count(cast(Any, getattr(theirs, field_info.name)))
                for field_info in fields(Track)
                if cast(int, field_info.metadata.get("match_weight", 0)) > 0
                and getattr(mine, field_info.name)
                and getattr(theirs, field_info.name)
            )

        media_exact = sum(
            1
            for field_name in type(self).attr_fields().values()
            if (mine_value := getattr(self, field_name)) is not None
            and (their_value := getattr(other, field_name)) is not None
            and mine_value.id == their_value.id
        )

        return track_weight, media_exact, track_exact

    def match_candidates(
        self,
        candidates: Iterable[MediaT],
        *,
        min_weight: int = MIN_MATCH_WEIGHT,
    ) -> tuple[int, list[tuple[tuple[int, int, int], MediaT]]]:
        required_weight = self.required_match_weight(min_weight=min_weight)
        scored = [
            (score, candidate)
            for candidate in candidates
            if (score := self.match_score(candidate)) is not None and score[0] >= required_weight
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return required_weight, scored


TrackMarker = Marker[TrackAttrVal[Any]]
MediaMarker = Marker[AttrVal[Any]]
