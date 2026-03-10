import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import ClassVar, Sequence

import httpx
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from languages import LangCode
from metadata.base import MetadataClient
from streaming.base import Stream, best_match, is_readable
from streaming.parsing.catalog import get_parser
from streaming.parsing.core import AttrVal, Parser, Track
from streaming.parsing.specs import DEFAULT_PARSING_SPECS, ParsingSpecs
from utils import CORS_HEADERS, cached, truncate_query

from .models import (
    MoviesList,
    SearchItem,
    SeriesPlaylist,
    ServerList,
    SuggestionsResponse,
    TokenResponse,
    UserInfo,
    VideoFile,
)

_log = logging.getLogger(__name__)


class FilmixSettings(BaseModel):
    token: str | None = None

    def is_configured(self) -> bool:
        return bool(self.token)

@dataclass
class Filmix:
    slug: ClassVar[str] = "filmix"
    template: ClassVar[str]  = "streaming/filmix/template.html"
    name: ClassVar[str] = "Filmix"
    parsing_patch: ClassVar[dict[str, object]] = {
        "markers": {
            "track": {
                "filmix_ua_dub": {
                    "pattern": r"\+UA\b",
                    "blocked": ("studio",),
                    "attrs": {
                        "lang": {"id": "uk", "anchored": True},
                        "voice_type": {"id": "DUB", "anchored": True},
                    },
                },
            },
        },
    }
    _BASE_URL: ClassVar[str] = "https://filmix.dev/api/v7"
    _BASE_PARAMS: ClassVar[dict[str, str]] = {
        "user_dev_apk": "1.0.4.27",
        "user_dev_name": "AppleTV14,1",
        "user_dev_os": "tvOS",
        "user_dev_os_version": "26.1",
        "user_dev_token": "",
        "user_dev_vendor": "Apple",
    }

    http: httpx.AsyncClient

    @classmethod
    def build_specs(cls, parsing_specs: Mapping[str, object] | None = None) -> ParsingSpecs:
        return DEFAULT_PARSING_SPECS.overlay(cls.parsing_patch).overlay(parsing_specs)

    @classmethod
    def build_parser(cls, parsing_specs: Mapping[str, object] | None = None) -> Parser:
        return get_parser(cls.build_specs(parsing_specs))

    @classmethod
    def from_settings(
        cls,
        http: httpx.AsyncClient,
        settings: FilmixSettings | None,
        *,
        parsing_specs: Mapping[str, object] | None = None,
    ) -> 'FilmixPrivate | None':
        if settings and settings.token:
            client = FilmixPrivate(http=http, token=settings.token)
            specs = cls.build_specs(parsing_specs)
            if specs != client.specs:
                client.specs = specs
                client.parser = get_parser(specs)
            return client
        return None

    @classmethod
    def get_routes(cls) -> Sequence[Route]:
        return [
            Route("/api/auth/filmix/start", cls._auth_start, methods=["GET"]),
            Route("/api/auth/filmix/check", cls._auth_check, methods=["GET"]),
        ]

    @classmethod
    async def _auth_start(cls, request: Request) -> JSONResponse:
        service = Filmix(http=request.app.state.http)
        response = await service.request_device_code()
        return JSONResponse({"user_code": response.code, "device_token": response.token}, headers=CORS_HEADERS)

    @classmethod
    async def _auth_check(cls, request: Request) -> JSONResponse:
        token = request.query_params.get("token", "")
        if not token:
            return JSONResponse({"error": "Token required"}, status_code=400, headers=CORS_HEADERS)
        service = FilmixPrivate(http=request.app.state.http, token=token)
        user_info = await service.get_user_info()

        if not user_info:
            return JSONResponse({"error": "Not authenticated"}, status_code=401, headers=CORS_HEADERS)
        return JSONResponse(user_info.model_dump(mode="json"), headers=CORS_HEADERS)

    def _params(self, **params: str) -> dict[str, str]:
        return {**self._BASE_PARAMS, **params}

    @cached(3600)
    async def get_server_list(self) -> dict[str, str]:
        resp = await self.http.get(f"{self._BASE_URL}/vs-list", params=self._params())
        resp.raise_for_status()
        return ServerList.validate_json(resp.text)

    async def get_server_name(self, tag: str) -> str | None:
        servers = await self.get_server_list()
        return servers.get(tag)

    async def request_device_code(self) -> TokenResponse:
        resp = await self.http.get(f"{self._BASE_URL}/request-token", params=self._params())
        resp.raise_for_status()
        return TokenResponse.model_validate_json(resp.text)

_PART_RE = re.compile(r'\b(?:сер[ияию]\w*|part)\s*(\d+)', re.I)

@dataclass
class FilmixPrivate(Filmix):
    language: ClassVar[LangCode] = 'ru'
    specs: ParsingSpecs = field(default_factory=Filmix.build_specs, init=False)
    parser: Parser = field(default_factory=Filmix.build_parser, init=False)
    token: str = field(repr=False, kw_only=True)

    def cache_scope_key(self) -> tuple[str, str]:
        return (self.slug, self.token)

    def _params(self, **params: str) -> dict[str, str]:
        return {**self._BASE_PARAMS, "user_dev_token": self.token, **params}

    async def get_user_info(self) -> UserInfo | None:
        resp = await self.http.get(f"{self._BASE_URL}/me", params=self._params())
        if resp.status_code == 401:
            return None
        resp.raise_for_status()
        return UserInfo.model_validate_json(resp.text)

    @cached(300, empty_ttl=60)
    async def search(
        self,
        title: str,
        year: int | None = None,
        *,
        season: int | None = None,
        episode: int | None = None,
        refresh: bool = False,
    ) -> Sequence[SearchItem]:
        # NOTE There is also /suggestions endpoint but it returns strictly 4 categories and RARELY something might not have a category so need to use /list endpoint that returns everything
        resp = await self.http.get(f"{self._BASE_URL}/list", params=self._params(search=truncate_query(title)))
        resp.raise_for_status()
        data = SuggestionsResponse.model_validate_json(resp.text)

        if season is not None:
            series_items = [
                item for item in data.items
                if item.last_episode is not None
            ]
            return series_items or data.items

        movie_items = [
            item for item in data.items
            if item.last_episode is None
        ]
        return movie_items or data.items

    @staticmethod
    def _strip_numbers(title: str) -> str | None:
        stripped = re.sub(r'\b\d+\b', '', title).strip()
        stripped = ' '.join(stripped.split())
        if not stripped or stripped == title:
            return None
        return stripped

    @staticmethod
    def _parse_voiceover(
        label: str,
        *,
        original_lang: LangCode,
        parser: Parser | None = None,
        language: LangCode = "ru",
    ):
        active_parser = Filmix.build_parser() if parser is None else parser
        result = active_parser.parse_label(label)
        track_schema = active_parser.profile.track

        tracks: list[Track] = []
        for track in result.tracks:
            if track.lang is None:
                if track.voice_type == track_schema.voice_type["OG"]:
                    track = track.with_language(original_lang, lang_attr=track_schema.lang)
                else:
                    track = track.with_language(language, lang_attr=track_schema.lang)
            tracks.append(track)

        return replace(result, tracks=tuple(tracks))

    async def _find(
        self,
        title: str,
        year: int,
        *,
        season: int | None = None,
        episode: int | None = None,
        refresh: bool = False,
    ) -> SearchItem | None:
        if not refresh:
            for results in self.search.store.all_valid():
                if found := best_match(results, title, year):
                    return found
        results = await self.search(title, year, season=season, episode=episode, refresh=refresh)
        if found := best_match(results, title, year):
            return found

        stripped = self._strip_numbers(title)
        if stripped:
            results = await self.search(stripped, year, season=season, episode=episode, refresh=refresh)
            return best_match(results, title, year)
        return None

    @cached(3600, scope="account", empty_ttl=60)
    async def _fetch_movie_streams(
        self,
        item_id: str | int,
        *,
        original_lang: LangCode,
        refresh: bool = False,
    ) -> list[Stream]:
        resp = await self.http.get(f"{self._BASE_URL}/post/{item_id}/videos-movies", params=self._params())
        resp.raise_for_status()
        videos = MoviesList.validate_json(resp.text)
        streams = [s for v in videos for s in self._build_streams(v.files, v.voiceover, original_lang=original_lang)]
        if not streams:
            _log.warning("Filmix returned no movie streams for item_id=%s", item_id)
        return streams

    @cached(3600, scope="account", empty_ttl=60)
    async def _fetch_multipart_streams(
        self,
        item_id: str | int,
        episode: int,
        *,
        original_lang: LangCode,
        refresh: bool = False,
    ) -> list[Stream]:
        resp = await self.http.get(f"{self._BASE_URL}/post/{item_id}/videos-movies", params=self._params())
        resp.raise_for_status()
        videos = MoviesList.validate_json(resp.text)
        streams: list[Stream] = []
        for v in videos:
            m = _PART_RE.search(v.voiceover)
            if m:
                if int(m.group(1)) == episode:
                    label = _PART_RE.sub('', v.voiceover).strip()
                    streams.extend(self._build_streams(v.files, label, original_lang=original_lang))
            else:
                streams.extend(
                    self._build_streams(
                        v.files,
                        v.voiceover,
                        edition=self.parser.profile.media.edition["combined"],
                        original_lang=original_lang,
                    )
                )
        if not streams:
            _log.warning("Filmix multipart episode not found for item_id=%s episode=%s", item_id, episode)
        return streams

    @cached(3600, scope="account", empty_ttl=60)
    async def _fetch_series_streams(
        self,
        item_id: str | int,
        season: int,
        episode: int,
        *,
        original_lang: LangCode,
        refresh: bool = False,
    ) -> list[Stream]:
        resp = await self.http.get(f"{self._BASE_URL}/post/{item_id}/videos-serial", params=self._params())
        resp.raise_for_status()
        playlist = SeriesPlaylist.validate_json(resp.text)

        season_key = f"season-{season}"
        episode_key = f"e{episode}"

        streams = [
            s
            for voice_name, seasons in playlist.items()
            if (season_data := seasons.get(season_key))
            if (ep_data := season_data.episodes.get(episode_key))
            for s in self._build_streams(ep_data.files, voice_name, original_lang=original_lang)
        ]
        if not streams:
            _log.warning(
                "Filmix series episode not found for item_id=%s season=%s episode=%s",
                item_id,
                season,
                episode,
            )
        return streams

    def _build_streams(self, files: list[VideoFile], label: str, *, edition: AttrVal | None = None, original_lang: LangCode) -> list[Stream]:
        parsed = self._parse_voiceover(label, original_lang=original_lang, parser=self.parser, language=self.language)
        streams: list[Stream] = []
        for f in sorted(files, key=lambda x: x.quality, reverse=True):
            if f.pro_plus:
                continue
            url = f.url
            if "hdr" in url.lower(): # Filmix serves HDR as HLS on some servers but it doesn't play - use direct URL instead
                url = self._hls_to_direct_url(url) or url
            streams.append(Stream(
                url=url,
                tracks=parsed.tracks,
                quality=self.parser.normalize('quality', str(f.quality)) or parsed.quality,
                codec=parsed.codec,
                hdr=parsed.hdr,
                edition=edition or parsed.edition,
            ))
        if files and not streams:
            _log.debug("Filmix produced no playable streams for label=%r", label)
        return streams

    async def resolve_streams(
        self,
        base_id: str,
        metadata: dict[str, MetadataClient],
        *,
        season: int | None = None,
        episode: int | None = None,
        refresh: bool = False,
    ) -> list[Stream]:
        tried: list[str] = []
        for client in metadata.values():
            info = await client.resolve(base_id, self.language)
            if not info:
                continue
            async for title in info.titles:
                if not is_readable(title):
                    continue
                tried.append(f"{title} ({info.year})")
                if found := await self._find(title, info.year, season=season, episode=episode, refresh=refresh):
                    is_series = found.last_episode is not None
                    if is_series and season is not None and episode is not None:
                        return await self._fetch_series_streams(
                            found.id,
                            season,
                            episode,
                            original_lang=info.original_lang,
                            refresh=refresh,
                        )
                    if not is_series and season is not None and episode is not None:
                        return await self._fetch_multipart_streams(
                            found.id,
                            episode,
                            original_lang=info.original_lang,
                            refresh=refresh,
                        )
                    return await self._fetch_movie_streams(found.id, original_lang=info.original_lang, refresh=refresh)
        if tried:
            _log.warning("No match for base_id=%s, tried: %s", base_id, "; ".join(tried))
        else:
            _log.warning("No resolvable titles for base_id=%s", base_id)
        return []

    @staticmethod
    def _hls_to_direct_url(url: str) -> str | None:
        if m := re.match(r"^(https?://[^/]+)/hls/(.*)/index\.m3u8\?hash=([^&]*)", url):
            base, path, hash_ = m.groups()
            return f"{base}/s/{hash_}/{path}"
        return None

    @staticmethod
    def _direct_to_hls_url(url: str) -> str | None:
        if m := re.match(r"^(https?://[^/]+)/s/([^/]+)/(.*)", url):
            base, hash_, path = m.groups()
            return f"{base}/hls/{path}/index.m3u8?hash={hash_}"
        return None
