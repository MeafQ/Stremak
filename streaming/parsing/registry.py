import re
from collections.abc import Iterable
from dataclasses import replace
from typing import Generic, Self, cast

from rapidfuzz import fuzz

from .values import AttrVal, IdT, Org, OrgKind, OrgList, TrackAttrVal, TrackIdT, ValueT


class Registry(Generic[IdT, ValueT]):
    __slots__ = ("name", "_values")

    def __init__(self, name: str) -> None:
        self.name = name
        self._values: dict[IdT, ValueT] = {}

    def _store(self, id: IdT, value: ValueT) -> ValueT:
        if id in self._values:
            raise ValueError(f"Duplicate key '{id}' in {self.name}")
        if value.id != id:
            raise ValueError(f"{self.name} value id mismatch: expected '{id}', got '{value.id}'")
        if value.label or value.msgid is not None:
            self._values[id] = value
        else:
            self._values[id] = cast(ValueT, replace(value, label=id))
        return self._values[id]

    def __getitem__(self, id: IdT) -> ValueT:
        return self._values[id]

    def get(self, id: IdT) -> ValueT | None:
        return self._values.get(id)

    def values(self) -> Iterable[ValueT]:
        return self._values.values()

    def clone(self) -> Self:
        clone = type(self)(self.name)
        clone._values = dict(self._values)
        return cast(Self, clone)


class Attr(Registry[IdT, AttrVal[IdT]], Generic[IdT]):
    __slots__ = ()

    def add(
        self,
        id: IdT,
        /,
        *,
        score: int = 0,
        label: str | None = None,
        msgid: str | None = None,
        hidden: bool = False,
    ) -> AttrVal[IdT]:
        return self._store(
            id,
            AttrVal(
                id=id,
                score=score,
                label="" if label is None else label,
                msgid=msgid,
                hidden=hidden,
            ),
        )


class TrackAttr(Registry[TrackIdT, TrackAttrVal[TrackIdT]], Generic[TrackIdT]):
    __slots__ = ()

    def add(
        self,
        id: TrackIdT,
        /,
        *,
        score: int = 0,
        label: str | None = None,
        msgid: str | None = None,
        hidden: bool = False,
        confidence: int = 0,
        anchored: bool = False,
    ) -> TrackAttrVal[TrackIdT]:
        return self._store(
            id,
            TrackAttrVal(
                id=id,
                score=score,
                label="" if label is None else label,
                msgid=msgid,
                hidden=hidden,
                confidence=confidence,
                anchored=anchored,
            ),
        )


class OrgAttr(TrackAttr[str]):
    __slots__ = ("kind", "fuzzy_ratio")

    def __init__(self, name: str, *, kind: OrgKind, fuzzy_ratio: int = OrgList.FUZZY_RATIO) -> None:
        super().__init__(name)
        self.kind = kind
        self.fuzzy_ratio = fuzzy_ratio

    def clone(self) -> Self:
        clone = type(self)(self.name, kind=self.kind, fuzzy_ratio=self.fuzzy_ratio)
        clone._values = dict(self._values)
        return cast(Self, clone)

    def to_org(
        self,
        value: TrackAttrVal[str],
        /,
        *,
        confidence: int | None = None,
        anchored: bool | None = None,
        hidden: bool = False,
    ) -> Org:
        return Org.from_value(
            value,
            kind=self.kind,
            confidence=confidence,
            anchored=anchored,
            hidden=hidden,
        )

    def find(self, raw: str) -> TrackAttrVal[str] | None:
        if value := self.get(raw):
            return value
        raw_folded = raw.casefold()
        return next(
            (
                candidate
                for candidate in self.values()
                if candidate.id.casefold() == raw_folded
                or fuzz.ratio(raw_folded, candidate.id.casefold()) >= self.fuzzy_ratio
            ),
            None,
        )


class Marker(Generic[ValueT]):
    __slots__ = ("attrs", "blocked", "compiled")

    def __init__(self, pattern: str, /, *, blocked: tuple[str, ...] = (), **attrs: ValueT) -> None:
        overlap = set(attrs) & set(blocked)
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ValueError(f"Marker cannot both set and block the same field(s): {names}")
        self.attrs: dict[str, ValueT] = attrs
        self.blocked = frozenset(blocked)
        self.compiled = re.compile(pattern, re.I)
