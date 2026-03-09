from collections.abc import Iterable
from dataclasses import dataclass, field, fields, replace
from typing import Any, TypeVar, cast

from languages import LangCode

from .registry import Marker, TrackAttr
from .values import MIN_MATCH_WEIGHT, AttrVal, OrgList, TrackAttrVal

MediaT = TypeVar("MediaT", bound="Media")


@dataclass(frozen=True, slots=True)
class Track:
    lang: TrackAttrVal[LangCode] | None = field(default=None, metadata={"match_weight": 1})
    voice_type: TrackAttrVal[str] | None = field(default=None, metadata={"match_weight": 1})
    orgs: OrgList = field(default_factory=OrgList, metadata={"match_weight": 4})
    official: TrackAttrVal[str] | None = field(default=None, metadata={"match_weight": 2})
    audio_format: TrackAttrVal[str] | None = field(default=None, metadata={"match_weight": 0})
    audio_note: TrackAttrVal[str] | None = field(default=None, metadata={"match_weight": 2})
    commentary: TrackAttrVal[str] | None = field(default=None, metadata={"match_weight": 3})
    ads: TrackAttrVal[str] | None = field(default=None, metadata={"match_weight": 0})
    mature: TrackAttrVal[str] | None = field(default=None, metadata={"match_weight": 2})
    index: int | None = None

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
    tracks: tuple[Track, ...] = ()
    quality: AttrVal[str] | None = field(default=None, metadata={"media_field": True})
    codec: AttrVal[str] | None = field(default=None, metadata={"media_field": True})
    hdr: AttrVal[str] | None = field(default=None, metadata={"media_field": True})
    edition: AttrVal[str] | None = field(default=None, metadata={"media_field": True})

    def score(self) -> int:
        total = sum(
            value.score
            for field_info in fields(type(self))
            if field_info.metadata.get("media_field") and (value := getattr(self, field_info.name)) is not None
        )
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
            field_info.name: value.identity_value()
            for field_info in fields(type(self))
            if field_info.metadata.get("media_field")
            and (value := getattr(self, field_info.name)) is not None
        })
        return identity

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
            for field_info in fields(type(self))
            if field_info.metadata.get("media_field")
            and (mine_value := getattr(self, field_info.name)) is not None
            and (their_value := getattr(other, field_info.name)) is not None
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
