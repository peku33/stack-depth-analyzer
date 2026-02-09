from importlib import metadata

from typer import Typer

from . import _cli as _  # noqa: F401
from .elf_arm_thumbv6m_cortex_m0.__main__ import app as elf_arm_thumbv6m_cortex_m0

app = Typer()

app.add_typer(
    elf_arm_thumbv6m_cortex_m0,
    name="elf_arm_thumbv6m_cortex_m0",
)


@app.command()
def version() -> None:
    version_ = metadata.version("stack-depth-analyzer")

    print(version_)


if __name__ == "__main__":
    app()
