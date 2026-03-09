from streaming.filmix.models import SuggestionsResponse


def test_suggestions_response_accepts_nested_last_episode():
    payload = {
        "status": "ok",
        "items": [
            {
                "id": 1,
                "title": "Test",
                "year": 2024,
                "last_episode": {
                    "season": 1,
                    "episode": "1-37",
                    "translation": "СВ-Дубль",
                    "date": "2023-05-10T15:03:55+03:00",
                },
                "max_episode": {"season": 1, "episode": 37},
            }
        ],
    }

    result = SuggestionsResponse.model_validate(payload)

    assert len(result.items) == 1
    assert result.items[0].last_episode is not None
    assert result.items[0].last_episode.season == 1
    assert result.items[0].last_episode.episode == "1-37"
    assert result.items[0].max_episode is not None
