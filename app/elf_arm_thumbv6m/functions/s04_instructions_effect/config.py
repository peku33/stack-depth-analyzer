from collections.abc import Mapping, Sequence, Set
from functools import cached_property
from typing import Self

from more_itertools import duplicates_everseen
from pydantic import BaseModel, Field, RootModel, field_validator, model_validator

from ...common import Address


class ConfigCallOverride(BaseModel):
    # single call override

    source: Address  # calling instruction address (eg. BX R0)
    targets: Set[Address]  # all possible target function addresses, unique

    @field_validator("source", mode="after")
    @classmethod
    def validate_source(cls, source: Address) -> Address:
        if source % 2 != 0:
            raise ValueError("Source address must be aligned")

        return source

    @field_validator("targets", mode="after")
    @classmethod
    def validate_targets(cls, targets: Set[Address]) -> Set[Address]:
        if not targets:
            raise ValueError("Targets must not me empty")

        if any(target % 2 != 0 for target in targets):
            raise ValueError("Targets must be aligned")

        return targets


class ConfigCallOverrides(RootModel[Sequence[ConfigCallOverride]]):
    # list of call overrides, to hint resolved where unresolved function calls points to

    @classmethod
    def default(cls) -> Self:
        return cls([])

    @model_validator(mode="after")
    def check_sources_unique(self) -> Self:
        sources_duplicate = set(duplicates_everseen(override.source for override in self.root))
        if sources_duplicate:
            raise ValueError(
                "Duplicate sources "
                f"({", ".join(f"0x{source_duplicate:04X}" for source_duplicate in sources_duplicate)}) "
                "found"
            )

        return self

    @cached_property
    def targets_by_source(self) -> Mapping[Address, Set[Address]]:
        return {override.source: override.targets for override in self.root}


class Config(BaseModel):
    # configuration for instructions effect resolver

    # see ConfigCallOverrides for details
    call_overrides: ConfigCallOverrides = Field(default_factory=ConfigCallOverrides.default)

    @classmethod
    def default(cls) -> Self:
        return cls()
