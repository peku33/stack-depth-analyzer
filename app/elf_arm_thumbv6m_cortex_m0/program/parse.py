from collections.abc import Collection, Mapping
from itertools import chain, islice
from logging import getLogger
from math import ceil

from ..common import Address, function_like_format
from ..entrypoints import model as parent_entrypoints
from ..entrypoints.common import PRIORITY_GROUPS
from ..functions import model as parent_functions
from .model import Entrypoint, Entrypoints, EntrypointsPriorityGroup, Function, Functions, Program

_logger = getLogger(__name__)


def parse(
    parent_functions_: parent_functions.Functions, parent_entrypoints_: parent_entrypoints.Entrypoints
) -> Program:
    # warn for orphaned functions
    warn_functions_unreachable(parent_functions_, parent_entrypoints_)

    # resolve functions
    functions = parse_functions(parent_functions_)

    # resolve entrypoints
    entrypoints = parse_entrypoints(parent_entrypoints_, functions)

    return Program(
        functions=functions,
        entrypoints=entrypoints,
    )


def warn_functions_unreachable(
    parent_functions_: parent_functions.Functions, parent_entrypoints_: parent_entrypoints.Entrypoints
) -> None:
    # start with all functions
    function_addresses_not_called = {function.address for function in parent_functions_.inner}

    # remove called
    for function in parent_functions_.inner:
        function_addresses_not_called -= function.call_addresses

    # remove pointed by entrypoints
    function_addresses_not_called -= parent_entrypoints_.addresses

    # we should be left with not called
    for function_address_not_called in function_addresses_not_called:
        _logger.warning(
            "Function %s has no calls. Make sure entrypoints are properly configured.",
            function_like_format(parent_functions_.by_address[function_address_not_called]),
        )


def parse_functions(parent_functions_: parent_functions.Functions) -> Functions:
    # calculate cumulative function stack usages
    stack_grow_cumulative_by_function_address = parse_stack_grow_cumulative_by_function_address(parent_functions_)

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


def parse_stack_grow_cumulative_by_function_address(
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
    entrypoints_priority_groups = list[EntrypointsPriorityGroup]()

    # group A
    # reset, hardfault, nmi have individual priorities
    def resolve_entrypoints_priority_group_from_exception(
        entrypoint_vector: parent_entrypoints.EntrypointVector, name: str, is_exception: bool
    ) -> EntrypointsPriorityGroup:
        # build single-item priority group from exception (with unconfigurable priority, like HardFault)
        entrypoint = resolve_entrypoint_from_entrypoint_vector(entrypoint_vector, name, is_exception, functions)

        return resolve_entrypoint_priority_group([entrypoint], name)

    # reset is not configurable
    entrypoints_priority_groups.append(
        resolve_entrypoints_priority_group_from_exception(parent_entrypoints_.reset, "Reset", False)
    )

    # nmi can be disabled, but is not configurable
    if parent_entrypoints_.nmi is not None:
        entrypoints_priority_groups.append(
            resolve_entrypoints_priority_group_from_exception(parent_entrypoints_.nmi, "NMI", True)
        )

    # hardfault is not configurable
    entrypoints_priority_groups.append(
        resolve_entrypoints_priority_group_from_exception(parent_entrypoints_.hardfault, "HardFault", True)
    )

    # group B
    # some entrypoints/interrupts may have unknown priority group, in this case we assume worst-case scenario. each
    # unknown entrypoint constitutes individual group and then we pick PRIORITY_GROUPS heaviest groups.
    # if all priority groups are known - this forwards them 1:1 in unchanged manner
    entrypoints_priority_known = dict[int, list[Entrypoint]]()
    entrypoints_priority_unknown = list[Entrypoint]()

    def handle_vector_with_priority_group(
        vector_with_priority_group: parent_entrypoints.EntrypointVectorWithPriorityGroup, name: str
    ) -> None:
        entrypoint = resolve_entrypoint_from_entrypoint_vector(vector_with_priority_group.vector, name, True, functions)

        if vector_with_priority_group.priority_group is not None:
            entrypoints_priority_known.setdefault(vector_with_priority_group.priority_group, []).append(entrypoint)
        else:
            entrypoints_priority_unknown.append(entrypoint)

    if parent_entrypoints_.svcall is not None:
        handle_vector_with_priority_group(parent_entrypoints_.svcall, "SVCall")
    if parent_entrypoints_.pendsv is not None:
        handle_vector_with_priority_group(parent_entrypoints_.pendsv, "PendSV")
    if parent_entrypoints_.systick is not None:
        handle_vector_with_priority_group(parent_entrypoints_.systick, "SysTick")

    for interrupt in parent_entrypoints_.interrupts.inner:
        handle_vector_with_priority_group(interrupt.vector_with_priority_group, interrupt.name)

    # now use heaviest PRIORITY_GROUPS
    entrypoints_priority_groups.extend(
        islice(  # take only PRIORITY_GROUPS heaviest
            sorted(  # sorted by stack usage, descending
                chain(  # from combined known and unknown priorities
                    (  # known priorities are grouped by priority
                        resolve_entrypoint_priority_group(entrypoints, f"Priority Group #{priority_group}")
                        for priority_group, entrypoints in entrypoints_priority_known.items()
                    ),
                    (  # unknown form individual groups
                        resolve_entrypoint_priority_group([entrypoint], "Unknown priority group")
                        for entrypoint in entrypoints_priority_unknown
                    ),
                ),
                key=lambda priority_group: priority_group.stack_grow,
                reverse=True,  # from heaviest
            ),
            PRIORITY_GROUPS,
        )
    )

    # whole program stack is sum of all concurrent entrypoint stacks
    stack_size = sum(
        entrypoints_priority_group.stack_grow for entrypoints_priority_group in entrypoints_priority_groups
    )

    return Entrypoints(
        priority_groups=entrypoints_priority_groups,
        stack_size=stack_size,
    )


def resolve_entrypoint_from_entrypoint_vector(
    entrypoint_vector: parent_entrypoints.EntrypointVector, name: str, is_exception: bool, functions: Functions
) -> Entrypoint:
    function = functions.by_address.get(entrypoint_vector.address)
    if function is None:
        raise ValueError(
            f"Unable to find function at address 0x{entrypoint_vector.address:04X} pointed by entrypoint vector."
        )

    # stack usage is cumulative stack usage by this point
    # - with 8x4 byte stack save for exceptions
    # - aligned to 8-byte boundary
    stack_grow = function.stack_grow_cumulative
    if is_exception:
        stack_grow += 8 * 4
    stack_grow = ceil(stack_grow / 8) * 8

    return Entrypoint(
        address=function.address,
        name=name,
        stack_grow=stack_grow,
    )


def resolve_entrypoint_priority_group(entrypoints: Collection[Entrypoint], name: str) -> EntrypointsPriorityGroup:
    stack_grow = max(entrypoint.stack_grow for entrypoint in entrypoints)

    return EntrypointsPriorityGroup(
        entrypoints=entrypoints,
        name=name,
        stack_grow=stack_grow,
    )
