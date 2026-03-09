import logging

from main import _select_play_stream
from streaming.base import Stream
from streaming.parsing.catalog import Codec, Lang, Quality, Studio, VoiceType
from streaming.parsing.core import Org, OrgList, Track
from utils import decode_config, encode_config


def make_stream(
    track: Track,
    *,
    url: str,
    quality: str | None = None,
    codec: str | None = None,
) -> Stream:
    return Stream(
        url=url,
        tracks=(track,),
        quality=Quality[quality] if quality else None,
        codec=Codec[codec] if codec else None,
    )


def make_lostfilm_track() -> Track:
    return Track(
        lang=Lang["ru"],
        orgs=OrgList((Org.from_value(Studio["LostFilm"], kind="studio"),)),
        voice_type=VoiceType["MVO"],
    )


def test_play_selection_survives_stream_reordering():
    requested_stream = make_stream(
        make_lostfilm_track(),
        url="http://old/1080",
        quality="1080p",
        codec="HEVC",
    )
    play_identity = decode_config(encode_config(requested_stream.identity()))

    fresh_streams = [
        make_stream(
            make_lostfilm_track(),
            url="http://new/1080",
            quality="1080p",
            codec="HEVC",
        ),
        make_stream(
            make_lostfilm_track(),
            url="http://new/720",
            quality="720p",
            codec="H264",
        ),
    ]

    selected = _select_play_stream(
        fresh_streams,
        play_identity,
        provider_name="filmix",
        stremio_id="tt0944947:1:6",
    )

    assert selected is not None
    assert selected.quality and selected.quality.id == "1080p"
    assert selected.codec and selected.codec.id == "HEVC"


def test_play_selection_uses_media_fields_to_break_ties_without_warning(caplog):
    requested_stream = make_stream(
        make_lostfilm_track(),
        url="http://old/hevc",
        quality="1080p",
        codec="HEVC",
    )
    play_identity = decode_config(encode_config(requested_stream.identity()))

    fresh_streams = [
        make_stream(
            make_lostfilm_track(),
            url="http://new/h264",
            quality="1080p",
            codec="H264",
        ),
        make_stream(
            make_lostfilm_track(),
            url="http://new/hevc",
            quality="1080p",
            codec="HEVC",
        ),
    ]

    with caplog.at_level(logging.WARNING):
        selected = _select_play_stream(
            fresh_streams,
            play_identity,
            provider_name="filmix",
            stremio_id="tt0944947:1:6",
        )

    assert selected is not None
    assert selected.codec and selected.codec.id == "HEVC"
    assert not any("Play selection remained ambiguous" in record.message for record in caplog.records)


def test_play_selection_logs_only_when_strong_candidates_remain_ambiguous(caplog):
    requested_stream = make_stream(
        make_lostfilm_track(),
        url="http://old/hevc",
        quality="1080p",
        codec="HEVC",
    )
    play_identity = decode_config(encode_config(requested_stream.identity()))

    fresh_streams = [
        make_stream(
            make_lostfilm_track(),
            url="http://new/hevc-a",
            quality="1080p",
            codec="HEVC",
        ),
        make_stream(
            make_lostfilm_track(),
            url="http://new/hevc-b",
            quality="1080p",
            codec="HEVC",
        ),
    ]

    with caplog.at_level(logging.WARNING):
        selected = _select_play_stream(
            fresh_streams,
            play_identity,
            provider_name="filmix",
            stremio_id="tt0944947:1:6",
        )

    assert selected is not None
    assert any("Play selection remained ambiguous" in record.message for record in caplog.records)
