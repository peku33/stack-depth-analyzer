from collections.abc import Set

from ...common import Address
from ..s05_instructions_graph import model as parent
from .model import Function, Functions


def parse(parent_functions: parent.Functions) -> Functions:
    functions = [parse_function(function) for function in parent_functions.inner]

    return Functions(functions)


def parse_function(parent_function: parent.Function) -> Function:
    stack_grow = resolve_function_stack_grow(parent_function)

    return Function(
        address=parent_function.address,
        names=parent_function.names,
        stack_grow=stack_grow,
        call_addresses=parent_function.call_addresses,
    )


def resolve_function_stack_grow(parent_function: parent.Function) -> int:
    # get function offsets of all instructions affecting the stack
    # we will later check if our entry -> + <- return searches found all of them
    function_offsets_stack_grow_all = {
        instruction.function_offset for instruction in parent_function.instructions.inner if instruction.stack_grow != 0
    }
    function_offsets_traversed = set[Address]()

    # entry
    stack_grow_entry, function_offsets_entry = resolve_function_stack_grow_function_offsets_entry(parent_function)
    function_offsets_traversed.update(function_offsets_entry)

    # returns (multiple)
    stack_grow_function_offsets_returns = resolve_function_stack_grow_function_offsets_returns(parent_function)

    # if a function returns, at least one return path must be resolved
    assert (stack_grow_function_offsets_returns is None) == (not parent_function.returns)

    if stack_grow_function_offsets_returns is not None:
        stack_grow_return, function_offsets_returns = stack_grow_function_offsets_returns
        function_offsets_traversed.update(function_offsets_returns)

        if stack_grow_entry != -stack_grow_return:
            raise ValueError(
                "Function stack size is not returned to zero? "
                f"Entry stack size grow ({stack_grow_entry}) does not match return stack shrink ({-stack_grow_return})?"
            )

    # check if we found all stack affecting instructions
    if not function_offsets_traversed >= function_offsets_stack_grow_all:
        raise ValueError(
            "Unable to reach all instructions affecting stack using entry-return method. "
            "This usually means that function isn't easily analyzable, "
            "eg. contains stack pointer affecting instructions between branches/calls."
        )

    # stack must be word-aligned
    if stack_grow_entry % 4 != 0:
        raise ValueError("Function stack usage is not aligned to word boundary?")

    return stack_grow_entry


def resolve_function_stack_grow_function_offsets_entry(parent_function: parent.Function) -> tuple[int, Set[Address]]:
    # from entry point

    stack_grow = 0
    function_offsets = set[Address]()

    function_offset = 0  # start with function entry
    while True:
        # make sure that we are not in a cycle
        function_offsets_previous = parent_function.instructions.function_offsets_previous.get(function_offset, set())
        if function_offset == 0:
            # first instruction may not have any incoming edge
            if len(function_offsets_previous) != 0:
                break
        else:
            # non-first instructions may only have one incoming edge
            if len(function_offsets_previous) != 1:
                break

        function_instruction = parent_function.instructions.by_function_offset[function_offset]

        # stop iterating if function makes a call
        if function_instruction.call_addresses:
            break

        # stop iterating if function shrinks the stack (may happen only on return side)
        if function_instruction.stack_grow < 0:
            break

        # mark stack grow
        stack_grow += function_instruction.stack_grow

        # add this function to visited. since we stop at branches, we shouldn't be able to reach the same address
        assert function_offset not in function_offsets
        function_offsets.add(function_offset)

        # go to next node if there is exactly one, otherwise stop iterating
        match list(parent_function.instructions.function_offsets_next.get(function_offset, set())):
            case [function_offset_next]:
                pass
            case _:
                break

        function_offset = function_offset_next

    return stack_grow, function_offsets


def resolve_function_stack_grow_function_offsets_returns(
    parent_function: parent.Function,
) -> tuple[int, Set[Address]] | None:
    # there could be multiple return points from this function
    # they should make exactly same effect (with different nodes involved)
    def resolve_function_stack_grow_function_offsets_return(
        function_offset_return: Address,
    ) -> tuple[int, Set[Address]]:
        stack_grow = 0
        function_offsets = set[Address]()

        function_offset = function_offset_return
        while True:
            function_offsets_next = parent_function.instructions.function_offsets_next.get(function_offset, set())
            if function_offset == function_offset_return:
                # last instruction may not have any outgoing edges
                if len(function_offsets_next) != 0:
                    break
            else:
                # non-last instruction may have only one outgoing edge
                if len(function_offsets_next) != 1:
                    break

            function_instruction = parent_function.instructions.by_function_offset[function_offset]

            # stop iterating if function makes a call
            if function_instruction.call_addresses:
                break

            # stop iterating if function grows the stack (may happen only on entry side)
            if function_instruction.stack_grow > 0:
                break

            # mark stack grow
            stack_grow += function_instruction.stack_grow

            # add this function to visited. since we stop at branches, we shouldn't be able to reach the same address
            assert function_offset not in function_offsets
            function_offsets.add(function_offset)

            # go back to previous node if there is exactly one, otherwise stop iterating
            match list(parent_function.instructions.function_offsets_previous.get(function_offset, set())):
                case [function_offset_previous]:
                    pass
                case _:
                    break

            function_offset = function_offset_previous

        return stack_grow, function_offsets

    # resolve stack grow starting from each return instruction
    function_offsets_return_stack_grow_function_offsets = {  # {return function offset: (stack grow, function offsets)}
        function_instruction.function_offset: resolve_function_stack_grow_function_offsets_return(
            function_instruction.function_offset
        )
        for function_instruction in parent_function.instructions.inner
        if function_instruction.function_offsets_next is None  # only returning instructions
    }

    if not function_offsets_return_stack_grow_function_offsets:
        # function has no return, so we don't care about the stack size
        return None

    # all return paths should have the same stack grow size
    stack_grows = list({stack_grow for stack_grow, _ in function_offsets_return_stack_grow_function_offsets.values()})
    match stack_grows:
        case [stack_grow]:
            pass
        case _:
            # 0 items not possible, checked earlier
            # there must be multiple paths with differing stack grow
            raise ValueError(
                "Different return paths results in differing stack sizes: "
                f"({", ".join(str(stack_grow for stack_grow in stack_grows))})."
            )

    # resolve all involved function_offsets
    function_offsets = set[Address]()
    for _, function_offsets_ in function_offsets_return_stack_grow_function_offsets.values():
        # paths may not have common nodes
        # this is guaranteed by iteration stop on first node with two sources
        assert function_offsets_.isdisjoint(function_offsets)

        # add to the combined set
        function_offsets.update(function_offsets_)

    return stack_grow, function_offsets
