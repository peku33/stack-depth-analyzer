from collections.abc import Mapping, Set
from logging import getLogger
from math import ceil

from ..common import Address, function_like_format
from ..entrypoints import model as parent_entrypoints
from ..functions import model as parent_functions
from .model import Entrypoint, Entrypoints, EntrypointsPriorityGroup, Function, Functions, Program

_logger = getLogger(__name__)


def parse(
    parent_functions_: parent_functions.Functions, parent_entrypoints_: parent_entrypoints.Entrypoints
) -> Program:
    # warn for orphaned functions
    warn_functions_unreachable(parent_functions_, parent_entrypoints_.addresses)

    # resolve functions
    functions = parse_functions(parent_functions_)

    # resolve entrypoints
    entrypoints = parse_entrypoints(parent_entrypoints_, functions)

    return Program(
        functions=functions,
        entrypoints=entrypoints,
    )


def warn_functions_unreachable(
    parent_functions_: parent_functions.Functions, entrypoints_addresses: Set[Address]
) -> None:
    # start with all functions
    function_addresses_not_called = {function.address for function in parent_functions_.inner}

    # remove called
    for function in parent_functions_.inner:
        function_addresses_not_called -= function.call_addresses

    # remove pointed by entrypoints
    function_addresses_not_called -= entrypoints_addresses

    # we should be left with not called
    for function_address_not_called in function_addresses_not_called:
        _logger.warning(
            "Function %s has no calls. Make sure entrypoints are properly configured.",
            function_like_format(parent_functions_.by_address[function_address_not_called]),
        )


def parse_functions(parent_functions_: parent_functions.Functions) -> Functions:
    # calculate cumulative function stack usages
    stack_grow_cumulative_by_function_address = resolve_stack_grow_cumulative_by_function_address(parent_functions_)

    # build new functions
    functions_ = [
        Function(
            address=parent_function.address,
            names=parent_function.names,
            stack_grow=parent_function.stack_grow,
            stack_grow_cumulative=stack_grow_cumulative_by_function_address[parent_function.address],
            call_addresses=parent_function.call_addresses,
        )
        for parent_function in parent_functions_.inner
    ]

    return Functions(functions_)


def resolve_stack_grow_cumulative_by_function_address(
    parent_functions_: parent_functions.Functions,
) -> Mapping[Address, int]:
    stack_grow_cumulative_by_function_address = dict[Address, int]()

    while True:
        changed = False

        # not yet resolved
        functions_unresolved = [
            function
            for function in parent_functions_.inner
            if function.address not in stack_grow_cumulative_by_function_address
        ]

        # try each unresolved function
        for function in functions_unresolved:
            # if all callees are not resolved - skip for now
            if not function.call_addresses <= stack_grow_cumulative_by_function_address.keys():
                continue

            # all our calls are resolved, so we can resolve ourselves

            # our cumulative stack grow is our stack grow + stack grow of the biggest call
            stack_grow_cumulative = function.stack_grow + max(
                (stack_grow_cumulative_by_function_address[call_address] for call_address in function.call_addresses),
                default=0,
            )

            # store information that we have resolved ourselves
            stack_grow_cumulative_by_function_address[function.address] = stack_grow_cumulative
            changed = True

        if not changed:
            break

    # all functions must be resolved
    # if they are not - it means there is a cycle in the graph
    function_addresses_unresolved = (
        parent_functions_.by_address.keys() - stack_grow_cumulative_by_function_address.keys()
    )
    if function_addresses_unresolved:
        raise ValueError(
            "Unable to resolve functions cumulative stack usage. "
            "This usually mean there is a cycle in call graph (ex. recursion). "
            f"Functions affected: {", ".join(
                function_like_format(parent_functions_.by_address[function_address_unresolved])
                for function_address_unresolved in function_addresses_unresolved)
            }"
        )

    return stack_grow_cumulative_by_function_address


def parse_entrypoints(parent_entrypoints_: parent_entrypoints.Entrypoints, functions: Functions) -> Entrypoints:
    entrypoints_priority_groups = [
        resolve_entrypoints_main(parent_entrypoints_.main, functions),
    ] + [
        parse_entrypoints_exceptions_priority_group(entrypoints_exception_priority_group, functions)
        for entrypoints_exception_priority_group in parent_entrypoints_.exception_priority_groups
    ]

    # whole program stack is sum of all concurrent entrypoint stacks
    stack_size = sum(
        entrypoints_priority_group.stack_grow for entrypoints_priority_group in entrypoints_priority_groups
    )

    return Entrypoints(
        priority_groups=entrypoints_priority_groups,
        stack_size=stack_size,
    )


def resolve_entrypoints_main(main: parent_entrypoints.Entrypoint, functions: Functions) -> EntrypointsPriorityGroup:
    entrypoint = parse_entrypoint(main, functions, False)

    return EntrypointsPriorityGroup(
        entrypoints=[entrypoint],
        name=entrypoint.name,
        stack_grow=entrypoint.stack_grow,
    )


def parse_entrypoints_exceptions_priority_group(
    entrypoints_exception_priority_group: parent_entrypoints.EntrypointsExceptionPriorityGroup, functions: Functions
) -> EntrypointsPriorityGroup:
    entrypoints = [
        parse_entrypoint(entrypoint, functions, True) for entrypoint in entrypoints_exception_priority_group.entrypoints
    ]

    stack_grow = max(entrypoint.stack_grow for entrypoint in entrypoints)

    return EntrypointsPriorityGroup(
        entrypoints=entrypoints,
        name=entrypoints_exception_priority_group.name,
        stack_grow=stack_grow,
    )


def parse_entrypoint(entrypoint: parent_entrypoints.Entrypoint, functions: Functions, is_exception: bool) -> Entrypoint:
    function = functions.by_address.get(entrypoint.address)
    if function is None:
        raise ValueError(f"Unable to find function at address 0x{entrypoint.address:04X} pointed by entrypoint vector.")

    # stack usage is cumulative stack usage by this point
    # - with 8x4 byte stack save for exceptions
    # - aligned to 8-byte boundary
    stack_grow = function.stack_grow_cumulative
    if is_exception:
        stack_grow += 8 * 4
    stack_grow = ceil(stack_grow / 8) * 8

    return Entrypoint(
        address=function.address,
        name=entrypoint.name,
        stack_grow=stack_grow,
    )
