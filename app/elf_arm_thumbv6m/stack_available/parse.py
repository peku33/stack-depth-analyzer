from collections.abc import Mapping
from dataclasses import dataclass
from logging import getLogger
from typing import Any, cast

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

from ..common import Address

_logger = getLogger(__name__)


# stack bounds defined by linker script / startup code
# stack grows down from top (initial SP) to bottom
@dataclass(frozen=True, kw_only=True)
class _ProviderRange:
    top: str
    bottom: str


# stack size defined directly as absolute symbol value
@dataclass(frozen=True, kw_only=True)
class _ProviderSize:
    size: str


type _Provider = _ProviderRange | _ProviderSize


# checked in order, first fully matching wins
# NOTE: order matters, eg. pico sdk defines both `__StackBottom` and `__StackLimit`, but the latter means RAM end
_PROVIDERS: tuple[_Provider, ...] = (
    _ProviderRange(  # rust cortex-m-rt
        top="_stack_start",
        bottom="_stack_end",
    ),
    _ProviderRange(  # raspberry pi pico sdk
        top="__StackTop",
        bottom="__StackBottom",
    ),
    _ProviderRange(  # CMSIS GCC (incl. nRF SDK)
        top="__StackTop",
        bottom="__StackLimit",
    ),
    _ProviderRange(  # microchip / atmel ASF GCC
        top="_estack",
        bottom="_sstack",
    ),
    _ProviderRange(  # IAR
        top="CSTACK$$Limit",
        bottom="CSTACK$$Base",
    ),
    _ProviderRange(  # Keil scatter
        top="Image$$ARM_LIB_STACK$$ZI$$Limit",
        bottom="Image$$ARM_LIB_STACK$$ZI$$Base",
    ),
    _ProviderRange(  # Keil/ARMCC startup assembly
        top="__initial_sp",
        bottom="Stack_Mem",
    ),
    _ProviderSize(  # STM32 GCC, minimal guaranteed size, stack may grow beyond it
        size="_Min_Stack_Size",
    ),
)


def parse(elffile: ELFFile) -> int | None:
    # stack symbols are linker (not processor) specific, so they may be missing - available stack is unknown then
    section = cast(
        SymbolTableSection | None,
        elffile.get_section_by_name(".symtab"),
    )
    if section is None:
        _logger.warning("Unable to find symbols table section (.symtab), available stack is unknown.")
        return None

    stack_availables = {
        stack_available
        for provider in _PROVIDERS
        if (stack_available := _parse_provider(section, provider)) is not None
    }
    match list(stack_availables):
        case []:
            _logger.warning("Unable to find stack symbols, available stack is unknown.")
            return None
        case [stack_available]:
            return stack_available
        case _:
            raise AssertionError


def _parse_provider(section: SymbolTableSection, provider: _Provider) -> int | None:
    match provider:
        case _ProviderRange(
            top=top_name,
            bottom=bottom_name,
        ):
            top = _symbol_address(section, top_name)
            bottom = _symbol_address(section, bottom_name)
            if top is None or bottom is None:
                return None

            if top < bottom:
                raise ValueError(
                    f"Stack top (`{top_name}` @ 0x{top:04X}) is below stack bottom (`{bottom_name}` @ 0x{bottom:04X})."
                )

            return top - bottom
        case _ProviderSize(
            size=size_name,
        ):
            return _symbol_address(section, size_name)
        case _:
            raise AssertionError


def _symbol_address(section: SymbolTableSection, name: str) -> Address | None:
    symbols = section.get_symbol_by_name(name)
    match symbols:
        case None | []:
            return None
        case [symbol]:
            pass
        case _:
            raise AssertionError

    entry = cast(Mapping[str, Any], symbol.entry)

    address = cast(Address, entry["st_value"])

    return address
