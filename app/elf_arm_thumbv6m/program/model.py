from collections.abc import Collection, Mapping, Set
from dataclasses import dataclass
from functools import cached_property

from more_itertools import all_unique, is_sorted

from ..common import Address


@dataclass(frozen=True, kw_only=True)
class Function:
    address: Address
    names: Set[str]

    stack_grow: int  # own
    stack_grow_cumulative: int  # own + max(calls)

    call_addresses: Set[Address]

    def __post_init__(self) -> None:
        # must be positive
        assert self.address >= 0

        # must be aligned
        assert self.address % 2 == 0

        # must have at least one name
        assert self.names

        # stack grow must be positive
        assert self.stack_grow >= 0

        # stack must be word-aligned
        assert self.stack_grow % 4 == 0

        # cumulative stack grow must be at least equal to our stack grow
        assert self.stack_grow_cumulative >= self.stack_grow

        # cumulative stack grow must be aligned
        assert self.stack_grow_cumulative % 4 == 0

        # call addresses (if any) must be aligned
        assert all(call_address % 2 == 0 for call_address in self.call_addresses)


@dataclass(frozen=True)
class Functions:
    inner: Collection[Function]

    def __post_init__(self) -> None:
        # must be sorted
        assert is_sorted(
            (function.address for function in self.inner),
            strict=True,
        )

        # names must be unique
        assert all_unique(name for function in self.inner for name in function.names)

        # call addresses must point to valid functions
        assert {
            call_address for function in self.inner for call_address in function.call_addresses
        } <= self.by_address.keys()

        # calls must not cycle
        # NOTE: this is somehow guaranteed by existence of cumulative stack size

    @cached_property
    def by_address(self) -> Mapping[Address, Function]:
        return {function.address: function for function in self.inner}


@dataclass(frozen=True, kw_only=True)
class Entrypoint:
    address: Address
    name: str

    # aligned to 8-byte boundary
    # including 8x4-byte for exceptions (B1.5.6 Exception entry behavior)
    stack_grow: int

    def __post_init__(self) -> None:
        # must be positive
        assert self.address >= 0

        # must be aligned
        assert self.address % 2 == 0

        # stack grow must be positive
        assert self.stack_grow >= 0

        # stack must be 8-byte aligned
        assert self.stack_grow % 8 == 0


@dataclass(frozen=True, kw_only=True)
class EntrypointsPriorityGroup:
    entrypoints: Collection[Entrypoint]
    name: str

    # worst-case scenario for this group
    stack_grow: int

    def __post_init__(self) -> None:
        # group must have at least one entrypoint
        assert self.entrypoints

        # stack grow must be positive
        assert self.stack_grow >= 0

        # stack must be 8-byte aligned
        assert self.stack_grow % 8 == 0


@dataclass(frozen=True, kw_only=True)
class Entrypoints:
    priority_groups: Collection[EntrypointsPriorityGroup]

    # whole program worst-case scenario
    stack_size: int

    def __post_init__(self) -> None:
        # there must be at least one priority group
        assert self.priority_groups

        # stack grow must be positive
        assert self.stack_size >= 0

        # stack must be 8-byte aligned
        assert self.stack_size % 8 == 0


@dataclass(frozen=True, kw_only=True)
class Program:
    functions: Functions
    entrypoints: Entrypoints

    def __post_init__(self) -> None:
        # all entrypoints must point to valid functions
        assert {
            entrypoint.address
            for priority_group in self.entrypoints.priority_groups
            for entrypoint in priority_group.entrypoints
        } <= self.functions.by_address.keys()

    @property
    def stack_size(self) -> int:
        return self.entrypoints.stack_size
