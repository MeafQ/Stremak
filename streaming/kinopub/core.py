import logging
import random
import re
import string
import time
from dataclasses import dataclass, field, replace
from typing import ClassVar, Sequence

import httpx
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from languages import LangCode, to_alpha2
from metadata.base import MetadataClient
from streaming.base import Stream, best_match, is_readable
from streaming.parsing.catalog import Lang, VoiceType, default_profile
from streaming.parsing.core import AttrVal, Parser, Track
from utils import CORS_HEADERS, cached, truncate_query

from .models import (
    AudioTrack,
    DeviceCodeResponse,
    DeviceInfoResponse,
    ItemDetail,
    ItemResponse,
    SearchItem,
    SearchResponse,
    TokenResponse,
    UserResponse,
    VideoFile,
)

_log = logging.getLogger(__name__)

class KinoPubSettings(BaseModel):
    token: str | None = None
    refresh_token: str | None = None

    def is_configured(self) -> bool:
        return bool(self.token)

@dataclass
class KinoPub:
    slug: ClassVar[str] = "kinopub"
    template: ClassVar[str] = "streaming/kinopub/template.html"
    name: ClassVar[str] = "KinoPub"
    profile = default_profile
    parser: ClassVar[Parser] = profile.build_parser()
    http: httpx.AsyncClient

    @classmethod
    def from_settings(cls, http: httpx.AsyncClient, settings: KinoPubSettings | None) -> 'KinoPubPrivate | None':
        if settings and settings.token:
            return KinoPubPrivate(http=http, token=settings.token, refresh_token=settings.refresh_token or "")
        return None

    @classmethod
    def get_routes(cls) -> Sequence[Route]:
        return [
            Route("/api/auth/kinopub/start", cls._auth_start, methods=["GET"]),
            Route("/api/auth/kinopub/poll", cls._auth_poll, methods=["GET"]),
            Route("/api/auth/kinopub/check", cls._auth_check, methods=["GET"]),
        ]

    @classmethod
    async def _auth_start(cls, request: Request) -> JSONResponse:
        service = cls(http=request.app.state.http)
        response = await service.request_device_code()
        return JSONResponse({
            "user_code": response.user_code,
            "verification_uri": response.verification_uri,
            "device_code": response.code,
            "interval": response.interval,
        }, headers=CORS_HEADERS)

    @classmethod
    async def _auth_poll(cls, request: Request) -> JSONResponse:
        code = request.query_params.get("code", "")
        if not code:
            return JSONResponse({"error": "Code required"}, status_code=400, headers=CORS_HEADERS)
        service = cls(http=request.app.state.http)
        result = await service.poll_device_token(code)
        if result is None:
            return JSONResponse({"error": "authorization_pending"}, status_code=202, headers=CORS_HEADERS)
        await service.notify_device(result.access_token)
        device_id = await service.get_device_id(result.access_token)
        if device_id:
            await service.configure_device(result.access_token, device_id)
        return JSONResponse({
            "access_token": result.access_token,
            "refresh_token": result.refresh_token,
        }, headers=CORS_HEADERS)

    @classmethod
    async def _auth_check(cls, request: Request) -> JSONResponse:
        token = request.query_params.get("token", "")
        refresh_token = request.query_params.get("refresh_token", "")
        if not token:
            return JSONResponse({"error": "Token required"}, status_code=400, headers=CORS_HEADERS)
        service = KinoPubPrivate(http=request.app.state.http, token=token, refresh_token=refresh_token)
        user = await service.get_user_info()
        if not user:
            return JSONResponse({"error": "Not authenticated"}, status_code=401, headers=CORS_HEADERS)
        return JSONResponse({
            "username": user.username,
            "name": user.profile.name if user.profile else None,
            "avatar": user.profile.avatar if user.profile else None,
            "subscription_active": user.subscription.active if user.subscription else False,
            "subscription_days": round(user.subscription.days) if user.subscription else 0,
        }, headers=CORS_HEADERS)

    _HOSTS: ClassVar[tuple[str, ...]] = (
        "https://ro03.flexcdn.cloud",
        "https://ro01.flexcdn.cloud",
        "https://ro02.flexcdn.cloud",
    )
    _CLIENT_ID: ClassVar[str] = "appletv2"
    _CLIENT_SECRET: ClassVar[str] = "3z5124kj5liqy9gahnjr07qpj65ferl2"
    _ENABLE_REFRESH_TOKEN_FLOW: ClassVar[bool] = False
    _USER_AGENT: ClassVar[str] = "MicroIPTV/8 CFNetwork/3860.300.31 Darwin/25.2.0"
    _DEVICE_TITLE: ClassVar[str] = "KinopubApp"
    _DEVICE_SOFTWARE: ClassVar[str] = "AppleTV (Micro IPTV 8)"
    _DEVICE_HARDWARE: ClassVar[str] = "AppleTV14,1 (26.2)"

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", self._USER_AGENT)
        last_exc: Exception = RuntimeError("No hosts configured")
        for host in self._HOSTS:
            try:
                return await self.http.request(method, f"{host}{path}", headers=headers, **kwargs)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
        raise last_exc

    @staticmethod
    def _rand() -> str:
        length = random.randint(2, 128)
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def _auth_body(self, grant_type: str, **extra: str) -> dict[str, str]:
        return {"client_id": self._CLIENT_ID, "client_secret": self._CLIENT_SECRET, "grant_type": grant_type, "rand": self._rand(), **extra}

    async def request_device_code(self) -> DeviceCodeResponse:
        resp = await self._request("POST", "/api/oauth2/device", json=self._auth_body("device_code"))
        resp.raise_for_status()
        return DeviceCodeResponse.model_validate_json(resp.text)

    async def poll_device_token(self, code: str) -> TokenResponse | None:
        resp = await self._request("POST", "/api/oauth2/device", json=self._auth_body("device_token", code=code))
        if resp.status_code == 400:
            return None
        resp.raise_for_status()
        return TokenResponse.model_validate_json(resp.text)

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse | None:
        if not self._ENABLE_REFRESH_TOKEN_FLOW:
            _log.debug("KinoPub refresh-token flow is currently disabled")
            return None
        resp = await self._request("POST", "/api/oauth2/device", json=self._auth_body("refresh_token", refresh_token=refresh_token))
        if resp.status_code == 400:
            return None
        resp.raise_for_status()
        return TokenResponse.model_validate_json(resp.text)

    async def get_device_id(self, access_token: str) -> int | None:
        resp = await self._request("GET", "/api/v1/device/info", params={"access_token": access_token})
        if resp.status_code != 200:
            return None
        return DeviceInfoResponse.model_validate_json(resp.text).device.id

    async def notify_device(self, access_token: str) -> bool:
        resp = await self._request(
            "POST", "/api/v1/device/notify",
            params={"access_token": access_token},
            json={
                "title": self._DEVICE_TITLE,
                "software": self._DEVICE_SOFTWARE,
                "hardware": self._DEVICE_HARDWARE,
                "rand": self._rand(),
            },
        )
        return resp.status_code == 200

    async def configure_device(self, access_token: str, device_id: int) -> bool:
        resp = await self._request(
            "POST", f"/api/v1/device/{device_id}/settings",
            params={"access_token": access_token},
            json={"page": 0, "perpage": "47", "support4k": True, "supportHevc": True, "mixedPlaylist": True},
        )
        return resp.status_code == 200


@dataclass
class KinoPubPrivate(KinoPub):
    language: ClassVar[LangCode] = 'ru'
    token: str = field(repr=False, kw_only=True)
    refresh_token: str = field(default="", repr=False, kw_only=True)

    # token -> (access_token, latest_refresh_token, expiry_timestamp)
    _token_cache: ClassVar[dict[str, tuple[str, str, float]]] = {}

    def cache_scope_key(self) -> tuple[str, str]:
        return (self.slug, self.token)

    def _params(self, **params: str) -> dict[str, str]:
        return {"access_token": self.token, **params}

    def _get_access_token(self) -> str:
        cached = self._token_cache.get(self.token)
        if cached:
            access_token, _, expiry = cached
            if time.time() < expiry:
                return access_token
        return self.token

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        params = kwargs.get("params")
        if not isinstance(params, dict) or "access_token" not in params:
            return await super()._request(method, path, **kwargs)

        params["access_token"] = self._get_access_token()
        resp = await super()._request(method, path, **kwargs)

        if resp.status_code == 401 and self.refresh_token:
            cached = self._token_cache.get(self.token)
            refresh_tok = cached[1] if cached else self.refresh_token
            try:
                result = await self.refresh_access_token(refresh_tok)
                if result:
                    self._token_cache[self.token] = (
                        result.access_token, result.refresh_token,
                        time.time() + result.expires_in - 600,
                    )
                    params["access_token"] = result.access_token
                    resp = await super()._request(method, path, **kwargs)
            except Exception:
                _log.debug("KinoPub token refresh failed", exc_info=True)

        return resp

    async def get_user_info(self):
        resp = await self._request("GET", "/api/v1/user", params=self._params())
        if resp.status_code == 401:
            return None
        resp.raise_for_status()
        return UserResponse.model_validate_json(resp.text).user

    @cached(300, empty_ttl=60)
    async def search(self, title: str, *, refresh: bool = False) -> Sequence[SearchItem]:    
        resp = await self._request("GET", "/api2/v1.1/items/search", params={"q": truncate_query(title)},)
        resp.raise_for_status()
        return SearchResponse.model_validate_json(resp.text).items

    async def _find(self, title: str, year: int, *, imdb_id: str | None = None, refresh: bool = False) -> list[SearchItem]:
        if not refresh:
            for results in self.search.store.all_valid():
                if found := self._match_items(results, title, year, imdb_id=imdb_id):
                    return found
        results = await self.search(title, refresh=refresh)
        return self._match_items(results, title, year, imdb_id=imdb_id)

    @staticmethod
    def _match_items(results: Sequence[SearchItem], title: str, year: int, *, imdb_id: str | None = None) -> list[SearchItem]:
        if imdb_id:
            try:
                imdb_num = int(imdb_id.lstrip("t"))
            except ValueError:
                imdb_num = 0
            else:
                matches = [item for item in results if item.imdb and item.imdb == imdb_num]
                if matches:
                    return matches
        found = best_match(results, title, year)
        return [found] if found else []

    @cached(3600, scope="account", empty_ttl=60)
    async def _get_item(self, item_id: int, *, refresh: bool = False) -> ItemDetail | None:
        resp = await self._request("GET", f"/api/v1/items/{item_id}", params=self._params())
        if resp.status_code in (401, 404):
            return None
        resp.raise_for_status()
        return ItemResponse.model_validate_json(resp.text).item

    @classmethod
    def _audio_to_track(cls, audio: AudioTrack) -> Track:
        track = cls.parser.parse_track(audio.author.title) if audio.author and audio.author.title else Track()
        lang_code = to_alpha2(audio.lang)
        updates: dict[str, object] = {'index': audio.index}
        if lang_code and (lang := Lang.get(lang_code)):
            updates['lang'] = lang
        if audio.type and audio.type.short_title and (vt := cls.parser.normalize("voice_type", audio.type.short_title)):
            updates['voice_type'] = vt
        if audio.codec and (af := cls.parser.normalize("audio_format", audio.codec)):
            updates['audio_format'] = af
        return replace(track, **updates)

    @classmethod
    def _infer_languages(cls, tracks: list[Track], *, original_lang: LangCode) -> list[Track]:
        if len(tracks) < 2:
            return tracks

        result = list(tracks)
        if result[0].lang is None:
            result[0] = result[0].with_language(cls.language, lang_attr=Lang)
        if len(result) == 2 and result[1].lang is None:
            result[1] = result[1].with_language(original_lang, lang_attr=Lang).with_original(voice_type_attr=VoiceType)
        return result

    def _build_streams(self, audios: list[AudioTrack], files: list[VideoFile], *, edition: AttrVal | None = None, original_lang: LangCode) -> list[Stream]:
        tracks = self._infer_languages([self._audio_to_track(a) for a in audios], original_lang=original_lang)
        hevc_qualities = {f.quality_id for f in files if f.codec == "h265"}
        filtered = [f for f in files if f.codec != "h264" or f.quality_id not in hevc_qualities]
        streams: list[Stream] = []
        for audio, track in zip(audios, tracks):
            for f in sorted(filtered, key=lambda f: f.quality_id, reverse=True):
                url = re.sub(r"a\d+\.m3u8", f"a{audio.index}.m3u8", f.url.hls, count=1) if f.url.hls else (f.url.hls4 or f.url.http)
                if not url:
                    continue
                streams.append(Stream(
                    url=url,
                    tracks=(track,),
                    quality=self.parser.normalize("quality", f.quality),
                    codec=self.parser.normalize("codec", f.codec),
                    edition=edition,
                ))
        if audios and files and not streams:
            _log.debug("KinoPub produced no playable streams for %s audio tracks", len(audios))
        return streams

    async def _fetch_movie_streams(self, item: ItemDetail, *, original_lang: LangCode) -> list[Stream]:
        if not item.videos:
            _log.warning("KinoPub item has no videos for title=%r", item.title)
            return []
        all_streams: list[Stream] = []
        for video in item.videos:
            edition = self.parser.normalize("edition", video.title) if len(item.videos) > 1 else self.parser.normalize("edition", item.title)
            all_streams.extend(self._build_streams(video.audios, video.files, edition=edition, original_lang=original_lang))
        if not all_streams:
            _log.warning("KinoPub returned no movie streams for title=%r", item.title)
        return all_streams

    async def _fetch_series_streams(self, item: ItemDetail, season: int, episode: int, *, original_lang: LangCode) -> list[Stream]:
        if item.seasons:
            season_data = next((s for s in item.seasons if s.number == season), None)
            if not season_data:
                _log.warning("KinoPub season not found for title=%r season=%s", item.title, season)
                return []
            episode_data = next((e for e in season_data.episodes if e.number == episode), None)
            if not episode_data:
                _log.warning("KinoPub episode not found for title=%r season=%s episode=%s", item.title, season, episode)
                return []
            return self._build_streams(episode_data.audios, episode_data.files, edition=self.parser.normalize("edition", item.title), original_lang=original_lang)
        # Fallback: movie with multiple videos (Stremio may treat these as series)
        if item.videos:
            video = next((v for v in item.videos if v.number == episode), None)
            if not video:
                _log.warning("KinoPub multipart episode not found for title=%r episode=%s", item.title, episode)
                return []
            return self._build_streams(video.audios, video.files, edition=self.parser.normalize("edition", video.title), original_lang=original_lang)
        _log.warning("KinoPub item has no series or fallback videos for title=%r", item.title)
        return []

    async def resolve_streams(
        self,
        base_id: str,
        metadata: dict[str, MetadataClient],
        *,
        season: int | None = None,
        episode: int | None = None,
        refresh: bool = False,
    ) -> list[Stream]:
        imdb_id = base_id if base_id.startswith("tt") else None
        tried: list[str] = []
        for client in metadata.values():
            info = await client.resolve(base_id, self.language)
            if not info:
                continue
            async for title in info.titles:
                if not is_readable(title):
                    continue
                tried.append(f"{title} ({info.year})")
                if found_items := await self._find(title, info.year, imdb_id=imdb_id, refresh=refresh):
                    all_streams: list[Stream] = []
                    for item in found_items:
                        detail = await self._get_item(item.id, refresh=refresh)
                        if not detail:
                            continue
                        if season is not None and episode is not None:
                            all_streams.extend(await self._fetch_series_streams(detail, season, episode, original_lang=info.original_lang))
                        else:
                            all_streams.extend(await self._fetch_movie_streams(detail, original_lang=info.original_lang))
                    return all_streams
        if tried:
            _log.warning("No match for base_id=%s, tried: %s", base_id, "; ".join(tried))
        else:
            _log.warning("No resolvable titles for base_id=%s", base_id)
        return []
