from pathlib import Path
from typing import Annotated

from typer import Argument, Typer

from app.elf_arm_thumbv6m.__main__ import display_summary

from .._cli import console
from .parse import parse_path

app = Typer()


@app.command()
def summary(elf_path: Path, config_path: Annotated[Path | None, Argument()] = None) -> None:
    with console.status("Parsing..."):
        program = parse_path(elf_path, config_path)

    display_summary(program)


if __name__ == "__main__":
    app()
