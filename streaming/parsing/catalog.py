import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import replace
from typing import Any, cast

from .core import Parser, ParserProfile, ParserRules
from .models import Media, MediaMarker, Track, TrackMarker
from .registry import Marker
from .schema import MediaSchema, TrackSchema
from .specs import DEFAULT_PARSING_SPECS, MarkerSpec, MarkerValueSpec, ParsingSpecs
from .values import AttrVal, TrackAttrVal


def _resolve_track_marker_value(
    field_name: str,
    value_spec: MarkerValueSpec,
    *,
    track: TrackSchema,
) -> TrackAttrVal[Any]:
    attr = track.orgs.attr(field_name) or track.attr(field_name)
    if attr is None:
        raise KeyError(field_name)
    value = cast(TrackAttrVal[Any], attr[value_spec.id])

    updates: dict[str, Any] = {}
    for key in ("score", "label", "msgid", "hidden", "confidence", "anchored"):
        if (new_value := getattr(value_spec, key)) is not None:
            updates[key] = new_value

    return replace(value, **updates) if updates else value


def _resolve_media_marker_value(
    field_name: str,
    value_spec: MarkerValueSpec,
    *,
    media: MediaSchema,
) -> AttrVal[Any]:
    attr = media.attr(field_name)
    if attr is None:
        raise KeyError(field_name)
    value = cast(AttrVal[Any], attr[value_spec.id])

    updates: dict[str, Any] = {}
    for key in ("score", "label", "msgid", "hidden"):
        if (new_value := getattr(value_spec, key)) is not None:
            updates[key] = new_value

    return replace(value, **updates) if updates else value


def _build_track_markers(
    marker_specs: Iterable[MarkerSpec],
    *,
    track: TrackSchema,
) -> tuple[TrackMarker, ...]:
    return tuple(
        Marker(
            marker_spec.pattern,
            blocked=marker_spec.blocked,
            **{
                field_name: _resolve_track_marker_value(
                    field_name,
                    value_spec,
                    track=track,
                )
                for field_name, value_spec in marker_spec.attrs.items()
            },
        )
        for marker_spec in marker_specs
    )


def _build_media_markers(
    marker_specs: Iterable[MarkerSpec],
    *,
    media: MediaSchema,
) -> tuple[MediaMarker, ...]:
    return tuple(
        Marker(
            marker_spec.pattern,
            blocked=marker_spec.blocked,
            **{
                field_name: _resolve_media_marker_value(field_name, value_spec, media=media)
                for field_name, value_spec in marker_spec.attrs.items()
            },
        )
        for marker_spec in marker_specs
    )


def compile_profile(specs: ParsingSpecs) -> ParserProfile:
    ignored_patterns = tuple(re.compile(pattern, re.I) for pattern in specs.ignored_patterns)
    media = MediaSchema.from_specs(specs)
    compiled_track_markers = _build_track_markers(specs.markers_for(Track).values(), track=media.track)
    compiled_media_markers = _build_media_markers(specs.markers_for(Media).values(), media=media)

    return ParserProfile(
        media=media,
        rules=ParserRules(
            track_markers=compiled_track_markers,
            media_markers=compiled_media_markers,
            ignored_patterns=ignored_patterns,
        ),
    )


def _specs_cache_key(specs: ParsingSpecs) -> str:
    raw = json.dumps(
        specs.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(raw.encode("ascii")).hexdigest()


_PROFILE_CACHE: dict[str, ParserProfile] = {}
_PARSER_CACHE: dict[str, Parser] = {}


def get_profile(specs: ParsingSpecs = DEFAULT_PARSING_SPECS) -> ParserProfile:
    cache_key = _specs_cache_key(specs)
    profile = _PROFILE_CACHE.get(cache_key)
    if profile is None:
        profile = compile_profile(specs)
        _PROFILE_CACHE[cache_key] = profile
    return profile


def get_parser(specs: ParsingSpecs = DEFAULT_PARSING_SPECS) -> Parser:
    cache_key = _specs_cache_key(specs)
    parser = _PARSER_CACHE.get(cache_key)
    if parser is None:
        parser = get_profile(specs).build_parser()
        _PARSER_CACHE[cache_key] = parser
    return parser


default_profile = get_profile()
