from languages import LangCode
from main import enrich_streams
from streaming.base import Stream
from streaming.parsing.catalog import Lang, VoiceType
from streaming.parsing.core import Org, OrgKind, OrgList, Track, TrackAttrVal


def _track(*, studio: str | None = None, voice_type: TrackAttrVal | None = None, lang: LangCode = "ru") -> Track:
    return Track(
        lang=Lang.get(lang),
        orgs=OrgList((Org(id=studio, label=studio, kind=OrgKind.STUDIO),)) if studio else OrgList(),
        voice_type=voice_type,
    )


def _stream(*tracks: Track, url: str = "http://test") -> Stream:
    return Stream(url=url, tracks=tuple(tracks))


def test_enrich_fills_missing_voice_type():
    result = enrich_streams({
        "filmix": [_stream(_track(studio="RHS"))],
        "kinopub": [_stream(_track(studio="RHS", voice_type=VoiceType["DUB"]))],
    })
    assert result["filmix"][0].tracks[0].voice_type == VoiceType["DUB"]
    assert result["kinopub"][0].tracks[0].voice_type == VoiceType["DUB"]


def test_enrich_does_not_overwrite_existing():
    result = enrich_streams({
        "filmix": [_stream(_track(studio="LostFilm", voice_type=VoiceType["MVO"]))],
        "kinopub": [_stream(_track(studio="LostFilm", voice_type=VoiceType["DUB"]))],
    })
    assert result["filmix"][0].tracks[0].voice_type == VoiceType["MVO"]


def test_enrich_no_studio_untouched():
    result = enrich_streams({
        "filmix": [_stream(_track())],
        "kinopub": [_stream(_track(studio="RHS", voice_type=VoiceType["DUB"]))],
    })
    assert result["filmix"][0].tracks[0].voice_type is None


def test_enrich_no_voice_data_noop():
    result = enrich_streams({
        "filmix": [_stream(_track(studio="RHS"))],
        "kinopub": [_stream(_track(studio="HDrezka"))],
    })
    assert result["filmix"][0].tracks[0].voice_type is None
    assert result["kinopub"][0].tracks[0].voice_type is None


def test_enrich_fuzzy_studio_match():
    result = enrich_streams({
        "filmix": [_stream(_track(studio="Red Head Sound"))],
        "kinopub": [_stream(_track(studio="RHS Red Head Sound", voice_type=VoiceType["DUB"]))],
    })
    assert result["filmix"][0].tracks[0].voice_type == VoiceType["DUB"]
