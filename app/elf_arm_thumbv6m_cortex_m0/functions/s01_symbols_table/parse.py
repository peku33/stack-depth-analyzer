from bisect import bisect_left, bisect_right
from collections.abc import Iterator, Mapping, Set
from itertools import chain, pairwise
from typing import Any, cast

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import Symbol, SymbolTableSection
from more_itertools import duplicates_everseen, first

from ...common import Address, function_format
from .demangle import name_demangle
from .model import Function, FunctionRegion, FunctionRegions, Functions


def parse(elffile: ELFFile) -> Functions:
    section = cast(
        SymbolTableSection | None,
        elffile.get_section_by_name(".symtab"),  # type: ignore
    )
    if section is None:
        raise ValueError(
            "Unable to find symbols table section (.symtab). "
            "It is required to get function boundaries and intra-function code/data regions. "
            "Most likely this is caused by your toolchain / build script stripping the elf. "
            "Please either don't strip the binary (as it won't affect final size/performance, it's not copied to elf). "
            "If you really need to strip it - do it after running this tool."
        )

    code_data_marker_by_address = dict[Address, bool]()  # {address: code} # (True - code, False - data)
    functions_by_address = dict[Address, tuple[int, set[str]]]()  # {address: (size, names)}

    # scan through all symbols and fill helper structures
    for symbol in cast(Iterator[Symbol], section.iter_symbols()):  # type: ignore
        name = cast(str, symbol.name)

        entry = cast(Mapping[str, Any], symbol.entry)

        address = cast(Address, entry["st_value"])
        size = cast(int, entry["st_size"])

        info = cast(Mapping[str, Any], entry["st_info"])

        # handle code/data markers
        code_data: bool | None
        match name:
            case "$t":
                code_data = True
            case "$d":
                code_data = False
            case _:
                code_data = None

        if code_data is not None:
            # code/data markers will have STT_NOTYPE
            if info["type"] != "STT_NOTYPE":
                raise ValueError(f"Unexpected type for code/data marker (`{info["type"]}`) at 0x{address:04X}.")

            # regions are always halfword aligned
            if address % 2 != 0:
                raise ValueError(f"Unaligned code/data marker at address 0x{address:04X}.")

            # must not repeat
            if address in code_data_marker_by_address:
                raise ValueError(f"Duplicated code/data marker at address 0x{address:04X}.")

            # add to collection
            code_data_marker_by_address[address] = code_data
        else:
            # skip non-functions
            if info["type"] != "STT_FUNC":
                continue

            # function addresses are always 16b aligned
            # lsb is used to signify arm(0)/thumb(1) instruction set for BX
            # thumbv6m supports only thumb, arm code is never present
            # we clear last bit to have actual address, not address + mode
            if address & 1 != 1:
                raise ValueError(f"Thumb bit not set for {function_format(address, {name})}.")
            address &= ~1

            # skip zero-sized functions (eg. empty __pre_init)
            # they don't contain any code, so won't affect stack etc
            if size <= 0:
                continue

            # demangle symbols-table specific name
            name = name_demangle(name)

            # some entries are repeated (ex. multiple exception names pointing same default handler)
            if (function_ := functions_by_address.get(address)) is not None:
                # some details should match between occurences (ex. size)
                size_, names = function_
                if size_ != size:
                    raise ValueError(f"Size mismatch between symbols at 0x{address:04X}.")

                # some details are different (eg. names)
                names.add(name)
            else:
                # this is newly seen
                functions_by_address[address] = (
                    size,
                    {name},
                )

    # prepare function to resolve code/data regions in functions
    # prepare sorted addresses
    code_data_marker_addresses = sorted(code_data_marker_by_address)

    def resolve_function_regions(
        address: Address,
        size: int,
        *,
        names: Set[str],
    ) -> FunctionRegions:
        # find all $t/$d markers within the function
        code_data_marker_addresses_index_first = bisect_left(
            code_data_marker_addresses,
            address,
        )
        code_data_marker_addresses_index_last = bisect_right(
            code_data_marker_addresses,
            address + size - 1,
        )

        code_data_marker_function_offsets = {  # {function_offset: code}
            code_data_marker_address - address: code_data_marker_by_address[code_data_marker_address]
            for code_data_marker_address in code_data_marker_addresses[
                code_data_marker_addresses_index_first:code_data_marker_addresses_index_last
            ]
        }

        match first(code_data_marker_function_offsets.items(), None):
            case None:
                # some compilers (like GCC) tend to ignore code/data markers for some simple functions
                # lets fix it, by marking whole function as code
                code_data_marker_function_offsets = {0: True}
            case (0, True):
                pass
            case _:
                raise ValueError(f"Function {function_format(address, names)} does not start with code marker.")

        def resolve_function_region(function_offset: int, function_offset_next: int, code_data: bool) -> FunctionRegion:
            # positive offset and size guaranteed by logic
            assert function_offset >= 0
            assert function_offset_next > function_offset

            # region must be [0, function_size]
            size_ = function_offset_next - function_offset
            assert 0 <= function_offset + size_ <= size

            return FunctionRegion(
                function_offset=function_offset,
                size=size_,
                code_data=code_data,
            )

        # find all pairs, including from last to end
        function_regions_ = [
            resolve_function_region(function_offset, function_offset_next, cast(bool, code_data))
            for ((function_offset, code_data), (function_offset_next, _)) in pairwise(
                chain(code_data_marker_function_offsets.items(), [(size, None)])
            )
        ]

        return FunctionRegions(function_regions_)

    # sort functions_by_address by address
    functions_by_address = {address: functions_by_address[address] for address in sorted(functions_by_address.keys())}

    # make sure functions don't overlap
    for (address, (size, names)), (address_next, (_, names_next)) in pairwise(functions_by_address.items()):
        if address + size > address_next:
            raise ValueError(
                f"Function {function_format(address, names)}, size {size} overlaps with next "
                f"{function_format(address_next, names_next)}."
            )

    # function names must be unique
    names_duplicate = set(duplicates_everseen(name for _, names in functions_by_address.values() for name in names))
    if names_duplicate:
        raise ValueError(
            f"Function names duplicated: {", ".join(f"`{name_duplicate}`" for name_duplicate in names_duplicate)}."
        )

    functions_ = [
        Function(
            address=address,
            size=size,
            names=names,
            regions=resolve_function_regions(
                address,
                size,
                names=names,
            ),
        )
        for address, (size, names) in functions_by_address.items()
    ]

    return Functions(functions_)
