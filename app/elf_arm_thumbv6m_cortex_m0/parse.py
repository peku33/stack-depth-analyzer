# cortex-m0(+) microcontroller with thumb v6-m isa

from collections.abc import Collection, Iterator, Mapping
from pathlib import Path
from typing import Any, cast

from elftools.elf.constants import E_FLAGS
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import (
    ARMAttribute,
    ARMAttributesSection,
    ARMAttributesSubsection,
    ARMAttributesSubsubsection,
)
from more_itertools import one

from .config import Config
from .entrypoints.parse import parse as entrypoints_parse
from .functions.parse import parse as functions_parse
from .program.model import Program
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
    _validate_elffile(elffile)

    if config is None:
        config = Config.default()

    functions = functions_parse(elffile, config.functions)

    entrypoints = entrypoints_parse(elffile, functions, config.entrypoints)

    program = program_parse(functions, entrypoints)

    return program


def _validate_elffile(elffile: ELFFile) -> None:
    header = cast(Mapping[str, Any], elffile.header)  # pyright: ignore[reportUnknownMemberType]
    e_ident = cast(Mapping[str, Any], header["e_ident"])
    attributes = _extract_elffile_attributes(elffile)

    # make sure we are parsing correct file
    _assert_equals("EI_VERSION", e_ident["EI_VERSION"], "EV_CURRENT")
    _assert_equals("EI_CLASS", e_ident["EI_CLASS"], "ELFCLASS32")
    _assert_equals("EI_DATA", e_ident["EI_DATA"], "ELFDATA2LSB")
    _assert_one_of("EI_OSABI", e_ident["EI_OSABI"], ("ELFOSABI_LINUX", "ELFOSABI_SYSV"))
    _assert_equals("EI_ABIVERSION", e_ident["EI_ABIVERSION"], 0)

    _assert_equals("e_version", header["e_version"], "EV_CURRENT")
    _assert_equals("e_type", header["e_type"], "ET_EXEC")
    _assert_equals("e_machine", header["e_machine"], "EM_ARM")
    _assert_equals("e_flags", header["e_flags"], E_FLAGS.EF_ARM_EABI_VER5 | E_FLAGS.EF_ARM_ABI_FLOAT_SOFT)

    _assert_one_of("TAG_CONFORMANCE", attributes.get("TAG_CONFORMANCE"), (None, "2.09"))  # rust - 2.09
    _assert_one_of("TAG_CPU_ARCH", attributes["TAG_CPU_ARCH"], (11, 12))  # ARM v6-M or ARM v6S-M
    _assert_equals("TAG_CPU_ARCH_PROFILE", attributes["TAG_CPU_ARCH_PROFILE"], 0x4D)  # Microcontroller
    _assert_one_of("TAG_ARM_ISA_USE", attributes.get("TAG_ARM_ISA_USE"), (None, 0))  # rust - 0 (isa use none)
    _assert_equals("TAG_THUMB_ISA_USE", attributes["TAG_THUMB_ISA_USE"], 1)  # Thumb-1
    _assert_one_of("TAG_ABI_PCS_R9_USE", attributes.get("TAG_ABI_PCS_R9_USE"), (None, 0))  # rust - 0 (Normal)


def _extract_elffile_attributes(elffile: ELFFile) -> Mapping[str, Any]:
    # check arm attributes
    arm_attributes = cast(
        ARMAttributesSection | None,
        elffile.get_section_by_name(".ARM.attributes"),  # type: ignore
    )
    if arm_attributes is None:
        raise ValueError("Missing `.ARM.attributes` section.")

    # we expect one "aeabi" subsection
    arm_attribute = one(
        cast(Iterator[ARMAttributesSubsection], arm_attributes.iter_subsections()),  # type: ignore
    )
    _assert_equals(
        "vendor_name",
        arm_attribute.header["vendor_name"],  # pyright: ignore[reportUnknownArgumentType,reportUnknownMemberType]
        "aeabi",
    )

    # we expect one "FILE" subsection
    file_attribute = one(
        cast(Iterator[ARMAttributesSubsubsection], arm_attribute.iter_subsubsections()),  # type: ignore
    )
    file_attribute_header = cast(ARMAttribute, file_attribute.header)  # pyright: ignore[reportUnknownMemberType]
    _assert_equals(
        "tag",
        file_attribute_header.tag,  # pyright: ignore[reportUnknownArgumentType,reportUnknownMemberType]
        "TAG_FILE",
    )

    attributes = {
        cast(str, attribute.tag): cast(Any, attribute.value)  # pyright: ignore[reportUnknownMemberType]
        for attribute in cast(Iterator[ARMAttribute], file_attribute.iter_attributes())  # type: ignore
    }

    return attributes


def _assert_equals[T](property_: str, actual: T, expected: T) -> None:
    if actual != expected:
        raise ValueError(f"Expecting {property_} to be `{expected}`, but got `{actual}`")


def _assert_one_of[T](property_: str, actual: T, expecteds: Collection[T]) -> None:
    if actual not in expecteds:
        raise ValueError(
            f"Expecting {property_} to be one of "
            f"{", ".join(f"`{expected}`" for expected in expecteds)}, "
            "but got `{actual}`"
        )
