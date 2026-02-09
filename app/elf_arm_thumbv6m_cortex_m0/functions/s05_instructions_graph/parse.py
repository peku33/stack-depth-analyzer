from collections.abc import Mapping, Set
from typing import cast

from ...common import Address
from ..s04_instructions_effect import model as parent
from .model import Function, FunctionInstruction, FunctionInstructions, Functions


def parse(parent_functions: parent.Functions) -> Functions:
    function_returns_by_address = {function.address: function.returns for function in parent_functions.inner}

    functions = [
        parse_function(
            function,
            function_returns_by_address=function_returns_by_address,
        )
        for function in parent_functions.inner
    ]

    return Functions(functions)


def parse_function(
    parent_function: parent.Function,
    *,
    function_returns_by_address: Mapping[Address, bool],  # {address: returns}
) -> Function:
    function_instructions = parse_function_instructions(
        parent_function.instructions,
        function_returns_by_address=function_returns_by_address,
    )

    return Function(
        address=parent_function.address,
        size=parent_function.size,
        names=parent_function.names,
        instructions=function_instructions,
    )


def parse_function_instructions(
    parent_function_instructions: parent.FunctionInstructions,
    *,
    function_returns_by_address: Mapping[Address, bool],  # {address: returns}
) -> FunctionInstructions:
    # since some functions may be unreachable on purpose (eg. padding functions?), we traverse the function by following
    # instructions from first
    function_offsets_queue = set[Address]()
    function_offsets_closed = set[Address]()

    # add starting instruction to the open set
    # existence validated by model
    function_offsets_queue.add(0)

    function_instructions = list[FunctionInstruction]()
    while function_offsets_queue:
        # remove from open set, add to closed set
        function_offset = function_offsets_queue.pop()
        function_offsets_closed.add(function_offset)

        # find the instruction at given offset. its existence should be guaranteed - we have parent model checks that
        # all branches ends on valid instructions
        parent_function_instruction = parent_function_instructions.by_function_offset[function_offset]

        # handle the instruction
        function_instruction = parse_function_instruction(
            parent_function_instruction,
            function_returns_by_address=function_returns_by_address,
        )
        function_instructions.append(function_instruction)

        # add unvisited nodes to the queue if function does not return
        # skip already visited nodes
        if function_instruction.function_offsets_next is not None:
            function_offsets_queue.update(function_instruction.function_offsets_next - function_offsets_closed)

    # sort function_instructions
    function_instructions.sort(
        key=lambda function_instruction: function_instruction.function_offset,
    )

    # NOTE: some functions (especially padding functions) may be unreachable. they will not be traversed, they will be
    # missing from function_offsets_closed.

    return FunctionInstructions(function_instructions)


def parse_function_instruction(
    parent_function_instruction: parent.FunctionInstruction,
    *,
    function_returns_by_address: Mapping[Address, bool],  # {address: returns}
) -> FunctionInstruction:
    function_offsets_next: Set[Address] | None  # None here means that the function returns
    call_addresses: Set[Address]
    match parent_function_instruction.program_counter_effect:
        case parent.FunctionInstructionProgramCounterEffectFlow(
            function_offsets=function_offsets,
        ):
            # None here means that we fall out of usable program space
            # in this case we consider this function to be invalid
            if None in function_offsets:
                raise ValueError(
                    f"Instruction {parent_function_instruction}, reachable by the call graph, "
                    "falls out of function boundary."
                )

            # all offsets are valid, add them as edges
            function_offsets_next = cast(Set[Address], function_offsets)

            # there are no calls from this instruction
            call_addresses = set[Address]()
        case parent.FunctionInstructionProgramCounterEffectCall(
            addresses=addresses,
            return_function_offset=return_function_offset,
        ):
            # resolve call targets, add information whether it returns
            call_function_returns_by_address = {
                address: function_returns_by_address[address] for address in addresses for address in addresses
            }

            # check if any of call targets returns
            # we have generally checked this in the model, but here we can also discard unreachable instructions
            # NOTE: this will require update if we support tail call optimization
            if any(call_function_returns_by_address.values()):
                if return_function_offset is None:
                    raise ValueError(
                        f"Instruction {parent_function_instruction} calls functions that returns, "
                        "but return falls out of function boundary."
                    )
                function_offsets_next = {return_function_offset}
            else:
                # function does not return, so we don't flow into next instruction
                function_offsets_next = set[Address]()

            call_addresses = call_function_returns_by_address.keys()
        case parent.FunctionInstructionProgramCounterEffectReturn():
            # function returns, so we mark it this way
            function_offsets_next = None
            call_addresses = set[Address]()
        case _:
            assert False

    return FunctionInstruction(
        function_offset=parent_function_instruction.function_offset,
        instruction=parent_function_instruction.instruction,
        function_offsets_next=function_offsets_next,
        call_addresses=call_addresses,
        stack_grow=parent_function_instruction.stack_grow,
    )
