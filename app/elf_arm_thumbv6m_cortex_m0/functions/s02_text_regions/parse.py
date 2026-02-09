from typing import cast

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import Section

from ...common import Address, function_like_format
from ..s01_symbols_table import model as parent
from .model import Function, FunctionRegionCode, FunctionRegionData, FunctionRegions, Functions


def parse(parent_functions: parent.Functions, elffile: ELFFile) -> Functions:
    text_section = cast(Section | None, elffile.get_section_by_name(".text"))  # type: ignore
    if text_section is None:
        raise ValueError("Section `.text` is missing.")

    text = cast(bytes, text_section.data())  # type: ignore
    text_offset = cast(int, text_section.header["sh_addr"])  # pyright: ignore[reportUnknownMemberType]

    functions = [parse_function(parent_function, text, text_offset) for parent_function in parent_functions.inner]

    return Functions(functions)


def parse_function(parent_function: parent.Function, text: bytes, text_offset: Address) -> Function:
    text_start = parent_function.address - text_offset
    text_end = text_start + parent_function.size

    if not 0 <= text_start <= text_end <= len(text):
        raise ValueError(f"Function {function_like_format(parent_function)} overflows text boundary.")
    function_text = text[text_start:text_end]

    regions = parse_function_regions(parent_function.regions, function_text)

    return Function(
        address=parent_function.address,
        size=parent_function.size,
        names=parent_function.names,
        regions=regions,
    )


def parse_function_regions(parent_function_regions: parent.FunctionRegions, function_text: bytes) -> FunctionRegions:
    function_regions_ = [
        parse_function_region(parent_function_region, function_text)
        for parent_function_region in parent_function_regions.inner
    ]

    return FunctionRegions(function_regions_)


def parse_function_region(
    parent_function_region: parent.FunctionRegion, function_text: bytes
) -> FunctionRegionCode | FunctionRegionData:
    function_offset = parent_function_region.function_offset

    function_text_start = function_offset
    function_text_end = function_text_start + parent_function_region.size

    if not 0 <= function_text_start <= function_text_end <= len(function_text):
        raise ValueError(f"Function region at {parent_function_region.function_offset} overflow function")
    content = function_text[function_text_start:function_text_end]

    if parent_function_region.code_data:
        return FunctionRegionCode(
            function_offset=function_offset,
            opcodes=content,
        )
    else:
        return FunctionRegionData(
            function_offset=function_offset,
            data=content,
        )
