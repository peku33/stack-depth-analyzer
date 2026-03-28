from typing import Literal, Self

from pydantic import BaseModel, Field

from app.elf_arm_thumbv6m.functions.config import Config as Functions

from .entrypoints.config import Config as Entrypoints


class Config(BaseModel):
    # main configuration file, supplied by user

    # used to distinguish config versions if more then one is available
    stack_depth_analyzer: Literal["elf_arm_thumbv6m_cortex_m0:v1"]

    # see Functions for details
    functions: Functions = Field(default_factory=Functions.default)

    # see Entrypoints for details
    entrypoints: Entrypoints = Field(default_factory=Entrypoints.default)

    @classmethod
    def default(cls) -> Self:
        return cls(
            # TODO: make this smarter
            stack_depth_analyzer="elf_arm_thumbv6m_cortex_m0:v1",
        )
