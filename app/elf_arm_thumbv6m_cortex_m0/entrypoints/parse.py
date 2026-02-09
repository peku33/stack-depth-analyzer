from collections.abc import Iterator
from logging import getLogger
from typing import cast

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import Section
from more_itertools import one

from ..common import function_like_format
from ..functions.model import Function, Functions
from .config import (
    Config,
    ConfigDefaultHandler,
    ConfigExceptionConfigurable,
    ConfigExceptionConfigurableEnabled,
    ConfigExceptionOptional,
    ConfigInterrupt,
    ConfigInterruptConfig,
    ConfigInterruptConfigEnabled,
)
from .model import (
    EntrypointInterrupt,
    EntrypointInterrupts,
    Entrypoints,
    EntrypointVector,
    EntrypointVectorWithPriorityGroup,
)

_logger = getLogger(__name__)

_VECTOR_TABLE_SECTION_NAMES = {
    ".vector_table",  # rust cortex-m-rt
    ".isr_vector",  # GCC
    ".intvec",  # IAR
    "VECTORS",  # Keil/ARMCC
}

_DEFAULT_HANDLER_NAMES = {
    "DefaultHandler",  # used by rust cortex-m-rt
    "DefaultHandler_",  # used by rust cortex-m-rt
}


def parse(elffile: ELFFile, functions: Functions, config: Config) -> Entrypoints:
    # https://developer.arm.com/documentation/dui0497/a/the-cortex-m0-processor/exception-model/vector-table
    # we use non-reserved values only
    vector_table = resolve_vector_table_section(elffile)

    vector_table_bytes = cast(bytes, vector_table.data())  # type: ignore
    if len(vector_table_bytes) % 4 != 0:
        raise ValueError(f"Weird size of vector table section ({len(vector_table_bytes)}), should be divisible by 4.")

    default_handler_function = resolve_default_handler_function(functions, config.default_handler)

    # extract vector table size, must be at least 16 (initial SP + 15 core exceptions), at most 48 (with 32 interrupts)
    vector_table_entries_count = len(vector_table_bytes) // 4  # including sp initial value
    if not 16 <= vector_table_entries_count <= 48:
        raise ValueError(
            f"Weird count of vector table entries count ({vector_table_entries_count}), expecting 16 <= ... <= 48."
        )

    # extract exceptions & interrupts from vector table
    reset: EntrypointVector | None = None

    nmi: EntrypointVector | None = None
    hardfault: EntrypointVector | None = None

    svcall: EntrypointVectorWithPriorityGroup | None = None
    pendsv: EntrypointVectorWithPriorityGroup | None = None
    systick: EntrypointVectorWithPriorityGroup | None = None

    interrupts = list[EntrypointInterrupt]()

    for exception_number in range(1, vector_table_entries_count):  # offset 0 is initial SP
        # resolve target function
        function: Function | None
        address_ = int.from_bytes(vector_table_bytes[(exception_number * 4) : ((exception_number + 1) * 4)], "little")
        if address_ != 0:
            # thumb bit must be set
            if address_ & 1 != 1:
                raise ValueError(
                    f"Thumb bit not set for vector #{exception_number} at address 0x{address_:04X}? "
                    "This would result in HardFault..."
                )

            # remove it for function address
            address = address_ & ~1

            # find a function, it must exist
            function = functions.by_address.get(address)
            if function is None:
                raise ValueError(f"Vector #{exception_number} points to non-existing function at 0x{address_:04X}.")
        else:
            # 0 address is assumed to be unused
            function = None

        if exception_number < 16:
            # exceptions at specific offsets
            # only exceptions defined by the core should be set
            match exception_number:
                case 1:
                    # Reset
                    if function is None:
                        raise ValueError("Missing vector table entry for `Reset`.")

                    _warn_if_enabled_default_mismatch("Reset", function, default_handler_function)

                    reset = EntrypointVector(
                        address=function.address,
                    )
                case 2:
                    # NMI (optional)
                    if function is None:
                        raise ValueError("Missing vector table entry for `NMI`.")

                    nmi = resolve_entrypoint_vector_from_config_exception_optional(
                        "NMI", function, config.nmi, default_handler_function
                    )
                case 3:
                    # HardFault
                    if function is None:
                        raise ValueError("Missing vector table entry for `HardFault`.")

                    _warn_if_enabled_default_mismatch("HardFault", function, default_handler_function)

                    hardfault = EntrypointVector(
                        address=function.address,
                    )
                case 11:
                    # SVCall (configurable)
                    if function is None:
                        raise ValueError("Missing vector table entry for `SVCall`.")

                    svcall = resolve_entrypoint_vector_with_priority_group_from_config_exception_configurable(
                        "SVCall", function, config.svcall, default_handler_function
                    )
                case 14:
                    # PendSV (configurable)
                    if function is None:
                        raise ValueError("Missing vector table entry for `PendSV`.")

                    pendsv = resolve_entrypoint_vector_with_priority_group_from_config_exception_configurable(
                        "PendSV", function, config.pendsv, default_handler_function
                    )
                case 15:
                    # SysTick (configurable)
                    if function is None:
                        raise ValueError("Missing vector table entry for `SysTick`.")

                    systick = resolve_entrypoint_vector_with_priority_group_from_config_exception_configurable(
                        "SysTick", function, config.systick, default_handler_function
                    )
                case _:
                    # should be reserved, there should be no valid entry in the table
                    if function is not None:
                        _logger.warning(
                            "Unused exception #%d points to a function %s",
                            exception_number,
                            function_like_format(function),
                        )

        else:
            # interrupts starts from 16
            interrupt_number = exception_number - 16

            # resolve config
            interrupt_config = config.interrupts.by_number.get(interrupt_number)
            assert interrupt_config is None or interrupt_config.number == interrupt_number

            if function is not None:
                # vector table has function address and it was resolved
                # build vector
                entrypoint_interrupt = resolve_entrypoint_interrupt_from_config_interrupt(
                    interrupt_number, function, interrupt_config, default_handler_function
                )

                if entrypoint_interrupt is not None:
                    interrupts.append(entrypoint_interrupt)
            else:
                # vector table does not contain entry for this interrupt
                # user should also not provide config for it, as it won't be reached?
                if interrupt_config is not None:
                    _logger.warning(
                        (
                            "Interrupt #%d does not have a valid address in the vector table, "
                            "but interrupt definition wa provided (%s). "
                            "Probably a non-existing interrupt is configured."
                        ),
                        interrupt_number,
                        interrupt_config,
                    )

    # these must be present, guaranteed by initial check for table size
    assert reset is not None
    assert hardfault is not None

    return Entrypoints(
        reset=reset,
        nmi=nmi,
        hardfault=hardfault,
        svcall=svcall,
        pendsv=pendsv,
        systick=systick,
        interrupts=EntrypointInterrupts(interrupts),
    )


def resolve_vector_table_section(elffile: ELFFile) -> Section:
    # find all sections matching different toolchains
    sections = [
        section
        for section in cast(Iterator[Section], elffile.iter_sections())  # type: ignore
        if section.name in _VECTOR_TABLE_SECTION_NAMES
    ]

    match sections:
        case []:
            # no matching sections was found
            raise ValueError(
                "No vector table section was found, "
                f"tried: {", ".join(f"`{section_name}`" for section_name in _VECTOR_TABLE_SECTION_NAMES)}."
            )
        case [section]:
            # exactly one matching section was found, yay
            return section
        case _:
            # multiple matching sections were found
            raise ValueError(
                "Multiple vector table sections were found? "
                f"({", ".join(f"`{section.name}`" for section in sections)})."
            )


def resolve_default_handler_function(functions: Functions, config: ConfigDefaultHandler) -> Function | None:
    default_handler_function: Function | None
    match config.root:
        case True:
            # autodetect

            # get all functions matching our predefined names list
            default_handler_functions = [
                function
                for function in (
                    functions.by_name.get(default_handler_name) for default_handler_name in _DEFAULT_HANDLER_NAMES
                )
                if function is not None
            ]

            # we should have exactly one match
            match default_handler_functions:
                case [default_handler_function]:
                    # exactly one match
                    _logger.info(
                        "Resolved auto-detected default handler to be %s",
                        function_like_format(default_handler_function),
                    )
                case []:
                    # no matches
                    _logger.warning(
                        (
                            "None of auto-detected default handler names was found, defaulting to none. "
                            "Functionality will be disabled."
                        )
                    )
                    default_handler_function = None
                case _:
                    # multiple matches
                    _logger.warning(
                        (
                            "Multiple matches for auto-detected default handler names was found (%s). "
                            "Functionality will be disabled."
                        ),
                        {
                            name
                            for default_handler_function in default_handler_functions
                            for name in default_handler_function.names
                        },
                    )
                    default_handler_function = None
        case False:
            # disable
            default_handler_function = None
        case int():
            # Address
            # NOTE: must be after True/False as int() matches bool()
            default_handler_function = functions.by_address.get(config.root)
            if default_handler_function is None:
                raise ValueError(f"Default handler function configured by address 0x{config.root:04X} was not found.")
        case str():
            # name
            default_handler_function = functions.by_name.get(config.root)
            if default_handler_function is None:
                raise ValueError(f"Default handler function configured by name `{config.root}` was not found.")
        case _:
            assert False

    return default_handler_function


def resolve_entrypoint_vector_from_config_exception_optional(
    name: str, function: Function, config: ConfigExceptionOptional, default_handler_function: Function | None
) -> EntrypointVector | None:
    match config.root:
        case True:
            # user says it will be used

            # warn if points to default handler
            _warn_if_enabled_default_mismatch(name, function, default_handler_function)
        case False:
            # user guarantees no call

            # warn if call points to non-default handler
            _warn_if_disabled_default_mismatch(name, function, default_handler_function)

            return None
        case None:
            # user chosen autodetected
            if default_handler_function is None:
                _logger.warning(
                    (
                        "Exception `%s` is auto-configured, but default handler was not specified. "
                        "Unable to determine if it's used or not, assuming it is."
                    ),
                    name,
                )
            elif function == default_handler_function:
                # function points to default handler, so we assume it won't be used
                return None
        case _:
            assert False

    return EntrypointVector(
        address=function.address,
    )


def resolve_entrypoint_vector_with_priority_group_from_config_exception_configurable(
    name: str,
    function: Function,
    config: ConfigExceptionConfigurable,
    default_handler_function: Function | None,
) -> EntrypointVectorWithPriorityGroup | None:
    priority_group: int | None
    match config.root:
        case ConfigExceptionConfigurableEnabled(
            priority_group=priority_group,
        ):
            # user says it will be used, and provides details
            # sets `priority_group`

            # warn if points to default handler
            _warn_if_enabled_default_mismatch(name, function, default_handler_function)
        case True:
            # user says it will be used, but provides no details
            priority_group = None

            # warn if points to default handler
            _warn_if_enabled_default_mismatch(name, function, default_handler_function)
        case False:
            # user guarantees no call

            # warn if call points to non-default handler
            _warn_if_disabled_default_mismatch(name, function, default_handler_function)

            return None
        case None:
            # user chosen autodetected
            if default_handler_function is None:
                _logger.warning(
                    (
                        "Exception `%s` is auto-configured, but default handler was not specified. "
                        "Unable to determine if it's used or not, assuming it is."
                    ),
                    name,
                )

            if default_handler_function is not None and function == default_handler_function:
                # function points to default handler, so we assume it won't be used
                return None
            else:
                # function points to non-default handler, so we assume it will be used
                priority_group = None
        case _:
            assert False

    if priority_group is None:
        _logger.warning(
            (
                "Resolved unspecified priority group for exception `%s`. "
                "Worst case scenario will be assumed (can preempt / be preempted by everything). "
                "Provide valid priority group in config, based on your interrupt settings."
            ),
            name,
        )

    return EntrypointVectorWithPriorityGroup(
        vector=EntrypointVector(
            address=function.address,
        ),
        priority_group=priority_group,
    )


def resolve_entrypoint_interrupt_from_config_interrupt(
    interrupt_number: int, function: Function, config: ConfigInterrupt | None, default_handler_function: Function | None
) -> EntrypointInterrupt | None:
    assert config is None or config.number == interrupt_number

    # get interrupt name from user provided value (if set), otherwise from target function name, otherwise autogenerate
    name: str
    if config is not None and config.name is not None:
        name = config.name
    elif len(function.names) == 1:
        name = one(function.names)
    else:
        name = f"Interrupt #{interrupt_number} (autogenerated)"

    priority_group: int | None

    config_config = config.config if config is not None else ConfigInterruptConfig.default()
    match config_config.root:
        case ConfigInterruptConfigEnabled(
            priority_group=priority_group,
        ):
            # user says it will be used, and provides details
            # sets `priority_group`

            # warn if points to default handler
            _warn_if_enabled_default_mismatch(name, function, default_handler_function)
        case True:
            # user says it will be used, but provides no details
            priority_group = None

            # warn if points to default handler
            _warn_if_enabled_default_mismatch(name, function, default_handler_function)
        case False:
            # user guarantees no call
            # warn if call points to non-default handler

            _warn_if_disabled_default_mismatch(name, function, default_handler_function)

            return None
        case None:
            # user chosen autodetected
            if default_handler_function is None:
                _logger.warning(
                    (
                        "Interrupt #%d is auto-configured, but default handler was not specified. "
                        "Unable to determine if it's used or not, assuming it is."
                    ),
                    interrupt_number,
                )

            if default_handler_function is not None and function == default_handler_function:
                # function points to default handler, so we assume it won't be used
                return None
            else:
                # function points to non-default handler, so we assume it will be used
                priority_group = None
        case _:
            assert False

    if priority_group is None:
        _logger.warning(
            (
                "Resolved unspecified priority group for interrupt #%d. "
                "Worst case scenario will be assumed (can preempt / be preempted by everything). "
                "Provide valid priority group in config, based on your interrupt settings."
            ),
            interrupt_number,
        )

    return EntrypointInterrupt(
        number=interrupt_number,
        name=name,
        vector_with_priority_group=EntrypointVectorWithPriorityGroup(
            vector=EntrypointVector(
                address=function.address,
            ),
            priority_group=priority_group,
        ),
    )


def _warn_if_enabled_default_mismatch(name: str, function: Function, default_handler_function: Function | None) -> None:
    if default_handler_function is None:
        # unable to check
        return

    if function == default_handler_function:
        _logger.warning(
            "`%s` is enabled, but points to default handler %s.", name, function_like_format(default_handler_function)
        )


def _warn_if_disabled_default_mismatch(
    name: str, function: Function, default_handler_function: Function | None
) -> None:
    if default_handler_function is None:
        # unable to check
        return

    if function != default_handler_function:
        _logger.warning(
            "`%s` is disabled, but points to %s, which is not default handler %s.",
            name,
            function_like_format(function),
            function_like_format(default_handler_function),
        )
