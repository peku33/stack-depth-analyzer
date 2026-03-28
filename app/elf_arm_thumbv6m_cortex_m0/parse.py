# cortex-m0(+) microcontroller with thumb v6-m isa

from pathlib import Path

from elftools.elf.elffile import ELFFile

from app.elf_arm_thumbv6m.functions.parse import parse as functions_parse
from app.elf_arm_thumbv6m.parse import validate_elffile
from app.elf_arm_thumbv6m.program.model import Program

from .config import Config
from .entrypoints.parse import parse as entrypoints_parse
from .program.parse import parse as program_parse


def parse_path(elf_path: Path, config_path: Path | None) -> Program:
    with elf_path.open("rb") as elf_file:
        elffile = ELFFile(elf_file)  # type: ignore

        if config_path is not None:
            with config_path.open("r") as config_file:
                config = Config.model_validate_json(config_file.read())
        else:
            config = None

        program = parse(elffile, config)

    return program


def parse(elffile: ELFFile, config: Config | None) -> Program:
    validate_elffile(elffile)

    if config is None:
        config = Config.default()

    functions = functions_parse(elffile, config.functions)

    entrypoints = entrypoints_parse(elffile, functions, config.entrypoints)

    program = program_parse(functions, entrypoints)

    return program
