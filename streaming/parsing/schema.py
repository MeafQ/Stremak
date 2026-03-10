from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, replace
from typing import Any, cast

from languages import LangCode

from .models import Media, Track
from .registry import Attr, OrgAttr, TrackAttr
from .specs import MarkerSpec, ParsingSpecs, ValueSpec
from .values import AttrVal, Org, OrgKind, OrgList, TrackAttrVal


@dataclass(frozen=True, slots=True)
class OrgSchema:
    attrs: dict[str, OrgAttr]

    @classmethod
    def from_marker_specs(
        cls,
        attr_kinds: Mapping[str, OrgKind],
        marker_specs: Mapping[str, MarkerSpec],
    ) -> "OrgSchema":
        attrs = {
            attr_id: OrgAttr(attr_id, kind=kind)
            for attr_id, kind in attr_kinds.items()
        }
        for attr_id, attr in attrs.items():
            attr.add_specs(_collect_org_value_specs(marker_specs, attr_id))
        return cls(attrs)

    def __getitem__(self, name: str) -> OrgAttr:
        return self.attrs[name]

    def values(self) -> tuple[OrgAttr, ...]:
        return tuple(self.attrs.values())

    def attr(self, name: str) -> OrgAttr | None:
        return self.attrs.get(name)

    def clone(self) -> "OrgSchema":
        return replace(self, attrs={name: attr.clone() for name, attr in self.attrs.items()})

    def decode(self, value_id: str, *, kind: OrgKind | str | None = None) -> Org:
        target = OrgKind(kind) if kind is not None else None
        candidates = (self.attrs.get(target.value),) if target is not None else self.attrs.values()
        for attr in candidates:
            if attr is None:
                continue
            if value := attr.get(value_id):
                return attr.to_org(value, hidden=False)
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

    @classmethod
    def from_specs(cls, specs: ParsingSpecs) -> "TrackSchema":
        attrs = {
            attr_id: TrackAttr(attr_id)
            for attr_id in Track.attr_ids()
        }
        for attr_id, attr in attrs.items():
            attr.add_specs(specs.attr(attr_id).values)
        orgs = OrgSchema.from_marker_specs(Track.marker_attr_kinds(), specs.markers_for(Track))
        return cls.from_attrs(attrs, orgs=orgs)

    @classmethod
    def from_attrs(
        cls,
        attrs: Mapping[str, TrackAttr[Any]],
        *,
        orgs: OrgSchema,
    ) -> "TrackSchema":
        values = {
            field_name: cast(TrackAttr[Any], attrs[attr_id])
            for attr_id, field_name in Track.attr_fields().items()
        }
        return cls(orgs=orgs, **values)

    def attr(self, name: str) -> TrackAttr[Any] | None:
        field_name = Track.attr_field_name(name)
        if field_name is None:
            return None
        return cast(TrackAttr[Any], getattr(self, field_name))

    def clone(self) -> "TrackSchema":
        updates = {
            field_info.name: getattr(self, field_info.name).clone()
            for field_info in fields(type(self))
        }
        return replace(self, **updates)

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
                for attr in self.orgs.values():
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

    @classmethod
    def from_specs(cls, specs: ParsingSpecs) -> "MediaSchema":
        track = TrackSchema.from_specs(specs)
        attrs = {
            attr_id: Attr(attr_id)
            for attr_id in Media.attr_ids()
        }
        for attr_id, attr in attrs.items():
            attr.add_specs(specs.attr(attr_id).values)
        return cls.from_attrs(attrs, track=track)

    @classmethod
    def from_attrs(
        cls,
        attrs: Mapping[str, Attr[Any]],
        *,
        track: TrackSchema,
    ) -> "MediaSchema":
        values = {
            field_name: cast(Attr[Any], attrs[attr_id])
            for attr_id, field_name in Media.attr_fields().items()
        }
        return cls(track=track, **values)

    def attr(self, name: str) -> Attr[Any] | None:
        field_name = Media.attr_field_name(name)
        if field_name is None:
            return None
        return cast(Attr[Any], getattr(self, field_name))

    def clone(self) -> "MediaSchema":
        updates = {
            field_info.name: getattr(self, field_info.name).clone()
            for field_info in fields(type(self))
        }
        return replace(self, **updates)

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


def _collect_org_value_specs(
    marker_specs: Mapping[str, MarkerSpec],
    field_name: str,
) -> dict[str, ValueSpec]:
    collected: dict[str, ValueSpec] = {}
    for marker_spec in marker_specs.values():
        spec = marker_spec.attrs.get(field_name)
        if spec is None:
            continue

        value_spec = ValueSpec(
            score=0 if spec.score is None else spec.score,
            label=spec.label,
            msgid=spec.msgid,
            hidden=False if spec.hidden is None else spec.hidden,
        )
        existing = collected.get(spec.id)
        if existing is not None and existing != value_spec:
            raise ValueError(f"Conflicting {field_name} spec for '{spec.id}'")
        collected[spec.id] = value_spec
    return collected
