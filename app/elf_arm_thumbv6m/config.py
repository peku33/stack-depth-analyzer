from typing import Literal

from pydantic import BaseModel, Field

from .entrypoints.config import Config as Entrypoints
from .functions.config import Config as Functions


class Config(BaseModel):
    # main configuration file, supplied by user

    # used to distinguish config versions if more then one is available
    stack_depth_analyzer: Literal["elf_arm_thumbv6m:v1"]

    # see Functions for details
    functions: Functions = Field(default_factory=Functions.default)

    # see Entrypoints for details
    entrypoints: Entrypoints
