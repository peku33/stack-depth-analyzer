from collections.abc import Set
from typing import Protocol

type Address = int


def function_format(address: Address, names: Set[str]) -> str:
    return f"0x{address:04X} ({" / ".join(f"`{name}`" for name in names)})"


class FunctionLikeFormat(Protocol):
    @property
    def address(self) -> Address: ...

    @property
    def names(self) -> Set[str]: ...


def function_like_format(function_like: FunctionLikeFormat) -> str:
    return function_format(function_like.address, function_like.names)
