from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import ClassVar, Self, Sequence

import httpx

from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from metadata.base import MediaInfo, _TitleStream
from metadata.tmdb.models import (
    AltTitlesResponse,
    FindResponse,
    MovieResult,
    SeriesResult,
)
from utils import cached


class Config(BaseModel):
    api_key: str


@dataclass
class TheMovieDB:
    _BASE_URL: ClassVar[str] = "https://api.themoviedb.org/3"
    slug: ClassVar[str] = "tmdb"
    template: ClassVar[str]  = "metadata/tmdb/template.html"
    
    http: httpx.AsyncClient = field(repr=False)
    api_key: str
    
    @classmethod
    def from_config(cls, http: httpx.AsyncClient, raw: dict) -> Self | None:
        config = Config.model_validate(raw.get(cls.slug, {}))
        if config.api_key:
            return cls(http=http, api_key=config.api_key)
        return None

    @classmethod
    async def _check_key(cls, request: Request) -> JSONResponse:
        api_key = request.query_params.get("api_key", "")
        if not api_key:
            return JSONResponse({"error": "API key required"}, status_code=400)
        
        http = request.app.state.http
        resp = await http.get(f"https://api.themoviedb.org/3/configuration?api_key={api_key}")
        if resp.status_code == 200:
            return JSONResponse({"ok": True})
        return JSONResponse({"error": "Invalid API key"}, status_code=401)

    @classmethod
    def get_routes(cls) -> Sequence[Route]:
        return [
            Route("/api/auth/tmdb/check", cls._check_key, methods=["GET"])
        ]

    def _params(self, **params) -> dict[str, str]:
        return {"api_key": self.api_key, **params}

    async def resolve(self, raw_id: str, language: str) -> MediaInfo | None:
        if not raw_id.startswith("tt"):
            return None

        media = (await self.find_by_imdb(raw_id, language=language)).first
        if not media:
            return None

        async def _titles() -> AsyncIterator[str]:
            seen: set[str] = set()
            for title in (media.title, media.original_title):
                if title not in seen:
                    seen.add(title)
                    yield title

            target_langs = {language, media.original_language}
            alt = await self.get_alt_titles(media)
            for t in alt.all:
                if t.lang in target_langs and t.title not in seen:
                    seen.add(t.title)
                    yield t.title

        return MediaInfo(
            year=media.release_date.year,
            original_lang=media.original_language,
            titles=_TitleStream(_titles),
        )

    @cached(3600)
    async def find_by_imdb(self, imdb_id: str, language: str = "ru-RU") -> FindResponse:
        resp = await self.http.get(f"{self._BASE_URL}/find/{imdb_id}", params=self._params(external_source="imdb_id", language=language))
        resp.raise_for_status()
        return FindResponse.model_validate_json(resp.text)

    @cached(3600)
    async def get_alt_titles(self, media: MovieResult | SeriesResult) -> AltTitlesResponse:
        endpoint = "tv" if isinstance(media, SeriesResult) else "movie"
        resp = await self.http.get(f"{self._BASE_URL}/{endpoint}/{media.id}/alternative_titles", params=self._params())
        resp.raise_for_status()
        return AltTitlesResponse.model_validate_json(resp.text)