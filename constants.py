import os

LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING").upper()

PROVIDER_TIMEOUT = 10

STREAM_CACHE_MAX_AGE = 60
PLAY_CACHE_MAX_AGE = 60

MANIFEST = {
    "id": "community.stremak",
    "version": "1.0.0a",
    "name": "Stremak",
    "description": "Streams from multiple services",
    "catalogs": [],
    "resources": ["stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt"],
}
