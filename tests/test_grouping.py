from dataclasses import replace

from streaming.base import Stream
from main import slugify
from streaming.parsing.catalog import default_profile
from streaming.parsing.core import Org, OrgList, Track

LANG = default_profile.track.lang
STUDIO = default_profile.track.orgs["studio"]
VOICE_TYPE = default_profile.track.voice_type


def _stream(track: Track, *, url: str = "http://test") -> Stream:
    return Stream(url=url, tracks=(track,))


def _group(source: str, stream: Stream) -> str:
    return slugify("-".join((source, *stream.group_tokens())))


def test_binge_group_uses_index_when_track_identity_is_weak():
    stream = _stream(Track(lang=LANG["ru"], index=2))

    group = _group("kinopub", stream)

    assert group == "kinopub-ru-2"


def test_binge_group_stays_stable_when_enrichment_adds_soft_attrs():
    raw = _stream(Track(lang=LANG["ru"], orgs=OrgList((Org.from_value(STUDIO["LostFilm"], kind="studio"),))))
    enriched = _stream(replace(raw.tracks[0], voice_type=VOICE_TYPE["MVO"]))

    assert _group("filmix", raw) == _group("filmix", enriched)
