from dataclasses import dataclass

from ...common import Address
from ...instructions_decoder.model import (
    Instruction,
    InstructionAddSpPlusImmediateT2,
    InstructionAddSpPlusRegisterT1,
    InstructionMovRegisterT1,
    InstructionMsrRegisterT1,
    InstructionPopT1,
    InstructionPushT1,
    InstructionSubSpMinusImmediateT1,
    Register4,
    SysM,
)
from ..s03_instructions.cursor import CursorFunctionRegionInstructions


@dataclass(frozen=True)
class Effect:
    add: int  # equivalent of SP = SP + add


class ResolveException(Exception):
    _address: Address

    def __init__(self, address: Address, message: str) -> None:
        super().__init__(message)

        self._address = address

    @property
    def address(self) -> Address:
        return self._address


def resolve(cursor_function_region_instructions: CursorFunctionRegionInstructions) -> Effect | None:
    address = cursor_function_region_instructions.address()
    instruction = cursor_function_region_instructions.instruction()

    match instruction:
        case InstructionAddSpPlusImmediateT2():
            return Effect(instruction.imm * 4)
        case InstructionAddSpPlusRegisterT1():
            if instruction.dm is Register4.SP:
                # SP = SP + SP ???
                raise ResolveUnsupportedInstructionException(instruction, address)

            return None
        case InstructionMovRegisterT1():
            if instruction.d is Register4.SP:
                # SP = m
                raise ResolveUnsupportedInstructionException(instruction, address)

            return None
        case InstructionPopT1():
            add = (int(instruction.pc) + len(instruction.registers3)) * 4

            return Effect(add)
        case InstructionPushT1():
            add = (int(instruction.lr) + len(instruction.registers3)) * -4

            return Effect(add)
        case InstructionMsrRegisterT1():
            if instruction.sys_m is SysM.CONTROL:
                # switching SPSEL
                raise ResolveUnsupportedInstructionException(instruction, address)

            if instruction.sys_m in (SysM.MSP, SysM.PSP):
                # MSP/PSP = n
                raise ResolveUnsupportedInstructionException(instruction, address)

            return None
        case InstructionSubSpMinusImmediateT1():
            return Effect(instruction.imm * -4)
        case _:
            # other instructions should not have affect on SP. if they have - we've missed something in this list
            assert Register4.SP not in instruction.affects_registers()

            return None


class ResolveUnsupportedInstructionException(ResolveException):
    _instruction: Instruction

    def __init__(self, instruction: Instruction, address: Address) -> None:
        super().__init__(address, self._format_message(instruction, address))

        self._instruction = instruction

    @classmethod
    def _format_message(cls, instruction: Instruction, address: Address) -> str:
        return (
            f"Unsupported instruction affecting stack pointer ({instruction}) encountered at address 0x{address:04X}.\n"
            "This usually means one of the following:\n"
            " - The program is running an preemptive RTOS with multiple stacks. This is not supported for now.\n"
            " - There are dynamic stack allocations happening. They are not supported for now.\n"
            "If you believe that this stack pointer effect can be resolved automatically, you can open an issue, "
            "providing as many details as possible."
        )
