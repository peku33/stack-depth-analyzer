from collections.abc import Collection, Set
from dataclasses import dataclass
from functools import cached_property

from ..common import Address


@dataclass(frozen=True, kw_only=True)
class Entrypoint:
    address: Address
    name: str

    def __post_init__(self) -> None:
        # must be positive
        assert self.address >= 0

        # must be aligned
        assert self.address % 2 == 0


@dataclass(frozen=True, kw_only=True)
class EntrypointsExceptionPriorityGroup:
    entrypoints: Collection[Entrypoint]
    name: str

    def __post_init__(self) -> None:
        # group must have at least one entrypoint
        assert self.entrypoints


@dataclass(frozen=True, kw_only=True)
class Entrypoints:
    main: Entrypoint
    exception_priority_groups: Collection[EntrypointsExceptionPriorityGroup]

    @cached_property
    def addresses(self) -> Set[Address]:
        return {
            self.main.address,
            *(
                entrypoint.address
                for exception_priority_group in self.exception_priority_groups
                for entrypoint in exception_priority_group.entrypoints
            ),
        }
