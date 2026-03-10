import html
import unicodedata
from dataclasses import dataclass
from typing import ClassVar, Protocol, Self, Sequence, TypeVar, runtime_checkable

from rapidfuzz import fuzz
from starlette.routing import Route

from metadata.base import MetadataClient

from .parsing.core import Media, Parser
from .parsing.formatting import format_stream
from .parsing.specs import DEFAULT_PARSING_SPECS, ParsingSpecs


class Matchable(Protocol):
    @property
    def id(self) -> int | str: ...
    @property
    def title(self) -> str: ...
    @property
    def year(self) -> int: ...
    @property
    def original_title(self) -> str | None: ...

_M = TypeVar("_M", bound=Matchable)


@dataclass(frozen=True, slots=True, kw_only=True)
class Stream(Media):
    url: str

    def format(self, *, specs: ParsingSpecs = DEFAULT_PARSING_SPECS) -> str:
        return format_stream(self, specs=specs)

    def display_name(self, source: str) -> str:
        return source

def _normalize(text: str) -> str:
    text = html.unescape(text)
    text = unicodedata.normalize("NFKD", text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return text.casefold()

def best_match(results: Sequence[_M], title: str, year: int, tolerance: int = 1) -> _M | None:
    title_norm = _normalize(title)
    candidates = (
        item for item in results
        if year - tolerance <= item.year <= year
        and (
            (normalized := _normalize(item.title)) == title_norm
            or fuzz.ratio(normalized, title_norm) >= 95.0
            or (
                item.original_title
                and (
                    (normalized_original := _normalize(item.original_title)) == title_norm
                    or fuzz.ratio(normalized_original, title_norm) >= 95.0
                )
            )
        )
    )
    return max(candidates, key=lambda item: item.year, default=None)

def is_readable(text: str, scripts: tuple[str, ...] = ("LATIN", "CYRILLIC")) -> bool:
    for c in text:
        if c.isalpha() and not any(s in unicodedata.name(c, "") for s in scripts):
            return False
    return True

class StreamingModule(Protocol):
    slug: ClassVar[str]
    template: ClassVar[str]
    name: ClassVar[str]

    @classmethod
    def get_routes(cls) -> Sequence[Route]: ...

@runtime_checkable
class StreamingService(StreamingModule, Protocol):
    specs: ParsingSpecs
    parser: Parser

    async def resolve_streams(
        self,
        base_id: str,
        metadata: dict[str, MetadataClient],
        *,
        season: int | None = None,
        episode: int | None = None,
        refresh: bool = False,
    ) -> list[Stream]: ...


def select_stream_by_identity(
    streams: list[Stream],
    play_identity: dict,
    *,
    parser: Parser,
) -> tuple[Stream | None, int, int, bool]:
    if not streams:
        return None, 0, 0, False

    target = parser.profile.media.decode_identity(play_identity)
    required_weight, scored = target.match_candidates(streams)
    if not scored:
        return None, required_weight, 0, target.has_min_identity()

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score = scored[0][0]
    top = [stream for score, stream in scored if score == best_score]
    return top[0], required_weight, len(top), target.has_min_identity()
