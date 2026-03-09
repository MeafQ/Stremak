from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar, TypeVar

from languages import LangCode

from .registry import Marker, TrackAttr
from .values import MIN_MATCH_WEIGHT, AttrVal, OrgList, TrackAttrVal

MediaT = TypeVar("MediaT", bound="Media")


@dataclass(frozen=True, slots=True)
class Track:
    ORG_MATCH_WEIGHT: ClassVar[int] = 4
    MATCH_WEIGHTS: ClassVar[dict[str, int]] = {
        "commentary": 3,
        "official": 2,
        "audio_note": 2,
        "mature": 2,
        "lang": 1,
        "voice_type": 1,
        "audio_format": 0,
        "ads": 0,
    }

    lang: TrackAttrVal[LangCode] | None = None
    voice_type: TrackAttrVal[str] | None = None
    orgs: OrgList = field(default_factory=OrgList)
    official: TrackAttrVal[str] | None = None
    audio_format: TrackAttrVal[str] | None = None
    audio_note: TrackAttrVal[str] | None = None
    commentary: TrackAttrVal[str] | None = None
    ads: TrackAttrVal[str] | None = None
    mature: TrackAttrVal[str] | None = None
    index: int | None = None

    def score(self) -> int:
        total = sum(value.score for field in self.MATCH_WEIGHTS if (value := getattr(self, field)) is not None)
        return total + self.orgs.max_score()

    def identity_weight(self) -> int:
        weight = self.ORG_MATCH_WEIGHT if self.orgs else 0
        weight += sum(
            match_weight
            for field, match_weight in self.MATCH_WEIGHTS.items()
            if match_weight > 0 and getattr(self, field) is not None
        )
        return weight

    def identity_tokens(self, min_weight: int = MIN_MATCH_WEIGHT) -> tuple[str, ...]:
        parts: list[str] = []
        weight = 0
        if self.orgs:
            parts.extend(self.orgs.identity_ids())
            weight += self.ORG_MATCH_WEIGHT
        for field, match_weight in self.MATCH_WEIGHTS.items():
            if match_weight <= 0:
                continue
            if value := getattr(self, field):
                parts.append(value.id)
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
        if self.orgs and other.orgs:
            if not self.orgs.overlaps(other.orgs):
                return None
            agree += self.ORG_MATCH_WEIGHT
        for field, match_weight in self.MATCH_WEIGHTS.items():
            if match_weight <= 0:
                continue
            mine = getattr(self, field, None)
            theirs = getattr(other, field, None)
            if mine is None or theirs is None:
                continue
            if mine.id != theirs.id:
                return None
            agree += match_weight
        return agree

    def matches(self, other: "Track", min_weight: int = MIN_MATCH_WEIGHT) -> bool:
        if (agree := self.match_weight(other)) is None:
            return False
        return agree >= min_weight

    def with_confidence(self, offset: int) -> "Track":
        changes: dict[str, Any] = {}
        if self.orgs:
            changes["orgs"] = self.orgs.with_confidence(offset)
        for field in self.MATCH_WEIGHTS:
            value = getattr(self, field)
            if value is not None:
                changes[field] = replace(value, confidence=value.confidence + offset)
        return replace(self, **changes) if changes else self

    def enrich_from(self, source: "Track") -> "Track":
        changes: dict[str, Any] = {}
        if source.orgs:
            merged = self.orgs.merged(source.orgs)
            if merged != self.orgs:
                changes["orgs"] = merged
        for field in self.MATCH_WEIGHTS:
            mine = getattr(self, field)
            theirs = getattr(source, field)
            if theirs is None:
                continue
            if mine is None or theirs.confidence > mine.confidence:
                changes[field] = theirs
        return replace(self, **changes) if changes else self


@dataclass(frozen=True, slots=True, kw_only=True)
class Media:
    FIELDS: ClassVar[tuple[str, ...]] = ("quality", "codec", "hdr", "edition")

    tracks: tuple[Track, ...] = ()
    quality: AttrVal[str] | None = None
    codec: AttrVal[str] | None = None
    hdr: AttrVal[str] | None = None
    edition: AttrVal[str] | None = None

    def score(self) -> int:
        total = sum(value.score for field in self.FIELDS if (value := getattr(self, field)) is not None)
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
            if primary.orgs:
                track_data["orgs"] = list(primary.orgs.identity_ids())
            track_data.update({
                field: value.id
                for field, match_weight in Track.MATCH_WEIGHTS.items()
                if match_weight > 0 and (value := getattr(primary, field)) is not None
            })
            tracks.append(track_data)

        identity: dict[str, object] = {"tracks": tracks}
        identity.update({
            field: value.id
            for field in self.FIELDS
            if (value := getattr(self, field)) is not None
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
            track_exact = mine.orgs.shared_count(theirs.orgs)
            track_exact += sum(
                1
                for field, match_weight in Track.MATCH_WEIGHTS.items()
                if match_weight > 0
                and (mine_value := getattr(mine, field)) is not None
                and (their_value := getattr(theirs, field)) is not None
                and mine_value.id == their_value.id
            )

        media_exact = sum(
            1
            for field in self.FIELDS
            if (mine_value := getattr(self, field)) is not None
            and (their_value := getattr(other, field)) is not None
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
