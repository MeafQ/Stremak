import asyncio

import pytest

import utils
from utils import cached


@pytest.mark.anyio
async def test_global_cache_shares_results_across_instances():
    class Dummy:
        def __init__(self) -> None:
            self.calls = 0

        @cached(300)
        async def load(self, value: str, *, refresh: bool = False) -> str:
            self.calls += 1
            return f"{self.calls}:{value}"

    first = Dummy()
    second = Dummy()

    assert await first.load("a") == "1:a"
    assert await second.load("a") == "1:a"
    assert first.calls == 1
    assert second.calls == 0


@pytest.mark.anyio
async def test_account_cache_isolated_between_accounts_but_shared_within_one():
    class Dummy:
        def __init__(self, account: str) -> None:
            self.account = account
            self.calls = 0

        def cache_scope_key(self) -> tuple[str, str]:
            return ("dummy", self.account)

        @cached(300, scope="account")
        async def load(self, value: str, *, refresh: bool = False) -> str:
            self.calls += 1
            return f"{self.account}:{self.calls}:{value}"

    first = Dummy("a")
    second = Dummy("a")
    third = Dummy("b")

    assert await first.load("x") == "a:1:x"
    assert await second.load("x") == "a:1:x"
    assert await third.load("x") == "b:1:x"
    assert first.calls == 1
    assert second.calls == 0
    assert third.calls == 1


@pytest.mark.anyio
async def test_cached_refresh_bypasses_stale_value_once():
    class Dummy:
        def __init__(self) -> None:
            self.calls = 0

        @cached(300)
        async def load(self, value: str, *, refresh: bool = False) -> str:
            self.calls += 1
            return f"{self.calls}:{value}"

    dummy = Dummy()

    assert await dummy.load("x") == "1:x"
    assert await dummy.load("x", refresh=True) == "2:x"
    assert await dummy.load("x") == "2:x"
    assert dummy.calls == 2


@pytest.mark.anyio
async def test_single_flight_coalesces_identical_requests():
    class Dummy:
        def __init__(self) -> None:
            self.calls = 0

        @cached(300)
        async def load(self, value: str, *, refresh: bool = False) -> str:
            self.calls += 1
            await asyncio.sleep(0.01)
            return f"{self.calls}:{value}"

    dummy = Dummy()
    results = await asyncio.gather(*(dummy.load("x") for _ in range(5)))

    assert results == ["1:x"] * 5
    assert dummy.calls == 1


@pytest.mark.anyio
async def test_cached_empty_results_use_shorter_ttl(monkeypatch):
    now = {"value": 0.0}
    monkeypatch.setattr(utils, "time", lambda: now["value"])

    class Dummy:
        def __init__(self) -> None:
            self.calls = 0

        @cached(300, empty_ttl=60)
        async def load(self, value: str, *, refresh: bool = False) -> list[str]:
            self.calls += 1
            return []

    dummy = Dummy()

    assert await dummy.load("x") == []
    assert await dummy.load("x") == []
    assert dummy.calls == 1

    now["value"] = 61.0
    assert await dummy.load("x") == []
    assert dummy.calls == 2


@pytest.mark.anyio
async def test_cached_empty_results_can_be_disabled(monkeypatch):
    now = {"value": 0.0}
    monkeypatch.setattr(utils, "time", lambda: now["value"])

    class Dummy:
        def __init__(self) -> None:
            self.calls = 0

        @cached(300, empty_ttl=0)
        async def load(self, value: str, *, refresh: bool = False) -> list[str]:
            self.calls += 1
            return []

    dummy = Dummy()

    assert await dummy.load("x") == []
    assert await dummy.load("x") == []
    assert dummy.calls == 2
