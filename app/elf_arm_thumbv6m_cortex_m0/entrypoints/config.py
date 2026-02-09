from collections.abc import Mapping, Sequence
from functools import cached_property
from typing import Annotated, Self

from annotated_types import Ge, Lt
from more_itertools import duplicates_everseen
from pydantic import BaseModel, Field, RootModel, model_validator

from ..common import Address
from .common import PRIORITY_GROUPS


class ConfigDefaultHandler(RootModel[Address | str | bool]):
    # default handler used by the program for unused/disabled interrupts. this helps to determine which
    # interrupts/exceptions are enabled if autodetect option is used (in exceptions/interrupts)
    # Address - user established default handler (by numeric function address)
    # str - user established default handler (by function name) (recommended)
    # True - automatically established default handler
    # False - default handler related functionality disabled

    @classmethod
    def default(cls) -> Self:
        return cls(True)


class ConfigExceptionOptional(RootModel[bool | None]):
    # configuration for exception which can be enabled/disable, but has no configurable priority (ex. nmi)
    # True - enabled/used (recommended if used)
    # False - disabled/unused (guaranteed no call) (recommended if not used)
    # None - autodetect (based on function match with default_handler)

    @classmethod
    def default(cls) -> Self:
        return cls(None)


type ConfigPriorityGroup = Annotated[int, Ge(0), Lt(PRIORITY_GROUPS)]  # supports priorities 0-3 (two bits)


class ConfigExceptionConfigurableEnabled(BaseModel):
    # optional exception - possibility to be executed depends on program flow (ex. whether systick will fire depends
    # whether user enables it.)

    priority_group: ConfigPriorityGroup | None  # None for unset priority (will create independent group)


class ConfigExceptionConfigurable(RootModel[ConfigExceptionConfigurableEnabled | bool | None]):
    # configuration for exception which can be enabled/disabled, with configurable priority (ex. SysTick)
    # ConfigExceptionConfigurableEnabled - enabled/used with provided details (recommended if used)
    # True - enabled/used with fallback details (not recommended)
    # False - disabled/unused (guaranteed no call) (recommended if not used)
    # None - autodetect (based on function match with default_handler)

    @classmethod
    def default(cls) -> Self:
        return cls(None)


class ConfigInterruptConfigEnabled(BaseModel):
    # configuration for enabled interrupt

    priority_group: ConfigPriorityGroup | None  # None for unset priority (will create independent group)


class ConfigInterruptConfig(RootModel[ConfigInterruptConfigEnabled | bool | None]):
    # configuration for interrupt
    # ConfigInterruptConfigEnabled - enabled/used with provided details (recommended if used)
    # True - enabled/used with fallback details (not recommended)
    # False - disabled/unused (guaranteed no call) (recommended if not used)
    # None - autodetect (based on function match with default_handler)

    @classmethod
    def default(cls) -> Self:
        return cls(None)


type ConfigInterruptNumber = Annotated[int, Ge(0), Lt(32)]


class ConfigInterrupt(BaseModel):
    # definition of single interrupt

    number: ConfigInterruptNumber  # must be unique
    name: str | None = None  # None - generate automatically (based on function name, etc)

    # see ConfigInterruptConfig for details
    config: ConfigInterruptConfig = Field(default_factory=ConfigInterruptConfig.default)


class ConfigInterrupts(RootModel[Sequence[ConfigInterrupt]]):
    # collection of interrupts
    # each item should correspond to single interrupt exposed by the processor, regardless if it's used by the program
    # or not (this should be indicated by config property of ConfigInterrupt).
    # unspecified items will be generated automatically (however its recommended to specify them manually)

    @classmethod
    def default(cls) -> Self:
        return cls([])

    @model_validator(mode="after")
    def check_numbers_unique(self) -> Self:
        numbers_duplicate = set(duplicates_everseen(interrupt.number for interrupt in self.root))
        if numbers_duplicate:
            raise ValueError(
                "Interrupt numbers duplicated: "
                f"{", ".join(str(number_duplicate) for number_duplicate in numbers_duplicate)}"
            )

        return self

    @cached_property
    def by_number(self) -> Mapping[ConfigInterruptNumber, ConfigInterrupt]:
        return {interrupt.number: interrupt for interrupt in self.root}


class Config(BaseModel):
    # entrypoints resolver configuration

    # see ConfigDefaultHandler for details
    default_handler: ConfigDefaultHandler = Field(default_factory=ConfigDefaultHandler.default)

    # exceptions like reset/hardfault are not configurable in any way (cannot be disabled, cannot have changed
    # priority), so we don't provide any configuration for them

    # exceptions like nmi have fixed priority, but technically user can enforce they never happen (eg. does not use any
    # mechanism firing them)
    # see ConfigExceptionOptional for details
    nmi: ConfigExceptionOptional = Field(default_factory=ConfigExceptionOptional.default)

    # exceptions like svcall, systick are configurable:
    # - they can be enabled/disabled (used/unused) by the program (eg. user does not use systick at all)
    # - they can have set priority (in NVIC)
    # see ConfigExceptionConfigurable for details
    svcall: ConfigExceptionConfigurable = Field(default_factory=ConfigExceptionConfigurable.default)
    pendsv: ConfigExceptionConfigurable = Field(default_factory=ConfigExceptionConfigurable.default)
    systick: ConfigExceptionConfigurable = Field(default_factory=ConfigExceptionConfigurable.default)

    # interrupts, see ConfigInterrupts for details
    interrupts: ConfigInterrupts = Field(default_factory=ConfigInterrupts.default)

    @classmethod
    def default(cls) -> Self:
        return cls()
