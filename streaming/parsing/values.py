from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, ClassVar, Generic, Self, TypeVar

from rapidfuzz import fuzz

MIN_MATCH_WEIGHT = 4
IdT = TypeVar("IdT", bound=str)
TrackIdT = TypeVar("TrackIdT", bound=str)
ValueT = TypeVar("ValueT", bound="AttrVal[Any]")


@dataclass(frozen=True, slots=True, kw_only=True)
class AttrVal(Generic[IdT]):
    id: IdT
    score: int = 0
    label: str = ""
    msgid: str | None = None
    hidden: bool = False

    @property
    def display(self) -> str | None:
        if self.hidden or not self.label:
            return None
        return self.label

    def __eq__(self, other: object) -> bool:
        if isinstance(other, AttrVal):
            return self.id == other.id
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class TrackAttrVal(AttrVal[TrackIdT], Generic[TrackIdT]):
    confidence: int = 0
    anchored: bool = False

    def __neg__(self) -> Self:
        return replace(self, confidence=-10)

    def __pos__(self) -> Self:
        return replace(self, confidence=10)

    def anchor(self) -> Self:
        if self.anchored:
            return self
        return replace(self, anchored=True)


class OrgKind(StrEnum):
    STUDIO = "studio"
    NETWORK = "network"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Org(TrackAttrVal[str]):
    kind: OrgKind = OrgKind.UNKNOWN

    @classmethod
    def from_value(
        cls,
        value: TrackAttrVal[str],
        /,
        *,
        kind: OrgKind | str,
        confidence: int | None = None,
        anchored: bool | None = None,
        hidden: bool = False,
    ) -> "Org":
        return cls(
            id=value.id,
            score=value.score,
            label=value.label,
            msgid=value.msgid,
            hidden=hidden,
            confidence=value.confidence if confidence is None else confidence,
            anchored=value.anchored if anchored is None else anchored,
            kind=OrgKind(kind),
        )


@dataclass(frozen=True, slots=True)
class OrgList:
    items: tuple[Org, ...] = ()

    FUZZY_RATIO: ClassVar[int] = 85

    def __iter__(self) -> Iterator[Org]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return bool(self.items)

    def __getitem__(self, index: int) -> Org:
        return self.items[index]

    def max_score(self) -> int:
        return max((org.score for org in self.items), default=0)

    def identity_ids(self) -> tuple[str, ...]:
        return tuple(sorted({org.id for org in self.items}, key=str.casefold))

    def with_confidence(self, offset: int) -> "OrgList":
        return OrgList(tuple(replace(org, confidence=org.confidence + offset) for org in self.items))

    @classmethod
    def same(cls, left: Org, right: Org) -> bool:
        return left.id.casefold() == right.id.casefold() or fuzz.ratio(
            left.id.casefold(),
            right.id.casefold(),
        ) >= cls.FUZZY_RATIO

    @staticmethod
    def _priority(org: Org) -> tuple[int, int, int, int]:
        return (org.kind != OrgKind.UNKNOWN, org.anchored, org.confidence, org.score)

    def merged(self, extra: Iterable[Org]) -> "OrgList":
        merged = list(self.items)
        for org in extra:
            for index, existing in enumerate(merged):
                if not self.same(existing, org):
                    continue
                if self._priority(org) > self._priority(existing):
                    merged[index] = org
                break
            else:
                merged.append(org)
        return OrgList(tuple(merged))

    def overlaps(self, other: "OrgList") -> bool:
        return any(self.same(left, right) for left in self.items for right in other.items)

    def shared_count(self, other: "OrgList") -> int:
        left_ids = {org.id.casefold() for org in self.items}
        right_ids = {org.id.casefold() for org in other.items}
        return len(left_ids & right_ids)
