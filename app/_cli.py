# side-effect module to be used within __main__.py

import logging
import string
from collections.abc import Collection
from functools import cache
from itertools import chain

from rich.console import Console
from rich.logging import RichHandler
from rich.markup import escape
from rich.style import Style
from rich.text import Text
from rich.traceback import install

console = Console()

install(
    console=console,
)

logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[
        RichHandler(
            rich_tracebacks=True,
            markup=False,
        )
    ],
)
logging.getLogger("app").setLevel(logging.DEBUG)
logging.getLogger("__main__").setLevel(logging.DEBUG)


@cache
def function_name_format(name: str) -> Text:
    parts = name.split("::")

    if not parts:
        return Text("?")

    # special case - if last part is h+HEX - this is rust hash, dim it
    part_format_rust_hash = _function_name_format_rust_hash(parts[-1])
    if part_format_rust_hash is not None:
        del parts[-1]

    # last item should be function name - highlight it
    # NOTE: technically parts could be empty right now, but this is super unlikely
    part_format_function_name = Text(
        escape(parts[-1]),
        style=Style(
            bold=True,
        ),
    )
    del parts[-1]

    # others - treat them normally
    parts_format_path = [Text(escape(part)) for part in parts]

    # combine
    format_ = Text("::").join(
        chain(
            parts_format_path,
            [part_format_function_name],
            ([part_format_rust_hash] if part_format_rust_hash is not None else []),
        )
    )

    return format_


def function_names_format(names: Collection[str]) -> Text:
    return Text(" / ").join(function_name_format(name) for name in names)


_HEX_LOWERCASE = set(chain(string.digits, "abcdef"))


def _function_name_format_rust_hash(part: str) -> Text | None:
    # h + lowercase hex
    if len(part) != 17:
        return None

    if part[0] != "h":
        return None

    if not set(part[1]) <= _HEX_LOWERCASE:
        return None

    return Text(
        part,
        style=Style(
            dim=True,
        ),
    )
