import re
from typing import cast

import httpx

from starlette.testclient import TestClient

from config import AppConfig
from main import _build_streaming, app, encode_config
from streaming.base import Stream
from streaming.parsing.catalog import get_profile
from streaming.parsing.core import Track
from streaming.parsing.specs import DEFAULT_PARSING_SPECS


def _test_http() -> httpx.AsyncClient:
    return cast(httpx.AsyncClient, object())


def _config_with_lang_scores(scores: dict[str, int]) -> AppConfig:
    return AppConfig.model_validate({
        "parsing": {
            "specs": {
                "attrs": {
                    "lang": {
                        "values": {
                            lang: {"score": score}
                            for lang, score in scores.items()
                        },
                    },
                },
            },
        },
        "streaming": {"filmix": {"token": "test"}},
        "metadata": {"tmdb": {"api_key": "test"}},
    })


def test_stream_rejects_missing_required_runtime_config():
    config = encode_config({"streaming": {}, "metadata": {}})

    with TestClient(app) as client:
        response = client.get(f"/{config}/stream/movie/tt0944947")

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid config"}


def test_play_rejects_missing_required_runtime_config():
    config = encode_config({"streaming": {}, "metadata": {}})
    play_identity = encode_config({"tracks": []})

    with TestClient(app) as client:
        response = client.get(f"/{config}/play/filmix/{play_identity}/tt0944947")

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid config"}


def test_stream_requires_configured_services_and_metadata():
    config = encode_config({"streaming": {}, "metadata": {}})

    with TestClient(app) as client:
        response = client.get(f"/{config}/stream/movie/tt0944947")

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid config"}


def test_play_requires_configured_services_and_metadata():
    config = encode_config({"streaming": {}, "metadata": {}})
    play_identity = encode_config({"tracks": []})

    with TestClient(app) as client:
        response = client.get(f"/{config}/play/filmix/{play_identity}/tt0944947")

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid config"}


def test_stream_rejects_empty_nested_service_config():
    config = encode_config({
        "streaming": {"filmix": {}},
        "metadata": {"tmdb": {"api_key": "test"}},
    })

    with TestClient(app) as client:
        response = client.get(f"/{config}/stream/movie/tt0944947")

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid config"}


def test_stream_rejects_invalid_parsing_specs():
    config = encode_config({
        "parsing": {
            "specs": {
                "markers": {
                    "track": {
                        "bad_lang": {
                            "pattern": r"\bBAD\b",
                            "attrs": {"lang": {"id": "zz"}},
                        },
                    },
                },
            },
        },
        "streaming": {"filmix": {"token": "test"}},
        "metadata": {"tmdb": {"api_key": "test"}},
    })

    with TestClient(app) as client:
        response = client.get(f"/{config}/stream/movie/tt0944947")

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid config"}


def test_app_config_uses_default_parsing_specs_when_omitted():
    config = AppConfig.model_validate({
        "streaming": {"filmix": {"token": "test"}},
        "metadata": {"tmdb": {"api_key": "test"}},
    })

    assert config.parsing.effective_specs().attr("lang").default_scores == DEFAULT_PARSING_SPECS.attr("lang").default_scores


def test_app_config_accepts_lang_score_override_in_specs():
    config = AppConfig.model_validate({
        "parsing": {"specs": {"attrs": {"lang": {"values": {"ru": {"score": 3500}}}}}},
        "streaming": {"filmix": {"token": "test"}},
        "metadata": {"tmdb": {"api_key": "test"}},
    })

    assert config.parsing.effective_specs().attr("lang")["ru"].score == 3500


def test_app_config_accepts_new_values_in_specs():
    config = AppConfig.model_validate({
        "parsing": {
            "specs": {
                "attrs": {
                    "audio_format": {
                        "values": {"PCM": {"score": 42, "label": "PCM"}},
                    },
                },
            },
        },
        "streaming": {"filmix": {"token": "test"}},
        "metadata": {"tmdb": {"api_key": "test"}},
    })

    assert config.parsing.effective_specs().attr("audio_format")["PCM"].score == 42


def test_build_streaming_uses_configured_parsing_profile():
    config = AppConfig.model_validate({
        "parsing": {
            "specs": {
                "markers": {
                    "track": {
                        "custom_xru": {
                            "pattern": r"\bXRU\b",
                            "attrs": {"lang": {"id": "ru", "anchored": True}},
                        },
                    },
                },
            },
        },
        "streaming": {"kinopub": {"token": "test"}},
        "metadata": {"tmdb": {"api_key": "test"}},
    })

    clients = _build_streaming(_test_http(), config)

    track = clients["kinopub"].parser.parse_track("XRU")
    assert track.lang and track.lang.id == "ru"


def test_build_streaming_uses_provider_default_parsing_specs():
    config = AppConfig.model_validate({
        "streaming": {"filmix": {"token": "test"}},
        "metadata": {"tmdb": {"api_key": "test"}},
    })

    clients = _build_streaming(_test_http(), config)

    track = clients["filmix"].parser.parse_track("+UA")
    assert track.lang and track.lang.id == "uk"
    assert track.voice_type and track.voice_type.id == "DUB"


def test_configure_applies_parsing_specs_without_runtime_placeholders():
    config = encode_config({
        "parsing": {
            "specs": {
                "attrs": {
                    "lang": {
                        "values": {
                            "ru": {"score": 3500},
                        },
                    },
                },
            },
        },
    })

    with TestClient(app) as client:
        response = client.get(f"/{config}/configure")

    assert response.status_code == 200
    assert re.search(r'"default_scores"\s*:\s*\{[^}]*"ru"\s*:\s*3500', response.text)


def test_stream_score_uses_configured_language_scores():
    profile = get_profile(_config_with_lang_scores({"uk": 3000, "ru": 2000, "en": 1000}).parsing.effective_specs())
    uk_stream = Stream(
        url="http://uk",
        tracks=(Track(lang=profile.track.lang["uk"], voice_type=profile.track.voice_type["DUB"]),),
    )
    ru_stream = Stream(
        url="http://ru",
        tracks=(Track(lang=profile.track.lang["ru"], voice_type=profile.track.voice_type["DUB"]),),
    )

    assert uk_stream.score() > ru_stream.score()


def test_quality_still_beats_language_scores():
    profile = get_profile(_config_with_lang_scores({"uk": 3000, "ru": 2000, "en": 1000}).parsing.effective_specs())
    preferred_lang_stream = Stream(
        url="http://uk-1080p",
        tracks=(Track(lang=profile.track.lang["uk"], voice_type=profile.track.voice_type["DUB"]),),
        quality=profile.media.quality["1080p"],
    )
    better_quality_stream = Stream(
        url="http://ru-4k",
        tracks=(Track(lang=profile.track.lang["ru"], voice_type=profile.track.voice_type["DUB"]),),
        quality=profile.media.quality["4K"],
    )

    assert better_quality_stream.score() > preferred_lang_stream.score()


def test_hdr_still_beats_language_scores():
    profile = get_profile(_config_with_lang_scores({"uk": 3000, "ru": 2000, "en": 1000}).parsing.effective_specs())
    preferred_lang_stream = Stream(
        url="http://uk-sdr",
        tracks=(Track(lang=profile.track.lang["uk"], voice_type=profile.track.voice_type["DUB"]),),
    )
    better_hdr_stream = Stream(
        url="http://ru-hdr",
        tracks=(Track(lang=profile.track.lang["ru"], voice_type=profile.track.voice_type["DUB"]),),
        hdr=profile.media.hdr["DV"],
    )

    assert better_hdr_stream.score() > preferred_lang_stream.score()
