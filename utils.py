import asyncio
import base64
import functools
import json
import re
from dataclasses import dataclass
from time import time
from typing import (
    Any,
    Callable,
    Concatenate,
    Coroutine,
    Iterator,
    Literal,
    ParamSpec,
    Protocol,
    TypeVar,
)

T = TypeVar("T")
P = ParamSpec('P')

CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

class _TTLStore[K, V]:
    def __init__(self, ttl: int = 300, maxsize: int = 10_000):
        self.ttl = ttl
        self.maxsize = maxsize
        self._data: dict[K, tuple[V, float]] = {}
    
    def get(self, key: K) -> V | None:
        if entry := self._data.get(key):
            if time() < entry[1]:
                return entry[0]
            del self._data[key]
        return None
    
    def set(self, key: K, value: V, *, ttl: int | float | None = None) -> None:
        ttl_value = self.ttl if ttl is None else ttl
        if ttl_value <= 0:
            self._data.pop(key, None)
            return
        if key not in self._data and len(self._data) >= self.maxsize:
            now = time()
            self._data = {k: v for k, v in self._data.items() if now < v[1]}
        self._data[key] = (value, time() + ttl_value)

    def all_valid(self) -> Iterator[V]:
        now = time()
        for value, expires in self._data.values():
            if now < expires:
                yield value

class CachedMethod(Protocol[P, T]):
    store: _TTLStore[tuple, T]
    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T: ...

CacheScope = Literal["global", "account"]


def _cache_scope_key(scope: CacheScope, self_: Any) -> tuple[Any, ...]:
    if scope == "global":
        return ()

    cache_scope_key = getattr(self_, "cache_scope_key", None)
    if not callable(cache_scope_key):
        raise TypeError(f"{type(self_).__name__} must define cache_scope_key() for account-scoped caching")

    scope_key = cache_scope_key()
    if isinstance(scope_key, tuple):
        return scope_key
    return (scope_key,)


def _is_empty_result(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, bytes, bytearray)):
        return len(value) == 0
    try:
        return len(value) == 0  # type: ignore[arg-type]
    except TypeError:
        return False


def cached[**P, T](
    ttl: int = 300,
    maxsize: int = 10_000,
    *,
    scope: CacheScope = "global",
    empty_ttl: int | float | None = None,
) -> Callable[[Callable[Concatenate[Any, P], Coroutine[Any, Any, T]]], CachedMethod[P, T]]:
    def decorator(method: Callable[Concatenate[Any, P], Coroutine[Any, Any, T]]) -> CachedMethod[P, T]:
        store: _TTLStore[tuple, T] = _TTLStore(ttl, maxsize)
        inflight: dict[tuple, asyncio.Task[T]] = {}
        
        @functools.wraps(method)
        async def wrapper(self_: Any, *args: P.args, **kwargs: P.kwargs) -> T:
            refresh = bool(kwargs.get("refresh", False))
            key = (_cache_scope_key(scope, self_), args, tuple(sorted((k, v) for k, v in kwargs.items() if k != "refresh")))
            if not refresh and (result := store.get(key)) is not None:
                return result

            if task := inflight.get(key):
                return await task

            task = asyncio.create_task(method(self_, *args, **kwargs))
            inflight[key] = task
            try:
                result = await task
            finally:
                inflight.pop(key, None)
            ttl_override = empty_ttl if empty_ttl is not None and _is_empty_result(result) else None
            store.set(key, result, ttl=ttl_override)
            return result
        
        wrapper.store = store  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]
    return decorator

def b64_encode(data) -> str:
    return base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")

def b64_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode()

def encode_config(config: dict) -> str:
    return b64_encode(json.dumps(config))

def decode_config(config_str: str) -> dict:
    if not config_str:
        return {}
    try:
        return json.loads(b64_decode(config_str))
    except Exception:
        return {}
    
_SLUG_RE = re.compile(r'[^\w-]+', re.UNICODE)

def slugify(text: str) -> str:
    return _SLUG_RE.sub('-', text).strip('-').lower()

def truncate_query(text: str, max_words: int = 8) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])
