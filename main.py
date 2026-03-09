import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import httpx
from jinja2 import Environment, FileSystemLoader
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from metadata import METADATA_MODULES
from streaming import STREAMING_MODULES
from streaming.base import Stream, StreamingService
from streaming.parsing.catalog import default_profile
from streaming.parsing.core import Parser
from streaming.parsing.formatting import DEFAULT_LOCALE
from streaming.parsing.grouping import build_binge_group
from utils import CORS_HEADERS, decode_config, encode_config

LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING").upper()

logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(name)s: %(message)s")
_log = logging.getLogger(__name__)

PROVIDER_TIMEOUT = 10

STREAM_CACHE_MAX_AGE = 60    # /stream/
PLAY_CACHE_MAX_AGE = 60       # /play/

MANIFEST = {
    "id": "community.stremak",
    "version": "1.0.0",
    "name": "Stremak",
    "description": "Streams from multiple services",
    "catalogs": [],
    "resources": ["stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt"] # "kitsu:", "mal:"
}

templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=True,
)

def _parse_stremio_id(raw_id: str) -> tuple[str, int | None, int | None]:
    parts = raw_id.split(":")
    base_id = parts[0]
    season = int(parts[1]) if len(parts) > 1 else None
    episode = int(parts[2]) if len(parts) > 2 else None
    return base_id, season, episode
    
def _build_metadata(http: httpx.AsyncClient, config: dict) -> dict:
    return {
        p.slug: client
        for p in METADATA_MODULES
        if (client := p.from_config(http, config.get("metadata", {}))) is not None
    }


def _select_play_stream(
    streams: list[Stream],
    play_identity: dict,
    *,
    parser: Parser | None = None,
    provider_name: str,
    stremio_id: str,
) -> Stream | None:
    if not streams:
        return None

    profile = parser.profile if parser is not None else default_profile
    target = profile.media.decode_identity(play_identity)
    required_weight, scored = target.match_candidates(streams)

    if not scored:
        _log.warning(
            "No play candidates matched at weight=%s for provider=%s stremio_id=%s",
            required_weight,
            provider_name,
            stremio_id,
        )
        return None

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score = scored[0][0]
    top = [stream for score, stream in scored if score == best_score]
    if len(top) > 1 and target.has_min_identity():
        _log.warning(
            "Play selection remained ambiguous for provider=%s stremio_id=%s candidates=%s",
            provider_name,
            stremio_id,
            len(top),
        )
    return top[0]

async def manifest_handler(request: Request) -> JSONResponse:
    config = decode_config(request.path_params.get("config", ""))
    configured = config.get("streaming") and config.get("metadata")
    hints = {"configurable": True}
    if not configured:
        hints["configurationRequired"] = True
    return JSONResponse({**MANIFEST, "behaviorHints": hints}, headers=CORS_HEADERS)

async def configure_handler(request: Request) -> HTMLResponse:
    config = decode_config(request.path_params.get("config", ""))
    template = templates.get_template("templates/configure.jinja2")
    return HTMLResponse(
        template.render(
            services=STREAMING_MODULES,
            metadata=METADATA_MODULES,
            config=config,
            default_locale=DEFAULT_LOCALE,
        )
    )
    
def enrich_streams(provider_streams: dict[str, list[Stream]]) -> dict[str, list[Stream]]:
    all_tracks = [
        track
        for streams in provider_streams.values()
        for stream in streams
        for track in stream.tracks
    ]
    if not all_tracks:
        return provider_streams

    result: dict[str, list[Stream]] = {}
    for slug, streams in provider_streams.items():
        enriched: list[Stream] = []
        for stream in streams:
            new_tracks_list = []
            for t in stream.tracks:
                for ref in all_tracks:
                    if t is not ref and t.matches(ref):
                        t = t.enrich_from(ref)
                new_tracks_list.append(t)
            new_tracks = tuple(new_tracks_list)
            enriched.append(replace(stream, tracks=new_tracks) if new_tracks != stream.tracks else stream)
        result[slug] = enriched
    return result

async def stream_handler(request: Request) -> JSONResponse:
    config_str = request.path_params.get("config", "")
    config = decode_config(config_str)
    locale = str(config.get("locale") or DEFAULT_LOCALE)
    http: httpx.AsyncClient = request.app.state.http
    raw_id: str = request.path_params["stremio_id"].split(".")[0]
    base_id, season, episode = _parse_stremio_id(raw_id)
    base = str(request.base_url).rstrip("/")
    metadata = _build_metadata(http, config)

    async def _resolve(provider) -> list[Stream]:
        client = provider.from_config(http, config.get("streaming", {}))
        if not isinstance(client, StreamingService):
            return []
        return await asyncio.wait_for(
            client.resolve_streams(base_id, metadata, season=season, episode=episode),
            timeout=PROVIDER_TIMEOUT,
        )

    tasks = [_resolve(p) for p in STREAMING_MODULES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    raw: dict[str, list[Stream]] = {}
    for provider, result in zip(STREAMING_MODULES, results):
        if isinstance(result, asyncio.TimeoutError):
            _log.warning("Provider %s timed out for %s", provider.name, raw_id)
        elif isinstance(result, Exception):
            _log.exception("Provider %s failed for %s", provider.name, raw_id, exc_info=result)
        elif isinstance(result, list):
            raw[provider.slug] = result

    if not raw:
        _log.warning(
            "No streams resolved for %s (base_id=%s season=%s episode=%s)",
            raw_id,
            base_id,
            season,
            episode,
        )

    enriched = enrich_streams(raw)
    tagged: list[tuple[Stream, type, str, str]] = []
    for provider in STREAMING_MODULES:
        display_streams = enriched.get(provider.slug)
        raw_streams = raw.get(provider.slug)
        if display_streams and raw_streams:
            tagged.extend(
                (
                    display_stream,
                    provider,
                    build_binge_group(provider.slug, raw_stream),
                    encode_config(raw_stream.identity()),
                )
                for display_stream, raw_stream in zip(display_streams, raw_streams)
            )
    tagged.sort(key=lambda x: x[0].score(), reverse=True)

    all_streams: list[dict] = []
    for s, provider, group, play_identity in tagged:
        all_streams.append({
            "name": s.display_name(provider.name),
            "description": s.format(locale=locale),
            "url": f"{base}/{config_str}/play/{provider.slug}/{play_identity}/{raw_id}",
            "behaviorHints": {"bingeGroup": group},
        })

    return JSONResponse(
        {"streams": all_streams},
        headers={**CORS_HEADERS, "Cache-Control": f"max-age={STREAM_CACHE_MAX_AGE}"},
    )

async def play_handler(request: Request) -> Response:    
    config = decode_config(request.path_params["config"])
    provider_name: str = request.path_params["provider"]
    play_identity = decode_config(request.path_params["play_identity"])
    stremio_id: str = request.path_params["stremio_id"]

    provider = next((m for m in STREAMING_MODULES if m.slug == provider_name), None)
    if not provider:
        _log.warning("Unknown provider '%s' for play request %s", provider_name, stremio_id)
        return JSONResponse({"error": "Provider not found"}, status_code=404, headers=CORS_HEADERS)

    http: httpx.AsyncClient = request.app.state.http
    client = provider.from_config(http, config.get("streaming", {}))
    if not isinstance(client, StreamingService):
        _log.warning("Provider %s is not configured for play request %s", provider_name, stremio_id)
        return JSONResponse({"error": "Provider not configured"}, status_code=404, headers=CORS_HEADERS)

    base_id, season, episode = _parse_stremio_id(stremio_id)
    metadata = _build_metadata(http, config)
    streams = await asyncio.wait_for(
        client.resolve_streams(base_id, metadata, season=season, episode=episode),
        timeout=PROVIDER_TIMEOUT,
    )

    if not isinstance(play_identity, dict):
        _log.warning("Invalid play identity for provider=%s stremio_id=%s", provider_name, stremio_id)
        return JSONResponse({"error": "Invalid play identity"}, status_code=404, headers=CORS_HEADERS)

    selected = _select_play_stream(
        streams,
        play_identity,
        parser=provider.parser,
        provider_name=provider_name,
        stremio_id=stremio_id,
    )
    if selected is None:
        fresh_streams = await asyncio.wait_for(
            client.resolve_streams(base_id, metadata, season=season, episode=episode, refresh=True),
            timeout=PROVIDER_TIMEOUT,
        )
        selected = _select_play_stream(
            fresh_streams,
            play_identity,
            parser=provider.parser,
            provider_name=provider_name,
            stremio_id=stremio_id,
        )
        streams = fresh_streams

    if selected is not None:
        return RedirectResponse(
            selected.url,
            status_code=302,
            headers={**CORS_HEADERS, "Cache-Control": f"max-age={PLAY_CACHE_MAX_AGE}"},
        )

    _log.warning(
        "Play candidate not found for provider=%s stremio_id=%s candidates=%s",
        provider_name,
        stremio_id,
        len(streams),
    )
    return JSONResponse({"error": "Stream not found"}, status_code=404, headers=CORS_HEADERS)

routes = [
    Route("/", configure_handler),
    Route("/configure", configure_handler),
    Route("/{config}/configure", configure_handler),
    Route("/manifest.json", manifest_handler),
    Route("/{config}/manifest.json", manifest_handler),
    Route("/{config}/stream/{type}/{stremio_id}", stream_handler),
    Route("/{config}/play/{provider}/{play_identity}/{stremio_id}", play_handler),
]

for module in STREAMING_MODULES:
    routes.extend(module.get_routes())
for module in METADATA_MODULES:
    routes.extend(module.get_routes())

@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as http:
        app.state.http = http
        yield

app = Starlette(routes=routes, lifespan=lifespan)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")), access_log=False)
