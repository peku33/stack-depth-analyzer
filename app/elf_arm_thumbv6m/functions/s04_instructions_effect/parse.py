from collections.abc import Collection, Sequence, Set

from typing_extensions import Self

from ...common import Address, function_like_format
from ..s03_instructions import model as parent
from ..s03_instructions.cursor import CursorFunction, CursorFunctionRegionInstructions
from . import _program_counter_effect, _stack_pointer_effect
from .config import Config
from .model import (
    Function,
    FunctionInstruction,
    FunctionInstructionProgramCounterEffect,
    FunctionInstructionProgramCounterEffectCall,
    FunctionInstructionProgramCounterEffectFlow,
    FunctionInstructionProgramCounterEffectReturn,
    FunctionInstructions,
    Functions,
)


def parse(parent_functions: parent.Functions, config: Config) -> Functions:
    functions = list[Function]()
    exceptions = list[ParseFunctionInstructionsException]()

    for parent_function in parent_functions.inner:
        try:
            function = parse_function(parent_function, config)
        except ParseFunctionInstructionsException as exception:
            exceptions.append(exception)
        else:
            functions.append(function)

    if exceptions:
        raise ExceptionGroup("Exceptions encountered while parsing functions", exceptions)

    # perform extra validations
    validate_functions(functions)

    return Functions(functions)


def validate_functions(functions: Collection[Function]) -> None:
    functions_by_address = {function.address: function for function in functions}

    # validate if call addresses point to valid functions
    # validate if we can handle return if call target returns
    function_calls_missing = set[tuple[Address, Address]]()  # {(call instruction address, callee address)}
    function_calls_invalid_return = set[tuple[Address, Address]]()  # {(call instruction address, callee address)}
    for function in functions:
        for instruction in function.instructions.inner:
            if type(instruction.program_counter_effect) is not FunctionInstructionProgramCounterEffectCall:
                continue

            for call_address in instruction.program_counter_effect.addresses:
                call_function = functions_by_address.get(call_address)

                # mark missing calls
                if call_function is None:
                    function_calls_missing.add((function.address + instruction.function_offset, call_address))
                    continue

                # mark if function returns, but we cant handle it
                if instruction.program_counter_effect.return_function_offset is None and call_function.returns:
                    function_calls_invalid_return.add(
                        (function.address + instruction.function_offset, call_function.address)
                    )
                    continue

    if function_calls_missing:
        raise ValueError(f"Found calls to non-existing functions: {", ".join(
            f"0x{call_address_from:04X} -> 0x{call_address_to:04X}"
            for call_address_from, call_address_to in function_calls_missing
        )}")

    if function_calls_invalid_return:
        raise ValueError(f"Found impossible return address: {", ".join(
            f"0x{call_address_from:04X} -> 0x{call_address_to:04X}"
            for call_address_from, call_address_to in function_calls_invalid_return
        )}")


def parse_function(parent_function: parent.Function, config: Config) -> Function:
    cursor_function = CursorFunction(
        function=parent_function,
    )
    instructions = parse_function_instructions(cursor_function, config)

    return Function(
        address=parent_function.address,
        size=parent_function.size,
        names=parent_function.names,
        instructions=instructions,
    )


class ParseFunctionInstructionsException(ExceptionGroup):
    _function: parent.Function
    _inner: Sequence[_program_counter_effect.ResolveException | _stack_pointer_effect.ResolveException]

    def __new__(
        cls,
        function: parent.Function,
        inner: Sequence[_program_counter_effect.ResolveException | _stack_pointer_effect.ResolveException],
    ) -> Self:
        object_ = super().__new__(cls, cls._format_message(function), inner)
        object_._function = function
        object_._inner = inner
        return object_

    def __init__(
        self,
        function: parent.Function,
        inner: Sequence[_program_counter_effect.ResolveException | _stack_pointer_effect.ResolveException],
    ) -> None:
        super().__init__(self._format_message(function), inner)

        self._function = function
        self._inner = inner

    @classmethod
    def _format_message(cls, function: parent.Function) -> str:
        return f"Exceptions encountered while parsing function {function_like_format(function)}"


def parse_function_instructions(cursor_function: CursorFunction, config: Config) -> FunctionInstructions:
    instructions = list[FunctionInstruction]()
    exceptions = list[_program_counter_effect.ResolveException | _stack_pointer_effect.ResolveException]()

    for parent_function_regions_index, parent_function_region in enumerate(cursor_function.function.regions.inner):
        if type(parent_function_region) is not parent.FunctionRegionInstructions:
            continue

        for parent_function_region_instructions_index in range(len(parent_function_region.instructions)):
            cursor_function_region_instructions = CursorFunctionRegionInstructions(
                cursor_function=cursor_function,
                function_regions_index=parent_function_regions_index,
                function_region_instructions_index=parent_function_region_instructions_index,
            )

            try:
                instruction_ = parse_function_instruction(cursor_function_region_instructions, config)
            except (_program_counter_effect.ResolveException, _stack_pointer_effect.ResolveException) as exception:
                exceptions.append(exception)
            else:
                instructions.append(instruction_)

    if exceptions:
        raise ParseFunctionInstructionsException(
            cursor_function.function, exceptions  # pyright: ignore[reportArgumentType]
        )

    # extra validations
    validate_function_instructions(instructions)

    # we are good to go
    return FunctionInstructions(instructions)


def validate_function_instructions(instructions: Collection[FunctionInstruction]) -> None:
    # all valid function offsets
    function_offsets = {instruction.function_offset for instruction in instructions}

    # validate if all flow targets point to a valid instructions
    flow_function_offsets_invalid = dict[Address, Set[Address]]()  # {function_offset: {function_offset_invalid}}

    for instruction in instructions:
        if type(instruction.program_counter_effect) is not FunctionInstructionProgramCounterEffectFlow:
            continue

        flow_function_offsets_invalid_ = {
            function_offset
            for function_offset in instruction.program_counter_effect.function_offsets
            if function_offset is not None and function_offset not in function_offsets
        }
        if flow_function_offsets_invalid_:
            flow_function_offsets_invalid[instruction.function_offset] = flow_function_offsets_invalid_

    if flow_function_offsets_invalid:
        raise ValueError(
            f"Found instruction flow / branch (not call) reaching instruction out of function boundaries: {", ".join(
                f"+{function_offset_from} -> {", ".join(
                    f"+{function_offset_to}" for function_offset_to in function_offsets_to)
                }"
                for function_offset_from, function_offsets_to in flow_function_offsets_invalid.items()
            )}"
        )


def parse_function_instruction(
    cursor_function_region_instructions: CursorFunctionRegionInstructions, config: Config
) -> FunctionInstruction:
    function_offset = cursor_function_region_instructions.function_offset()
    instruction = cursor_function_region_instructions.instruction()

    # program counter effects
    program_counter_effect: FunctionInstructionProgramCounterEffect

    # in most situations we will simply flow to the next instruction, calculate its offset here
    # instruction can theoretically not exist, in which case we have None here
    cursor_function_region_instructions_next = cursor_function_region_instructions.next()
    flow_function_offset = (
        cursor_function_region_instructions_next.function_offset()
        if cursor_function_region_instructions_next is not None
        else None
    )

    program_counter_effect_ = _program_counter_effect.resolve(
        cursor_function_region_instructions, config.call_overrides
    )
    match program_counter_effect_:
        case _program_counter_effect.EffectBranch():
            # use branch targets as next flow targets
            # if branch is conditional, it may simply flow to next instruction if condition is not passed
            function_offsets: Set[Address | None] = {
                *program_counter_effect_.target_function_offsets,
                *({flow_function_offset} if program_counter_effect_.conditional else set()),
            }

            program_counter_effect = FunctionInstructionProgramCounterEffectFlow(
                function_offsets=function_offsets,
            )
        case _program_counter_effect.EffectCall():
            addresses = set(program_counter_effect_.target_addresses)
            program_counter_effect = FunctionInstructionProgramCounterEffectCall(
                addresses=addresses,
                return_function_offset=flow_function_offset,
            )
        case _program_counter_effect.EffectReturn():
            program_counter_effect = FunctionInstructionProgramCounterEffectReturn()
        case _program_counter_effect.EffectInvalid():
            # an invalid instruction will not continue its execution, and will put processor in the terminal state, eg.
            # UDF instruction. this is a special case in which an instruction has no successor. we denote it by flow to
            # nowhere

            function_offsets = set[Address]()
            program_counter_effect = FunctionInstructionProgramCounterEffectFlow(
                function_offsets=function_offsets,
            )
        case None:
            # standard instruction will always flow to the next instruction
            # some instructions won't have successors (for example padding instructions)
            # we will then validate if such scenarios are not reachable under standard program flow
            function_offsets = {flow_function_offset}

            program_counter_effect = FunctionInstructionProgramCounterEffectFlow(
                function_offsets=function_offsets,
            )
        case _:
            assert False

    # stack pointer effects
    stack_grow = 0

    stack_pointer_effect = _stack_pointer_effect.resolve(cursor_function_region_instructions)
    match stack_pointer_effect:
        case _stack_pointer_effect.Effect():
            # stack is descending
            stack_grow += -stack_pointer_effect.add
        case None:
            pass
        case _:
            assert False

    return FunctionInstruction(
        function_offset=function_offset,
        instruction=instruction,
        program_counter_effect=program_counter_effect,
        stack_grow=stack_grow,
    )
