from collections.abc import Collection

from more_itertools import one

from ..functions.model import Functions
from .config import Config, ConfigEntrypoint, ConfigExceptionPriorityGroup, ConfigExceptionPriorityGroups
from .model import Entrypoint, Entrypoints, EntrypointsExceptionPriorityGroup


def parse(config: Config, functions: Functions) -> Entrypoints:
    # we don't know which MCU implementation we are, so we assume everything is provided by config

    entrypoint_main = parse_entrypoint(
        config.main,
        functions,
        name_hint="Main",
    )
    entrypoints_exception_priority_groups = parse_entrypoints_exception_priority_groups(
        config.exception_priority_groups, functions
    )

    return Entrypoints(
        main=entrypoint_main,
        exception_priority_groups=entrypoints_exception_priority_groups,
    )


def parse_entrypoints_exception_priority_groups(
    config: ConfigExceptionPriorityGroups, functions: Functions
) -> Collection[EntrypointsExceptionPriorityGroup]:
    entrypoints_exception_priority_groups = [
        parse_entrypoints_exception_priority_group(
            exception_priority_groups,
            functions,
            index=index,
        )
        for index, exception_priority_groups in enumerate(config.root)
    ]

    return entrypoints_exception_priority_groups


def parse_entrypoints_exception_priority_group(
    config: ConfigExceptionPriorityGroup,
    functions: Functions,
    *,
    index: int,
) -> EntrypointsExceptionPriorityGroup:
    entrypoints = [
        parse_entrypoint(
            config_entrypoint,
            functions,
            name_hint=f"Entrypoint #{entrypoint_index}",
        )
        for entrypoint_index, config_entrypoint in enumerate(config.exceptions)
    ]

    name = config.name if config.name is not None else f"Priority Group #{index}"

    return EntrypointsExceptionPriorityGroup(
        entrypoints=entrypoints,
        name=name,
    )


def parse_entrypoint(config: ConfigEntrypoint, functions: Functions, *, name_hint: str) -> Entrypoint:
    match config.handler:
        case int():
            # Address
            function = functions.by_address.get(config.handler)
            if function is None:
                raise ValueError(f"Entrypoint function configured by address 0x{config.handler:04X} was not found.")
        case str():
            # name
            function = functions.by_name.get(config.handler)
            if function is None:
                raise ValueError(f"Entrypoint function configured by name `{config.handler}` was not found.")
        case _:
            assert False

    # get interrupt name from user provided value (if set), otherwise from target function name, otherwise autogenerate
    name: str
    if config.name is not None:
        name = config.name
    elif len(function.names) == 1:
        name = one(function.names)
    else:
        name = name_hint

    return Entrypoint(
        address=function.address,
        name=name,
    )
