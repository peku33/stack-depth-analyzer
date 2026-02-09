from collections.abc import Collection, Mapping, Set
from dataclasses import dataclass
from functools import cached_property
from itertools import pairwise

from more_itertools import all_unique, first, is_sorted, last

from ...common import Address
from ...instructions_decoder.model import Instruction


@dataclass(frozen=True, kw_only=True)
class FunctionInstruction:
    function_offset: Address
    instruction: Instruction

    # None in function_offsets_next signifies returning.
    # empty allowed for terminal instructions, eg. UDF
    function_offsets_next: Set[Address] | None
    call_addresses: Set[Address]

    stack_grow: int

    def __post_init__(self) -> None:
        # must be in the function
        assert self.function_offset >= 0

        # must be halfword aligned
        assert self.function_offset % 2 == 0

        # next offsets must be aligned
        assert self.function_offsets_next is None or all(
            function_offset_next % 2 == 0 for function_offset_next in self.function_offsets_next
        )

        # call addresses (if any) must be aligned
        assert all(call_address % 2 == 0 for call_address in self.call_addresses)


@dataclass(frozen=True)
class FunctionInstructions:
    inner: Collection[FunctionInstruction]

    def __post_init__(self) -> None:
        # must contain at least one instruction
        assert self.inner

        # must be ordered
        assert is_sorted(
            (instruction.function_offset for instruction in self.inner),
            strict=True,
        )

        # first instruction must be at offset 0
        assert first(self.inner).function_offset == 0

        # must no overlap
        assert all(
            instruction.function_offset + instruction.instruction.size() <= instruction_next.function_offset
            for instruction, instruction_next in pairwise(self.inner)
        )

        # edges offsets must point to valid instructions
        assert {
            function_offset_next
            for instruction in self.inner
            if instruction.function_offsets_next is not None
            for function_offset_next in instruction.function_offsets_next
        } <= self.by_function_offset.keys()

    @cached_property
    def by_function_offset(self) -> Mapping[Address, FunctionInstruction]:
        return {instruction.function_offset: instruction for instruction in self.inner}

    @cached_property
    def function_offsets_next(self) -> Mapping[Address, Set[Address]]:
        # will not contain functions with no next

        return {
            instruction.function_offset: instruction.function_offsets_next
            for instruction in self.inner
            if instruction.function_offsets_next is not None and instruction.function_offsets_next
        }

    @cached_property
    def function_offsets_previous(self) -> Mapping[Address, Set[Address]]:
        # will not contain functions with no previous

        function_offsets_previous = dict[Address, set[Address]]()

        for function_offset, function_offsets_next in self.function_offsets_next.items():
            for function_offset_next in function_offsets_next:
                function_offsets_previous.setdefault(function_offset_next, set()).add(function_offset)

        return function_offsets_previous


@dataclass(frozen=True, kw_only=True)
class Function:
    address: Address
    size: int

    names: Set[str]

    instructions: FunctionInstructions

    def __post_init__(self) -> None:
        # must be positive
        assert self.address >= 0

        # must be aligned
        assert self.address % 2 == 0

        # must not be empty
        assert self.size > 0

        # must have at least one name
        assert self.names

        # all instructions must fit in function size
        instruction_last = last(self.instructions.inner)
        assert instruction_last.function_offset + instruction_last.instruction.size() <= self.size

    @cached_property
    def call_addresses(self) -> Set[Address]:
        return {call_address for instruction in self.instructions.inner for call_address in instruction.call_addresses}

    @cached_property
    def returns(self) -> bool:
        return any(instruction.function_offsets_next is None for instruction in self.instructions.inner)


@dataclass(frozen=True)
class Functions:
    inner: Collection[Function]

    def __post_init__(self) -> None:
        # must be sorted
        assert is_sorted(
            (function.address for function in self.inner),
            strict=True,
        )

        # must not overlap
        assert all(
            function.address + function.size <= function_next.address
            for function, function_next in pairwise(self.inner)
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
