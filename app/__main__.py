from importlib import metadata

from typer import Typer

from . import _cli as _  # noqa: F401
from .elf_arm_thumbv6m.__main__ import app as elf_arm_thumbv6m
from .elf_arm_thumbv6m_cortex_m0.__main__ import app as elf_arm_thumbv6m_cortex_m0

app = Typer()

app.add_typer(
    elf_arm_thumbv6m,
    name="elf_arm_thumbv6m",
    help=(
        "(Virtual) ARM ThumbV6-M architecture. Requires manual entrypoint configuration. "
        "Used for raw binaries compiled for no specific MCU family (usually for testing and experiments). "
        "For Cortex-M0(+), use `elf_arm_thumbv6m_cortex_m0` instead."
    ),
)
app.add_typer(
    elf_arm_thumbv6m_cortex_m0,
    name="elf_arm_thumbv6m_cortex_m0",
    help=(
        "ARM ThumbV6-M for Cortex-M0(+) MCUs. "
        "Provides semi-automatic entrypoint detection on top of `elf_arm_thumbv6m`. "
        "This is recommended for work with MCUs like STM32F0/G0/C0, etc."
    ),
)


@app.command()
def version() -> None:
    version_ = metadata.version("stack-depth-analyzer")

    print(version_)


if __name__ == "__main__":
    app()
