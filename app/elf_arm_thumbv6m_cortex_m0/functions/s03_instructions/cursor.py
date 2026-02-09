from bisect import bisect
from collections.abc import Sequence
from dataclasses import dataclass, replace
from functools import cached_property
from typing import Self

from ...common import Address
from ...instructions_decoder.model import Instruction
from .model import Function, FunctionRegionData, FunctionRegionInstructions


@dataclass(frozen=True, kw_only=True)
class CursorFunction:
    function: Function

    def region_data(self, function_offset: Address) -> "CursorFunctionRegionData | None":
        assert function_offset >= 0

        # # region in function
        # find region index (possibly) containing function_offset
        function_regions_index = bisect(self._function_region_offsets, function_offset) - 1

        # get the region
        function_region = self.function.regions.inner[function_regions_index]

        # validate if this is a data region
        if type(function_region) is not FunctionRegionData:
            return None

        # validate region left boundary (should be guaranteed by bisect + fact that we always have region at offset 0)
        assert function_region.function_offset <= function_offset

        # validate region right boundary
        if function_offset >= function_region.function_offset + function_region.size:
            return None

        # # offset in region
        function_region_data_offset = function_offset - function_region.function_offset

        return CursorFunctionRegionData(
            cursor_function=self,
            function_regions_index=function_regions_index,
            function_region_data_offset=function_region_data_offset,
        )

    @cached_property
    def _function_region_offsets(self) -> Sequence[Address]:
        return [region.function_offset for region in self.function.regions.inner]


@dataclass(frozen=True, kw_only=True)
class CursorFunctionRegionInstructions:
    cursor_function: CursorFunction
    function_regions_index: int
    function_region_instructions_index: int

    def __post_init__(self) -> None:
        # validates function_regions_index is valid
        function_region_instructions = self._function_region_instructions

        # validates function_region_instructions_index is valid
        assert 0 <= self.function_region_instructions_index < len(function_region_instructions.instructions)

    @cached_property
    def _function_region_instructions(self) -> FunctionRegionInstructions:
        function_region = self.cursor_function.function.regions.inner[self.function_regions_index]
        assert type(function_region) is FunctionRegionInstructions
        return function_region

    @cached_property
    def _function_offset(self) -> Address:
        return (
            self._function_region_instructions.function_offset  # region from function
            + self._function_region_instructions.instructions_with_function_offsets[
                self.function_region_instructions_index
            ][
                1
            ]  # instruction from region
        )

    def function_offset(self) -> Address:
        return self._function_offset

    @cached_property
    def _function_end_offset(self) -> Address:
        return (
            self._function_region_instructions.function_offset  # region from function
            + self._function_region_instructions.instructions_with_function_offsets[
                self.function_region_instructions_index
            ][
                2
            ]  # instruction from region
        )

    def function_end_offset(self) -> Address:
        return self._function_end_offset

    @cached_property
    def _address(self) -> Address:
        return self.cursor_function.function.address + self._function_offset

    def address(self) -> Address:
        return self._address

    @cached_property
    def _instruction(self) -> Instruction:
        return self._function_region_instructions.instructions[self.function_region_instructions_index]

    def instruction(self) -> Instruction:
        return self._instruction

    @cached_property
    def _previous(self) -> Self | None:
        if self.function_region_instructions_index <= 0:
            return None

        return replace(
            self,
            function_region_instructions_index=self.function_region_instructions_index - 1,
        )

    def previous(self) -> Self | None:
        return self._previous

    @cached_property
    def _next(self) -> Self | None:
        if self.function_region_instructions_index + 1 >= len(self._function_region_instructions.instructions):
            return None

        return replace(
            self,
            function_region_instructions_index=self.function_region_instructions_index + 1,
        )

    def next(self) -> Self | None:
        return self._next


@dataclass(frozen=True, kw_only=True)
class CursorFunctionRegionData:
    cursor_function: CursorFunction
    function_regions_index: int
    function_region_data_offset: int

    def __post_init__(self) -> None:
        # validates function_regions_index is valid
        function_region_data = self._function_region_data

        # validates function_region_instructions_index is valid
        assert 0 <= self.function_region_data_offset < function_region_data.size

    @cached_property
    def _function_region_data(self) -> FunctionRegionData:
        function_region = self.cursor_function.function.regions.inner[self.function_regions_index]
        assert type(function_region) is FunctionRegionData
        return function_region

    def read_byte_unsigned(self) -> tuple[int, Self | None]:
        return self.read_unsigned(1)

    def read_halfword_unsigned(self) -> tuple[int, Self | None]:
        return self.read_unsigned(2)

    def read_word_unsigned(self) -> tuple[int, Self | None]:
        return self.read_unsigned(4)

    def read_unsigned(self, bytes_: int) -> tuple[int, Self | None]:
        # must be positive and be power of 2
        assert bytes_ > 0 and (bytes_ & (bytes_ - 1)) == 0

        # must be aligned
        if (
            self.cursor_function.function.address
            + self._function_region_data.function_offset
            + self.function_region_data_offset
        ) % bytes_ != 0:
            raise ValueError(f"Attempted unaligned {bytes_} bytes access for {self}.")

        function_region_data_offset_end = self.function_region_data_offset + bytes_

        # end must not overflow
        if function_region_data_offset_end > self._function_region_data.size:
            raise ValueError(f"Overflow for {bytes_} bytes access for {self}.")

        value_bytes = self._function_region_data.data[
            self.function_region_data_offset : function_region_data_offset_end
        ]
        value_int = int.from_bytes(
            value_bytes,
            "little",
            signed=False,
        )

        next_ = (
            replace(
                self,
                function_region_data_offset=function_region_data_offset_end,
            )
            if function_region_data_offset_end < self._function_region_data.size
            else None
        )

        return value_int, next_
