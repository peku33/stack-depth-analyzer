from collections.abc import Collection, Set
from dataclasses import dataclass
from functools import cached_property
from itertools import pairwise

from more_itertools import all_unique, is_sorted, last, mark_ends

from ...common import Address


@dataclass(frozen=True, kw_only=True)
class FunctionRegion:
    function_offset: Address
    size: int
    code_data: bool  # True - code, False - data

    def __post_init__(self) -> None:
        # must start after the function start
        assert self.function_offset >= 0

        # must not be empty
        assert self.size > 0


@dataclass(frozen=True)
class FunctionRegions:
    inner: Collection[FunctionRegion]

    def __post_init__(self) -> None:
        # must contain at least one region
        assert self.inner

        # regions must start at 0 and be consecutive
        function_offset = 0
        for is_first, _is_last, region in mark_ends(self.inner):
            # first region must be a code region
            assert not is_first or region.code_data

            # regions must be contiguous and non-overlapping
            assert region.function_offset == function_offset
            function_offset = region.function_offset + region.size

    @cached_property
    def size(self) -> int:
        last_ = last(self.inner)
        return last_.function_offset + last_.size


@dataclass(frozen=True, kw_only=True)
class Function:
    address: Address
    size: int

    names: Set[str]

    regions: FunctionRegions

    def __post_init__(self) -> None:
        # must be positive
        assert self.address >= 0

        # must be aligned
        assert self.address % 2 == 0

        # must not be empty
        assert self.size > 0

        # must have at least one name
        assert self.names

        # regions must cover whole function
        assert self.regions.size == self.size


@dataclass(frozen=True)
class Functions:
    inner: Collection[Function]

    def __post_init__(self) -> None:
        # must be sorted
        assert is_sorted(function.address for function in self.inner)

        # must not overlap
        assert all(
            function.address + function.size <= function_next.address
            for function, function_next in pairwise(self.inner)
        )

        # names must be unique
        assert all_unique(name for function in self.inner for name in function.names)
