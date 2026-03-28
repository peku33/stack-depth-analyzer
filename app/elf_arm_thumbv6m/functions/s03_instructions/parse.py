from ...instructions_decoder.parse import instructions_from_opcodes
from ..s02_text_regions import model as parent
from .model import Function, FunctionRegionData, FunctionRegionInstructions, FunctionRegions, Functions


def parse(parent_functions: parent.Functions) -> Functions:
    functions = [parse_function(parent_function) for parent_function in parent_functions.inner]

    return Functions(functions)


def parse_function(parent_function: parent.Function) -> Function:
    regions = parse_function_regions(parent_function.regions)

    return Function(
        address=parent_function.address,
        size=parent_function.size,
        names=parent_function.names,
        regions=regions,
    )


def parse_function_regions(
    parent_function_regions: parent.FunctionRegions,
) -> FunctionRegions:
    inner = [parse_function_region(parent_function_region) for parent_function_region in parent_function_regions.inner]

    return FunctionRegions(inner)


def parse_function_region(
    parent_function_region: parent.FunctionRegionCode | parent.FunctionRegionData,
) -> FunctionRegionInstructions | FunctionRegionData:
    match parent_function_region:
        case parent.FunctionRegionCode(
            function_offset=function_offset,
            opcodes=opcodes,
        ):
            instructions = list(instructions_from_opcodes(opcodes))

            # parsed instructions must cover the region exactly
            assert sum(instruction.size() for instruction in instructions) == len(opcodes)

            return FunctionRegionInstructions(
                function_offset=function_offset,
                instructions=instructions,
            )

        case parent.FunctionRegionData(
            function_offset=function_offset,
            data=data,
        ):
            return FunctionRegionData(
                function_offset=function_offset,
                data=data,
            )
        case _:
            assert False
