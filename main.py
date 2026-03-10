import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import httpx
from jinja2 import Environment, FileSystemLoader
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from config import AppConfig, ParsingConfig
from constants import (
    LOG_LEVEL,
    MANIFEST,
    PLAY_CACHE_MAX_AGE,
    PROVIDER_TIMEOUT,
    STREAM_CACHE_MAX_AGE,
)
from metadata.base import MetadataClient
from metadata.tmdb import TheMovieDB
from streaming.base import Stream, StreamingService, select_stream_by_identity
from streaming.filmix import Filmix
from streaming.kinopub import KinoPub
from streaming.parsing import Parser
from streaming.parsing.specs import DEFAULT_PARSING_SPECS
from utils import CORS_HEADERS, decode_config, encode_config, slugify

logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(name)s: %(message)s")
_log = logging.getLogger(__name__)

STREAMING_PROVIDERS = (Filmix, KinoPub)
METADATA_PROVIDERS = (TheMovieDB,)

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


def _build_metadata(http: httpx.AsyncClient, config: AppConfig) -> dict[str, MetadataClient]:
    clients: dict[str, MetadataClient] = {}
    if config.metadata.tmdb is not None and (client := TheMovieDB.from_settings(http, config.metadata.tmdb)) is not None:
        clients[TheMovieDB.slug] = client
    return clients


def _build_streaming(http: httpx.AsyncClient, config: AppConfig) -> dict[str, StreamingService]:
    clients: dict[str, StreamingService] = {}
    if config.streaming.filmix is not None and (
        client := Filmix.from_settings(http, config.streaming.filmix, parsing_specs=config.parsing.specs)
    ) is not None:
        clients[Filmix.slug] = client
    if config.streaming.kinopub is not None and (
        client := KinoPub.from_settings(http, config.streaming.kinopub, parsing_specs=config.parsing.specs)
    ) is not None:
        clients[KinoPub.slug] = client
    return clients

def _select_play_stream(streams: list[Stream], play_identity: dict, *, parser: Parser, provider_name: str, stremio_id: str) -> Stream | None:
    selected, required_weight, top_count, strong_identity = select_stream_by_identity(
        streams,
        play_identity,
        parser=parser,
    )
    if selected is None:
        _log.warning(
            "No play candidates matched at weight=%s for provider=%s stremio_id=%s",
            required_weight,
            provider_name,
            stremio_id,
        )
        return None
    if top_count > 1 and strong_identity:
        _log.warning(
            "Play selection remained ambiguous for provider=%s stremio_id=%s candidates=%s",
            provider_name,
            stremio_id,
            top_count,
        )
    return selected

async def manifest_handler(request: Request) -> JSONResponse:
    try:
        config = AppConfig.model_validate(decode_config(request.path_params.get("config", "")))
    except ValidationError:
        config = None
    configured = config is not None
    hints = {"configurable": True}
    if not configured:
        hints["configurationRequired"] = True
    return JSONResponse({**MANIFEST, "behaviorHints": hints}, headers=CORS_HEADERS)

async def configure_handler(request: Request) -> HTMLResponse:
    config = decode_config(request.path_params.get("config", ""))
    parsing_specs = DEFAULT_PARSING_SPECS
    if isinstance(config, dict):
        try:
            parsing_specs = ParsingConfig.model_validate(config.get("parsing")).effective_specs()
        except ValidationError:
            pass
    template = templates.get_template("templates/configure.jinja2")
    return HTMLResponse(
        template.render(
            services=STREAMING_PROVIDERS,
            metadata=METADATA_PROVIDERS,
            config=config,
            parsing_specs=parsing_specs.model_dump(mode="json"),
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
    try:
        config = AppConfig.model_validate(decode_config(config_str))
    except ValidationError:
        config = None
    http: httpx.AsyncClient = request.app.state.http
    if config is None:
        return JSONResponse({"error": "Invalid config"}, status_code=400, headers=CORS_HEADERS)
    streaming_clients = _build_streaming(http, config)
    metadata = _build_metadata(http, config)
    raw_id: str = request.path_params["stremio_id"].split(".")[0]
    base_id, season, episode = _parse_stremio_id(raw_id)
    base = str(request.base_url).rstrip("/")

    async def _resolve(provider, client: StreamingService) -> list[Stream]:
        return await asyncio.wait_for(
            client.resolve_streams(base_id, metadata, season=season, episode=episode),
            timeout=PROVIDER_TIMEOUT,
        )

    tasks = [_resolve(p, streaming_clients[p.slug]) for p in STREAMING_PROVIDERS if p.slug in streaming_clients]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    raw: dict[str, list[Stream]] = {}
    active_providers = [p for p in STREAMING_PROVIDERS if p.slug in streaming_clients]
    for provider, result in zip(active_providers, results):
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
    for provider in STREAMING_PROVIDERS:
        display_streams = enriched.get(provider.slug)
        raw_streams = raw.get(provider.slug)
        if display_streams and raw_streams:
            tagged.extend(
                (
                    display_stream,
                    provider,
                    slugify("-".join((provider.slug, *raw_stream.group_tokens()))),
                    encode_config(raw_stream.identity()),
                )
                for display_stream, raw_stream in zip(display_streams, raw_streams)
            )
    tagged.sort(
        key=lambda x: x[0].score(),
        reverse=True,
    )

    all_streams: list[dict] = []
    for s, provider, group, play_identity in tagged:
        all_streams.append({
            "name": s.display_name(provider.name),
            "description": s.format(specs=streaming_clients[provider.slug].specs),
            "url": f"{base}/{config_str}/play/{provider.slug}/{play_identity}/{raw_id}",
            "behaviorHints": {"bingeGroup": group},
        })

    return JSONResponse(
        {"streams": all_streams},
        headers={**CORS_HEADERS, "Cache-Control": f"max-age={STREAM_CACHE_MAX_AGE}"},
    )

async def play_handler(request: Request) -> Response:    
    try:
        config = AppConfig.model_validate(decode_config(request.path_params["config"]))
    except ValidationError:
        config = None
    http: httpx.AsyncClient = request.app.state.http
    if config is None:
        return JSONResponse({"error": "Invalid config"}, status_code=400, headers=CORS_HEADERS)

    streaming_clients = _build_streaming(http, config)
    metadata = _build_metadata(http, config)
    provider_name: str = request.path_params["provider"]
    play_identity = decode_config(request.path_params["play_identity"])
    stremio_id: str = request.path_params["stremio_id"]

    provider = next((m for m in STREAMING_PROVIDERS if m.slug == provider_name), None)
    if not provider:
        _log.warning("Unknown provider '%s' for play request %s", provider_name, stremio_id)
        return JSONResponse({"error": "Provider not found"}, status_code=404, headers=CORS_HEADERS)

    client = streaming_clients.get(provider_name)
    if client is None:
        _log.warning("Provider %s is not configured for play request %s", provider_name, stremio_id)
        return JSONResponse({"error": "Provider not configured"}, status_code=404, headers=CORS_HEADERS)

    base_id, season, episode = _parse_stremio_id(stremio_id)
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
        parser=client.parser,
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
            parser=client.parser,
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

for module in STREAMING_PROVIDERS:
    routes.extend(module.get_routes())
for module in METADATA_PROVIDERS:
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
