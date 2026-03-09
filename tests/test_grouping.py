from dataclasses import replace

from streaming.base import Stream
from main import build_binge_group
from streaming.parsing.catalog import Lang, Studio, VoiceType
from streaming.parsing.core import Org, OrgList, Track


def _stream(track: Track, *, url: str = "http://test") -> Stream:
    return Stream(url=url, tracks=(track,))


def test_binge_group_uses_index_when_track_identity_is_weak():
    stream = _stream(Track(lang=Lang["ru"], index=2))

    group = build_binge_group("kinopub", stream)

    assert group == "kinopub-ru-2"


def test_binge_group_stays_stable_when_enrichment_adds_soft_attrs():
    raw = _stream(Track(lang=Lang["ru"], orgs=OrgList((Org.from_value(Studio["LostFilm"], kind="studio"),))))
    enriched = _stream(replace(raw.tracks[0], voice_type=VoiceType["MVO"]))

    assert build_binge_group("filmix", raw) == build_binge_group("filmix", enriched)
