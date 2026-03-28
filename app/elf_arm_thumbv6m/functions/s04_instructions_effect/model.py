from collections.abc import Collection, Mapping, Set
from dataclasses import dataclass
from functools import cached_property
from itertools import pairwise

from more_itertools import all_unique, first, is_sorted, last

from ...common import Address
from ...instructions_decoder.model import Instruction


@dataclass(frozen=True, kw_only=True)
class FunctionInstructionProgramCounterEffectFlow:
    # None here means an invalid instruction. at this point they may exist (eg. mov r8, r8 used as last instruction for
    # padding, but control will never reach it).
    function_offsets: Set[Address | None]

    def __post_init__(self) -> None:
        # function_offsets may be empty for terminal instructions, eg. UDF

        # must be aligned
        assert all(function_offset % 2 == 0 for function_offset in self.function_offsets if function_offset is not None)


@dataclass(frozen=True, kw_only=True)
class FunctionInstructionProgramCounterEffectCall:
    addresses: Set[Address]  # different options to call
    return_function_offset: Address | None  # None means that a return will flow outside program space

    def __post_init__(self) -> None:
        # must call at least one target
        assert self.addresses

        # addresses must be aligned
        assert all(address % 2 == 0 for address in self.addresses)

        # return address must be aligned if exits
        assert self.return_function_offset is None or self.return_function_offset % 2 == 0


@dataclass(frozen=True, kw_only=True)
class FunctionInstructionProgramCounterEffectReturn:
    pass


type FunctionInstructionProgramCounterEffect = (
    FunctionInstructionProgramCounterEffectFlow
    | FunctionInstructionProgramCounterEffectCall
    | FunctionInstructionProgramCounterEffectReturn
)


@dataclass(frozen=True, kw_only=True)
class FunctionInstruction:
    function_offset: Address
    instruction: Instruction

    program_counter_effect: FunctionInstructionProgramCounterEffect
    stack_grow: int

    def __post_init__(self) -> None:
        # must be in the function
        assert self.function_offset >= 0

        # must be halfword aligned
        assert self.function_offset % 2 == 0


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

        # flow offsets must point to valid instructions
        assert {
            function_offset
            for instruction in self.inner
            if type(instruction.program_counter_effect) is FunctionInstructionProgramCounterEffectFlow
            for function_offset in instruction.program_counter_effect.function_offsets
            if function_offset is not None
        } <= self.by_function_offset.keys()

    @cached_property
    def by_function_offset(self) -> Mapping[Address, FunctionInstruction]:
        return {instruction.function_offset: instruction for instruction in self.inner}


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
        return {
            call_address
            for instruction in self.instructions.inner
            if type(instruction.program_counter_effect) is FunctionInstructionProgramCounterEffectCall
            for call_address in instruction.program_counter_effect.addresses
        }

    @cached_property
    def returns(self) -> bool:
        return any(
            type(instruction.program_counter_effect) is FunctionInstructionProgramCounterEffectReturn
            for instruction in self.instructions.inner
        )


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

        # callees must not return if caller has valid return instruction
        assert not any(
            self.by_address[call_address].returns
            for function in self.inner
            for instruction in function.instructions.inner
            if type(instruction.program_counter_effect) is FunctionInstructionProgramCounterEffectCall
            if instruction.program_counter_effect.return_function_offset is None  # only consider calls that cant return
            for call_address in instruction.program_counter_effect.addresses  # check all call targets
        )

    @cached_property
    def by_address(self) -> Mapping[Address, Function]:
        return {function.address: function for function in self.inner}
