from collections.abc import Sequence
from typing import Annotated, Self

from annotated_types import MinLen
from pydantic import BaseModel, Field, RootModel

from ..common import Address


class ConfigEntrypoint(BaseModel):
    # definition of single entrypoint (main, isr, etc.)

    handler: Address | str  # Address (numeric) or function name (text)
    name: str | None = None  # None - generate automatically (based on function name, etc)


class ConfigExceptionPriorityGroup(BaseModel):
    # definition of single exception priority group. priority groups are meant to preempt each other. exceptions within
    # single groups are meant to be executed sequentially.

    exceptions: Annotated[Sequence[ConfigEntrypoint], MinLen(1)]
    name: str | None = None  # None - generate automatically (based on function name, etc)


class ConfigExceptionPriorityGroups(RootModel[Sequence[ConfigExceptionPriorityGroup]]):
    # collection of exception priority groups. multiple priority groups are meant to preempt each other (and main).
    # entrypoints within single priority group are executed sequentially.

    @classmethod
    def default(cls) -> Self:
        return cls([])


class Config(BaseModel):
    # entrypoints resolver configuration

    # main program entrypoints, eg (reset vector, main(), etc.)
    main: ConfigEntrypoint

    # additional exception vectors, formed as priority groups. see ConfigEntrypointsPriorityGroup for details
    exception_priority_groups: ConfigExceptionPriorityGroups = Field(
        default_factory=ConfigExceptionPriorityGroups.default
    )
