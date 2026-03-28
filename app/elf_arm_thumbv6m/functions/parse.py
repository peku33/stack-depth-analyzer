from elftools.elf.elffile import ELFFile

from .config import Config
from .model import Function, Functions
from .s01_symbols_table.parse import parse as s01_symbols_table_parse
from .s02_text_regions.parse import parse as s02_text_enrich_regions
from .s03_instructions.parse import parse as s03_instructions_decode
from .s04_instructions_effect.parse import parse as s04_instructions_effect_resolve
from .s05_instructions_graph.parse import parse as s05_instructions_graph_resolve
from .s06_functions_effect.parse import parse as s06_functions_effect_resolve


def parse(elffile: ELFFile, config: Config) -> Functions:
    s01_symbols_table_functions = s01_symbols_table_parse(elffile)
    s02_text_enrich_regions_functions = s02_text_enrich_regions(s01_symbols_table_functions, elffile)
    s03_instructions_decode_functions = s03_instructions_decode(s02_text_enrich_regions_functions)
    s04_instructions_effect_functions = s04_instructions_effect_resolve(
        s03_instructions_decode_functions, config.instructions_effect
    )
    s05_instructions_graph_functions = s05_instructions_graph_resolve(s04_instructions_effect_functions)
    s06_functions_effect_functions = s06_functions_effect_resolve(s05_instructions_graph_functions)

    functions = [
        Function(
            address=function.address,
            names=function.names,
            stack_grow=function.stack_grow,
            call_addresses=function.call_addresses,
        )
        for function in s06_functions_effect_functions.inner
    ]

    return Functions(functions)
