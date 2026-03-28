from typing import Self

from pydantic import BaseModel, Field

from .s04_instructions_effect.config import Config as InstructionsEffect


class Config(BaseModel):
    # functions resolver configuration

    # see InstructionsEffect for details
    instructions_effect: InstructionsEffect = Field(default_factory=InstructionsEffect.default)

    @classmethod
    def default(cls) -> Self:
        return cls()
