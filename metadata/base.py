from collections.abc import AsyncIterable, AsyncIterator, Callable
from dataclasses import dataclass
from typing import ClassVar, Protocol, Sequence

from starlette.routing import Route

from languages import LangCode


class _TitleStream:
    """Reusable async iterable — each ``async for`` creates a fresh iterator."""
    __slots__ = ("_factory",)
    def __init__(self, factory: Callable[[], AsyncIterator[str]]) -> None:
        self._factory = factory
    def __aiter__(self) -> AsyncIterator[str]:
        return self._factory()

@dataclass(slots=True)
class MediaInfo:
    year: int
    original_lang: LangCode
    titles: AsyncIterable[str]

class MetadataModule(Protocol):
    slug: ClassVar[str]
    template: ClassVar[str]

    @classmethod
    def get_routes(cls) -> Sequence[Route]: ...

class MetadataClient(Protocol):
    async def resolve(self, raw_id: str, language: str) -> MediaInfo | None: ...
