from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, cast

from languages import LangCode

from .models import Media, Track
from .registry import Attr, OrgAttr, TrackAttr
from .values import AttrVal, Org, OrgKind, OrgList, TrackAttrVal


@dataclass(frozen=True, slots=True)
class OrgSchema:
    studio: OrgAttr
    network: OrgAttr
    _attrs_by_name: dict[str, OrgAttr] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_attrs_by_name",
            {
                self.studio.name: self.studio,
                self.network.name: self.network,
            },
        )

    def attr(self, name: str) -> OrgAttr | None:
        return self._attrs_by_name.get(name)

    def clone(self) -> "OrgSchema":
        return replace(self, studio=self.studio.clone(), network=self.network.clone())

    def decode(self, value_id: str, *, kind: OrgKind | str | None = None) -> Org:
        target = OrgKind(kind) if kind is not None else None
        if target != OrgKind.NETWORK and (value := self.studio.get(value_id)):
            return self.studio.to_org(value)
        if target != OrgKind.STUDIO and (value := self.network.get(value_id)):
            return self.network.to_org(value, hidden=False)
        return Org(id=value_id, label=value_id, kind=target or OrgKind.UNKNOWN)


@dataclass(frozen=True, slots=True)
class TrackSchema:
    lang: TrackAttr[LangCode]
    voice_type: TrackAttr[str]
    orgs: OrgSchema
    official: TrackAttr[str]
    audio_format: TrackAttr[str]
    audio_note: TrackAttr[str]
    commentary: TrackAttr[str]
    ads: TrackAttr[str]
    mature: TrackAttr[str]
    _attrs_by_name: dict[str, TrackAttr[Any]] = field(init=False, repr=False, compare=False)
    _org_fields: frozenset[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_attrs_by_name",
            {
                "lang": cast(TrackAttr[Any], self.lang),
                "voice_type": cast(TrackAttr[Any], self.voice_type),
                self.orgs.studio.name: cast(TrackAttr[Any], self.orgs.studio),
                self.orgs.network.name: cast(TrackAttr[Any], self.orgs.network),
                "official": cast(TrackAttr[Any], self.official),
                "audio_format": cast(TrackAttr[Any], self.audio_format),
                "audio_note": cast(TrackAttr[Any], self.audio_note),
                "commentary": cast(TrackAttr[Any], self.commentary),
                "ads": cast(TrackAttr[Any], self.ads),
                "mature": cast(TrackAttr[Any], self.mature),
            },
        )
        object.__setattr__(
            self,
            "_org_fields",
            frozenset((self.orgs.studio.name, self.orgs.network.name)),
        )

    def attr(self, name: str) -> TrackAttr[Any] | None:
        return self._attrs_by_name.get(name)

    def clone(self) -> "TrackSchema":
        return replace(
            self,
            lang=self.lang.clone(),
            voice_type=self.voice_type.clone(),
            orgs=self.orgs.clone(),
            official=self.official.clone(),
            audio_format=self.audio_format.clone(),
            audio_note=self.audio_note.clone(),
            commentary=self.commentary.clone(),
            ads=self.ads.clone(),
            mature=self.mature.clone(),
        )

    def decode_identity(self, data: Mapping[str, object]) -> Track | None:
        track_fields: dict[str, Any] = {}
        for field_name, value_id in data.items():
            if field_name == "orgs":
                if isinstance(value_id, list):
                    decoded = [self.orgs.decode(org_id) for org_id in value_id if isinstance(org_id, str)]
                    if decoded:
                        track_fields["orgs"] = OrgList(tuple(decoded))
                continue
            if org_attr := self.orgs.attr(field_name):
                if isinstance(value_id, str):
                    current = cast(OrgList, track_fields.get("orgs", OrgList()))
                    track_fields["orgs"] = current.merged((self.orgs.decode(value_id, kind=org_attr.kind),))
                continue
            if not isinstance(value_id, str):
                continue
            if attr := self.attr(field_name):
                track_fields[field_name] = attr.get(value_id) or TrackAttrVal(id=value_id, label=value_id)
        return Track(**track_fields) if track_fields else None

    def resolve_unknown_orgs(
        self,
        track: Track,
        *,
        normalize: Callable[[str, str], AttrVal[Any] | None],
        infer_lang: Callable[[str], TrackAttrVal[LangCode] | None],
    ) -> Track:
        if not track.orgs:
            return track

        resolved = OrgList()
        official = track.official
        lang = track.lang

        for org in track.orgs:
            current = org
            if org.kind == OrgKind.UNKNOWN and org.confidence < 0:
                raw = org.id
                for attr in (self.orgs.studio, self.orgs.network):
                    known = normalize(attr.name, raw)
                    if not isinstance(known, TrackAttrVal):
                        known = attr.find(raw)
                    if known is None:
                        continue
                    current = attr.to_org(
                        cast(TrackAttrVal[str], known),
                        confidence=org.confidence,
                        anchored=org.anchored,
                        hidden=False,
                    )
                    if attr.kind == OrgKind.NETWORK and official is None:
                        official = replace(self.official["official"], confidence=org.confidence)
                    break
                if lang is None and (inferred := infer_lang(raw)):
                    lang = inferred
            resolved = resolved.merged((current,))

        changes: dict[str, Any] = {}
        if resolved != track.orgs:
            changes["orgs"] = resolved
        if official != track.official:
            changes["official"] = official
        if lang != track.lang:
            changes["lang"] = lang
        return replace(track, **changes) if changes else track


@dataclass(frozen=True, slots=True)
class MediaSchema:
    track: TrackSchema
    quality: Attr[str]
    codec: Attr[str]
    hdr: Attr[str]
    edition: Attr[str]
    _attrs_by_name: dict[str, Attr[Any]] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_attrs_by_name",
            {
                "quality": cast(Attr[Any], self.quality),
                "codec": cast(Attr[Any], self.codec),
                "hdr": cast(Attr[Any], self.hdr),
                "edition": cast(Attr[Any], self.edition),
            },
        )

    def attr(self, name: str) -> Attr[Any] | None:
        return self._attrs_by_name.get(name)

    def clone(self) -> "MediaSchema":
        return replace(
            self,
            track=self.track.clone(),
            quality=self.quality.clone(),
            codec=self.codec.clone(),
            hdr=self.hdr.clone(),
            edition=self.edition.clone(),
        )

    def decode_identity(self, data: Mapping[str, object]) -> Media:
        raw_track = None
        raw_tracks = data.get("tracks")
        if isinstance(raw_tracks, list):
            raw_track = next((item for item in raw_tracks if isinstance(item, dict)), None)
        elif isinstance(data.get("track"), dict):
            raw_track = cast(dict[str, object], data.get("track"))

        track = self.track.decode_identity(raw_track) if isinstance(raw_track, Mapping) else None

        raw_media = data.get("media")
        media_source = raw_media if isinstance(raw_media, Mapping) else data
        media_fields: dict[str, AttrVal[Any]] = {}
        for field_name, value_id in cast(Mapping[str, object], media_source).items():
            if not isinstance(value_id, str):
                continue
            if attr := self.attr(field_name):
                media_fields[field_name] = attr.get(value_id) or AttrVal(id=value_id, label=value_id)

        return Media(tracks=(track,) if track else (), **media_fields)
