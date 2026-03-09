import httpx
import pytest

from streaming.filmix.core import FilmixPrivate


def _response(items):
    return {
        "status": "ok",
        "items": items,
    }


@pytest.mark.anyio
async def test_search_treats_nested_last_episode_as_series_when_season_requested():
    payload = _response(
        [
            {
                "id": 1,
                "title": "Movie",
                "year": 2024,
            },
            {
                "id": 2,
                "title": "Series",
                "year": 2024,
                "last_episode": {
                    "season": 1,
                    "episode": "1-37",
                    "translation": "СВ-Дубль",
                    "date": "2023-05-10T15:03:55+03:00",
                },
                "max_episode": {"season": 1, "episode": 37},
            },
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/list")
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        service = FilmixPrivate(http=http, token="test-token")
        results = await service.search("Series", season=1, refresh=True)

    assert [item.id for item in results] == [2]


@pytest.mark.anyio
async def test_search_filters_series_items_out_of_movie_results():
    payload = _response(
        [
            {
                "id": 1,
                "title": "Movie",
                "year": 2024,
            },
            {
                "id": 2,
                "title": "Series",
                "year": 2024,
                "last_episode": {
                    "season": 1,
                    "episode": "1-37",
                    "translation": "СВ-Дубль",
                    "date": "2023-05-10T15:03:55+03:00",
                },
            },
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/list")
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        service = FilmixPrivate(http=http, token="test-token")
        results = await service.search("Movie", refresh=True)

    assert [item.id for item in results] == [1]
