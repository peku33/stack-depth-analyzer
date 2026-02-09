from collections.abc import Collection, Mapping, Set
from dataclasses import dataclass
from functools import cached_property

from more_itertools import all_unique, is_sorted

from ..common import Address


@dataclass(frozen=True, kw_only=True)
class Function:
    address: Address
    names: Set[str]

    stack_grow: int
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

    @cached_property
    def by_address(self) -> Mapping[Address, Function]:
        return {function.address: function for function in self.inner}

    @cached_property
    def by_name(self) -> Mapping[str, Function]:
        return {name: function for function in self.inner for name in function.names}
