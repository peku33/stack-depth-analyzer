from collections.abc import Collection, Set
from dataclasses import dataclass
from functools import cached_property

from more_itertools import is_sorted

from ..common import Address
from .common import PRIORITY_GROUPS


@dataclass(frozen=True, kw_only=True)
class EntrypointVector:
    address: Address

    def __post_init__(self) -> None:
        # address must be aligned
        assert self.address % 2 == 0


@dataclass(frozen=True, kw_only=True)
class EntrypointVectorWithPriorityGroup:
    vector: EntrypointVector
    priority_group: int | None  # None - unspecified

    def __post_init__(self) -> None:
        # validate range
        assert self.priority_group is None or 0 <= self.priority_group < PRIORITY_GROUPS


@dataclass(frozen=True, kw_only=True)
class EntrypointInterrupt:
    number: int  # 0-based, 32 maximum
    name: str
    vector_with_priority_group: EntrypointVectorWithPriorityGroup

    def __post_init__(self) -> None:
        # must be in range
        assert 0 <= self.number < 32


@dataclass(frozen=True)
class EntrypointInterrupts:
    inner: Collection[EntrypointInterrupt]

    def __post_init__(self) -> None:
        # must be sorted by number (and unique)
        assert is_sorted(
            (interrupt.number for interrupt in self.inner),
            strict=True,
        )


@dataclass(frozen=True, kw_only=True)
class Entrypoints:
    reset: EntrypointVector

    nmi: EntrypointVector | None
    hardfault: EntrypointVector

    svcall: EntrypointVectorWithPriorityGroup | None
    pendsv: EntrypointVectorWithPriorityGroup | None
    systick: EntrypointVectorWithPriorityGroup | None

    interrupts: EntrypointInterrupts

    @cached_property
    def addresses(self) -> Set[Address]:
        return {
            self.reset.address,
            *({self.nmi.address} if self.nmi is not None else set()),
            self.hardfault.address,
            *({self.svcall.vector.address} if self.svcall is not None else set()),
            *({self.pendsv.vector.address} if self.pendsv is not None else set()),
            *({self.systick.vector.address} if self.systick is not None else set()),
            *({interrupt.vector_with_priority_group.vector.address for interrupt in self.interrupts.inner}),
        }
