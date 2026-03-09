from starlette.testclient import TestClient

from main import app, encode_config


def test_stream_requires_locale_in_config():
    config = encode_config({"streaming": {}, "metadata": {}})

    with TestClient(app) as client:
        response = client.get(f"/{config}/stream/movie/tt0944947")

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid config"}


def test_play_requires_locale_in_config():
    config = encode_config({"streaming": {}, "metadata": {}})
    play_identity = encode_config({"tracks": []})

    with TestClient(app) as client:
        response = client.get(f"/{config}/play/filmix/{play_identity}/tt0944947")

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid config"}


def test_stream_requires_configured_services_and_metadata():
    config = encode_config({"locale": "ru", "streaming": {}, "metadata": {}})

    with TestClient(app) as client:
        response = client.get(f"/{config}/stream/movie/tt0944947")

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid config"}


def test_play_requires_configured_services_and_metadata():
    config = encode_config({"locale": "ru", "streaming": {}, "metadata": {}})
    play_identity = encode_config({"tracks": []})

    with TestClient(app) as client:
        response = client.get(f"/{config}/play/filmix/{play_identity}/tt0944947")

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid config"}


def test_stream_rejects_empty_nested_service_config():
    config = encode_config({
        "locale": "ru",
        "streaming": {"filmix": {}},
        "metadata": {"tmdb": {"api_key": "test"}},
    })

    with TestClient(app) as client:
        response = client.get(f"/{config}/stream/movie/tt0944947")

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid config"}
