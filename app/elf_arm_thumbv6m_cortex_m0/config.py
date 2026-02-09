from typing import Literal, Self

from pydantic import BaseModel, Field

from .entrypoints.config import Config as Entrypoints
from .functions.config import Config as Functions


class Config(BaseModel):
    # main configuration file, supplied by user

    # used to distinguish config versions if more then one is available
    stack_depth_analyzer_version: Literal[1]

    # see Functions for details
    functions: Functions = Field(default_factory=Functions.default)

    # see Entrypoints for details
    entrypoints: Entrypoints = Field(default_factory=Entrypoints.default)

    @classmethod
    def default(cls) -> Self:
        return cls(
            # TODO: make this smarter
            stack_depth_analyzer_version=1,
        )
