from pathlib import Path
from typing import Annotated

from rich.markup import escape
from rich.panel import Panel
from rich.rule import Rule
from rich.style import Style
from rich.table import Column, Table
from rich.text import Text
from rich.tree import Tree
from typer import Argument, Typer

from .._cli import console, function_names_format
from .parse import parse_path
from .program.model import Entrypoints, Function, Functions, Program

app = Typer()


@app.command()
def summary(elf_path: Path, config_path: Annotated[Path | None, Argument()] = None) -> None:
    with console.status("Parsing..."):
        program = parse_path(elf_path, config_path)

    _functions(program.functions)
    _entrypoints(program.entrypoints)
    _call_tree(program)
    _stack_size(program.stack_size)


def _functions(functions: Functions) -> None:
    table = Table(
        Column("Address"),
        Column(
            "Names",
            overflow="fold",
            no_wrap=False,
        ),
        Column("Stack cumulative (B)"),
        Column("Stack self (B)"),
        Column("Direct call addresses"),
        title="Functions",
    )

    for function in functions.inner:
        table.add_row(
            Text(f"0x{function.address:04X}"),
            function_names_format(function.names),
            Text(f"{function.stack_grow_cumulative}"),
            Text(f"{function.stack_grow}"),
            Text(", ".join(f"0x{call_address:04X}" for call_address in function.call_addresses)),
        )

    console.print(table)


def _entrypoints(entrypoints: Entrypoints) -> None:
    console.print(Rule("Entrypoints"))

    tree = Tree(
        Text(
            f"Whole program ({entrypoints.stack_size}B stack size)",
            style="blue",
        )
    )

    for entrypoints_priority_group in entrypoints.priority_groups:
        entrypoints_priority_group_node = tree.add(
            Text(
                f"{escape(entrypoints_priority_group.name)} ({entrypoints_priority_group.stack_grow}B stack grow)",
                style="yellow",
            ),
        )

        stack_grow_max = max(entrypoint.stack_grow for entrypoint in entrypoints_priority_group.entrypoints)

        for entrypoint in entrypoints_priority_group.entrypoints:
            entrypoints_priority_group_node.add(
                Text(f"{escape(entrypoint.name)} @ 0x{entrypoint.address:04X} ({entrypoint.stack_grow}B stack grow)"),
                style=Style(
                    color="green",
                    dim=entrypoint.stack_grow < stack_grow_max,
                ),
            )

    console.print(tree)


def _call_tree(program: Program) -> None:
    console.print(Rule("Call Tree"))

    def handle_function_node(parent: Tree, function: Function, hot: bool) -> None:
        # add self to the tree
        node = parent.add(
            (
                function_names_format(function.names)
                + Text(
                    f" @ 0x{function.address:04X} "
                    f"({function.stack_grow_cumulative}B stack cumulative) "
                    f"({function.stack_grow}B stack self)"
                )
            ),
            # dim non-hot path
            style=Style(
                color="blue",
                dim=not hot,
            ),
        )

        if not function.call_addresses:
            return

        # resolve hottest path
        call_functions = [program.functions.by_address[call_address] for call_address in function.call_addresses]
        call_stack_grow_cumulative_max = max(call_function.stack_grow_cumulative for call_function in call_functions)

        # add children to the tree
        # NOTE: shouldn't blow up, as we have guaranteed (by the model) that calls do not cycle
        for call_function in call_functions:
            handle_function_node(
                node, call_function, call_function.stack_grow_cumulative >= call_stack_grow_cumulative_max
            )

    tree = Tree(
        Text(
            f"Whole program ({program.stack_size}B stack size)",
            style="blue",
        )
    )

    for entrypoints_priority_group in program.entrypoints.priority_groups:
        entrypoints_priority_group_node = tree.add(
            Text(
                f"{escape(entrypoints_priority_group.name)} ({entrypoints_priority_group.stack_grow}B stack grow)",
                style="yellow",
            ),
        )

        for entrypoint in entrypoints_priority_group.entrypoints:
            entrypoint_node = entrypoints_priority_group_node.add(
                Text(f"{escape(entrypoint.name)} @ 0x{entrypoint.address:04X} ({entrypoint.stack_grow}B stack grow)"),
                # dim out if this is not the hot path
                style=Style(
                    color="green",
                    dim=entrypoint.stack_grow >= entrypoints_priority_group.stack_grow,
                ),
            )

            # add function nodes, its always the hottest path
            handle_function_node(entrypoint_node, program.functions.by_address[entrypoint.address], True)

    console.print(tree)


def _stack_size(stack_size: int) -> None:
    console.print(
        Panel(
            Text(f"{stack_size}"),
            title="Whole program total stack usage (B)",
            style="green",
        )
    )


if __name__ == "__main__":
    app()
