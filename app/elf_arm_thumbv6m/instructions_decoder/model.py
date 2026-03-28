from abc import ABC, abstractmethod
from collections.abc import Set
from dataclasses import dataclass
from enum import IntEnum
from itertools import chain
from typing import Self


class InstructionUndefined(Exception):
    def __init__(self) -> None:
        super().__init__("undefined instruction")


class InstructionUnpredictable(Exception):
    def __init__(self) -> None:
        super().__init__("unpredictable instruction")


class Register3(IntEnum):
    R0 = 0
    R1 = 1
    R2 = 2
    R3 = 3
    R4 = 4
    R5 = 5
    R6 = 6
    R7 = 7

    def __str__(self) -> str:
        return self.name


class Register4(IntEnum):
    R0 = 0
    R1 = 1
    R2 = 2
    R3 = 3
    R4 = 4
    R5 = 5
    R6 = 6
    R7 = 7
    R8 = 8
    R9 = 9
    R10 = 10
    R11 = 11
    R12 = 12
    SP = 13
    LR = 14
    PC = 15

    @classmethod
    def from_register3(cls, register3: Register3) -> Self:
        return cls(register3.value)

    def to_register3(self) -> Register3 | None:
        if self.value >= 8:
            return None

        return Register3(self.value)

    def __str__(self) -> str:
        return self.name


class Condition(IntEnum):
    EQ = 0
    NE = 1
    CS = 2
    CC = 3
    MI = 4
    PL = 5
    VS = 6
    VC = 7
    HI = 8
    LS = 9
    GE = 10
    LT = 11
    GT = 12
    LE = 13
    AL = 14

    def __str__(self) -> str:
        return self.name


class SysM(IntEnum):
    APSR = 0
    IAPSE = 1
    EAPSR = 2
    XPSR = 3
    IPSR = 5
    EPSR = 6
    IEPSR = 7
    MSP = 8
    PSP = 9
    PRIMASK = 16
    CONTROL = 20

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Instruction(ABC):
    @classmethod
    @abstractmethod
    def size(cls) -> int:
        pass

    @abstractmethod
    def __str__(self) -> str:
        pass

    @abstractmethod
    def affects_registers(self) -> Set[Register4]:
        pass


@dataclass(frozen=True)
class Instruction16(Instruction, ABC):
    @classmethod
    def size(cls) -> int:
        return 2


@dataclass(frozen=True)
class Instruction32(Instruction, ABC):
    @classmethod
    def size(cls) -> int:
        return 4


# common shared bases
@dataclass(frozen=True)
class BaseInstructionD3Imm(Instruction16):
    d: Register3
    imm: int

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.d)}


@dataclass(frozen=True)
class BaseInstructionDn3Imm(Instruction16):
    dn: Register3
    imm: int

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.dn)}


@dataclass(frozen=True)
class BaseInstructionD3M3(Instruction16):
    d: Register3
    m: Register3

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.d)}


@dataclass(frozen=True)
class BaseInstructionDn3M3(Instruction16):
    dn: Register3
    m: Register3

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.dn)}


@dataclass(frozen=True)
class BaseInstructionD3N3M3(Instruction16):
    d: Register3
    n: Register3
    m: Register3

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.d)}


@dataclass(frozen=True)
class BaseInstructionD3N3Imm(Instruction16):
    d: Register3
    n: Register3
    imm: int

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.d)}


@dataclass(frozen=True)
class BaseInstructionD3M3Imm(Instruction16):
    d: Register3
    m: Register3
    imm: int

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.d)}


@dataclass(frozen=True)
class BaseInstructionN3M3(Instruction16):
    n: Register3
    m: Register3

    def affects_registers(self) -> Set[Register4]:
        return set()


# concrete shared bases
@dataclass(frozen=True)
class BaseInstructionLdrImmediate(Instruction16):
    t: Register3
    n: Register3
    imm: int  # NOTE: multiplied by 1/2/4 depending on load_size

    @classmethod
    @abstractmethod
    def load_size(cls) -> int:
        pass

    def __str__(self) -> str:
        load_size = self.load_size()
        match load_size:
            case 1:
                suffix = "B"
            case 2:
                suffix = "H"
            case 4:
                suffix = ""
            case _:
                assert False

        return f"LDR{suffix} {self.t}, [{self.n}{f', #0x{(self.imm * load_size):0X}' if self.imm else ''}]"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.t)}


@dataclass(frozen=True)
class BaseInstructionLdrRegister(Instruction16):
    t: Register3
    n: Register3
    m: Register3

    @classmethod
    @abstractmethod
    def signed(cls) -> bool:
        pass

    @classmethod
    @abstractmethod
    def load_size(cls) -> int:
        pass

    def __str__(self) -> str:
        signed = self.signed()
        load_size = self.load_size()

        suffix = ""
        if signed:
            suffix += "S"
        match load_size:
            case 1:
                suffix += "B"
            case 2:
                suffix += "H"
            case 4:
                pass
            case _:
                assert False

        return f"LDR{suffix} {self.t}, [{self.n}, {self.m}]"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.t)}


@dataclass(frozen=True)
class BaseInstructionStrImmediate(Instruction16):
    t: Register3
    n: Register3
    imm: int  # NOTE: multiplied by 1/2/4 depending on store_size

    @classmethod
    @abstractmethod
    def store_size(cls) -> int:
        pass

    def __str__(self) -> str:
        store_size = self.store_size()
        match store_size:
            case 1:
                suffix = "B"
            case 2:
                suffix = "H"
            case 4:
                suffix = ""
            case _:
                assert False

        return f"STR{suffix} {self.t}, [{self.n}{f', #0x{(self.imm * store_size):0X}' if self.imm else ''}]"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class BaseInstructionStrRegister(Instruction16):
    t: Register3
    n: Register3
    m: Register3

    @classmethod
    @abstractmethod
    def store_size(cls) -> int:
        pass

    def __str__(self) -> str:
        store_size = self.store_size()
        match store_size:
            case 1:
                suffix = "B"
            case 2:
                suffix = "H"
            case 4:
                suffix = ""
            case _:
                assert False

        return f"STR{suffix} {self.t}, [{self.n}, {self.m}]"

    def affects_registers(self) -> Set[Register4]:
        return set()


# concrete instructions
@dataclass(frozen=True)
class InstructionAdcRegisterT1(BaseInstructionDn3M3):
    # A6.7.1 ADC (register) T1

    def __str__(self) -> str:
        return f"ADCS {self.dn}, {self.m}"


@dataclass(frozen=True)
class InstructionAddImmediateT1(BaseInstructionD3N3Imm):
    # A6.7.2 ADD (immediate) T1

    def __str__(self) -> str:
        return f"ADDS {self.d}, {self.n}, #0x{self.imm:0X}"


@dataclass(frozen=True)
class InstructionAddImmediateT2(BaseInstructionDn3Imm):
    # A6.7.2 ADD (immediate) T2

    def __str__(self) -> str:
        return f"ADDS {self.dn}, #0x{self.imm:0X}"


@dataclass(frozen=True)
class InstructionAddRegisterT1(BaseInstructionD3N3M3):
    # A6.7.3 ADD (register) T1

    def __str__(self) -> str:
        return f"ADDS {self.d}, {self.n}, {self.m}"


@dataclass(frozen=True)
class InstructionAddRegisterT2(Instruction16):
    # A6.7.3 ADD (register) T2
    dn: Register4  # d == n, not SP
    m: Register4  # not SP

    def __post_init__(self) -> None:
        # these are handled as InstructionAddSpPlusRegisterT1/2
        assert self.dn is not Register4.SP
        assert self.m is not Register4.SP

        # this is Unpredictable
        assert not (self.dn is Register4.PC and self.m is Register4.PC)

    def __str__(self) -> str:
        return f"ADD {self.dn}, {self.m}"

    def affects_registers(self) -> Set[Register4]:
        return {self.dn}


@dataclass(frozen=True)
class InstructionAddSpPlusImmediateT1(BaseInstructionD3Imm):
    # A6.7.4 ADD (SP plus immediate) T1
    # NOTE: imm multiplied by 4

    def __str__(self) -> str:
        return f"ADD {self.d}, SP, #0x{(self.imm * 4):0X}"


@dataclass(frozen=True)
class InstructionAddSpPlusImmediateT2(Instruction16):
    # A6.7.4 ADD (SP plus immediate) T2
    imm: int  # NOTE: multiplied by 4

    def __str__(self) -> str:
        return f"ADD SP, SP, #0x{(self.imm * 4):0X}"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.SP}


@dataclass(frozen=True)
class InstructionAddSpPlusRegisterT1(Instruction16):
    # A6.7.5 ADD (SP plus register) T1
    dm: Register4

    def __str__(self) -> str:
        return f"ADD {self.dm}, SP, {self.dm}"

    def affects_registers(self) -> Set[Register4]:
        return {self.dm}


@dataclass(frozen=True)
class InstructionAddSpPlusRegisterT2(Instruction16):
    # A6.7.5 ADD (SP plus register) T2
    m: Register4

    def __post_init__(self) -> None:
        assert self.m is not Register4.SP  # encoding T1

    def __str__(self) -> str:
        return f"ADD SP, {self.m}"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.SP}


@dataclass(frozen=True)
class InstructionAdrT1(BaseInstructionD3Imm):
    # A6.7.6 ADR T1
    # TODO: add register/immediate/literal?
    # NOTE: imm multiplied by 4

    def __str__(self) -> str:
        return f"ADR {self.d}, PC + #0x{(self.imm * 4):0X}]"


@dataclass(frozen=True)
class InstructionAndRegisterT1(BaseInstructionDn3M3):
    # A6.7.7 AND (register) T1

    def __str__(self) -> str:
        return f"ANDS {self.dn}, {self.m}"


@dataclass(frozen=True)
class InstructionAsrImmediateT1(BaseInstructionD3M3Imm):
    # A6.7.8 ASR (immediate) T1

    def __str__(self) -> str:
        return f"ASRS {self.d}, {self.m}, #0x{self.imm:0X}"


@dataclass(frozen=True)
class InstructionAsrRegisterT1(BaseInstructionDn3M3):
    # A6.7.9 ASR (register) T1

    def __str__(self) -> str:
        return f"ASRS {self.dn}, {self.m}"


@dataclass(frozen=True)
class InstructionBT1(Instruction16):
    # A6.7.10 B T1
    # TODO: add register/immediate/literal?
    cond: Condition
    imm: int  # NOTE: multiplied by 2

    def __post_init__(self) -> None:
        assert self.cond is not Condition.AL  # is UDF

    def __str__(self) -> str:
        return f"B{self.cond} PC + 0x{(self.imm * 2):0X}"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.PC}


@dataclass(frozen=True)
class InstructionBT2(Instruction16):
    # A6.7.10 B T2
    # TODO: add register/immediate/literal?
    imm: int  # NOTE: multiplied by 2

    def __str__(self) -> str:
        return f"B PC + 0x{(self.imm * 2):0X}"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.PC}


@dataclass(frozen=True)
class InstructionBicRegisterT1(BaseInstructionDn3M3):
    # A6.7.11 BIC (register) T1

    def __str__(self) -> str:
        return f"BICS {self.dn}, {self.m}"


@dataclass(frozen=True)
class InstructionBkptT1(Instruction16):
    # A6.7.12 BKPT T1
    # TODO: add register/immediate/literal?
    imm: int

    def __str__(self) -> str:
        return f"BKPT #0x{self.imm:0X}"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionBlT1(Instruction32):
    # A6.7.13 BL T1
    # TODO: add register/immediate/literal?
    imm: int  # NOTE: multiplied by 2

    def __str__(self) -> str:
        return f"BL PC + 0x{(self.imm * 2):0X}"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.LR, Register4.PC}


@dataclass(frozen=True)
class InstructionBlxRegisterT1(Instruction16):
    # A6.7.14 BLX (register) T1
    m: Register4

    def __post_init__(self) -> None:
        assert self.m is not Register4.PC

    def __str__(self) -> str:
        return f"BLX {self.m}"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.LR, Register4.PC}


@dataclass(frozen=True)
class InstructionBxT1(Instruction16):
    # A6.7.15 BX T1
    # TODO: add register/immediate/literal?
    m: Register4

    def __post_init__(self) -> None:
        assert self.m is not Register4.PC

    def __str__(self) -> str:
        return f"BX {self.m}"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.PC}


@dataclass(frozen=True)
class InstructionCmnRegisterT1(BaseInstructionN3M3):
    # A6.7.16 CMN (register) T1

    def __str__(self) -> str:
        return f"CMN {self.n}, {self.m}"


@dataclass(frozen=True)
class InstructionCmpImmediateT1(Instruction16):
    # A6.7.17 CMP (immediate) T1
    n: Register3
    imm: int

    def __str__(self) -> str:
        return f"CMP {self.n}, #0x{self.imm:0X}"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionCmpRegisterT1(BaseInstructionN3M3):
    # A6.7.18 CMP (register) T1

    def __str__(self) -> str:
        return f"CMP {self.n}, {self.m}"


@dataclass(frozen=True)
class InstructionCmpRegisterT2(Instruction16):
    # A6.7.18 CMP (register) T2
    n: Register4
    m: Register4

    def __post_init__(self) -> None:
        assert not (self.n.value < 8 and self.m.value < 8)
        assert not (self.n is Register4.PC or self.m is Register4.PC)

    def __str__(self) -> str:
        return f"CMP {self.n}, {self.m}"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionDmbT1(Instruction32):
    # A6.7.21 DMB T1
    # TODO: add register/immediate/literal?
    option: int

    def __str__(self) -> str:
        return f"DMB #0x{self.option:0X}"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionDsbT1(Instruction32):
    # A6.7.22 DSB T1
    # TODO: add register/immediate/literal?
    option: int

    def __str__(self) -> str:
        return f"DSB #0x{self.option:0X}"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionEorRegisterT1(BaseInstructionDn3M3):
    # A6.7.23 EOR (register) T1

    def __str__(self) -> str:
        return f"EORS {self.dn}, {self.m}"


@dataclass(frozen=True)
class InstructionIsbT1(Instruction32):
    # A6.7.24 ISB T1
    # TODO: add register/immediate/literal?
    option: int

    def __str__(self) -> str:
        return f"ISB #0x{self.option:0X}"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionLdmT1(Instruction16):
    # A6.7.25 LDM, LDMIA, LDMFD T1
    # TODO: add register/immediate/literal?
    n: Register3
    registers: Set[Register3]

    def __post_init__(self) -> None:
        assert self.registers

    def __str__(self) -> str:
        return f"LDM {self.n}{'!' if self.n not in self.registers else ''}, {{{''.join(
            str(register3) for register3 in Register3 if register3 in self.registers
        )}}}"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(register) for register in chain([self.n], self.registers)}


@dataclass(frozen=True)
class InstructionLdrImmediateT1(BaseInstructionLdrImmediate):
    # A6.7.26 LDR (immediate) T1

    @classmethod
    def load_size(cls) -> int:
        return 4


@dataclass(frozen=True)
class InstructionLdrImmediateT2(Instruction16):
    # A6.7.26 LDR (immediate) T2
    t: Register3
    imm: int  # NOTE: multiplied by 4

    def __str__(self) -> str:
        return f"LDR {self.t}, [SP{f', #0x{(self.imm * 4):0X}' if self.imm else ''}]"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.t)}


@dataclass(frozen=True)
class InstructionLdrLiteralT1(Instruction16):
    # A6.7.27 LDR (literal) T1
    t: Register3
    imm: int  # NOTE: multiplied by 4

    def __str__(self) -> str:
        return f"LDR {self.t}, PC + 0x{(self.imm * 4):0X}"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.t)}


@dataclass(frozen=True)
class InstructionLdrRegisterT1(BaseInstructionLdrRegister):
    # A6.7.28 LDR (register) T1

    @classmethod
    def signed(cls) -> bool:
        return False

    @classmethod
    def load_size(cls) -> int:
        return 4


@dataclass(frozen=True)
class InstructionLdrbImmediateT1(BaseInstructionLdrImmediate):
    # A6.7.29 LDRB (immediate) T1

    @classmethod
    def load_size(cls) -> int:
        return 1


@dataclass(frozen=True)
class InstructionLdrbRegisterT1(BaseInstructionLdrRegister):
    # A6.7.30 LDRB (register) T1

    @classmethod
    def signed(cls) -> bool:
        return False

    @classmethod
    def load_size(cls) -> int:
        return 1


@dataclass(frozen=True)
class InstructionLdrhImmediateT1(BaseInstructionLdrImmediate):
    # A6.7.31 LDRH (immediate) T1

    @classmethod
    def load_size(cls) -> int:
        return 2


@dataclass(frozen=True)
class InstructionLdrhRegisterT1(BaseInstructionLdrRegister):
    # A6.7.32 LDRH (register) T1

    @classmethod
    def signed(cls) -> bool:
        return False

    @classmethod
    def load_size(cls) -> int:
        return 2

    def __str__(self) -> str:
        return f"LDRH {self.t}, [{self.n}, {self.m}]"


@dataclass(frozen=True)
class InstructionLdrsbRegisterT1(BaseInstructionLdrRegister):
    # A6.7.33 LDRSB (register) T1

    @classmethod
    def signed(cls) -> bool:
        return True

    @classmethod
    def load_size(cls) -> int:
        return 1


@dataclass(frozen=True)
class InstructionLdrshRegisterT1(BaseInstructionLdrRegister):
    # A6.7.34 LDRSH (register) T1

    @classmethod
    def signed(cls) -> bool:
        return True

    @classmethod
    def load_size(cls) -> int:
        return 2


@dataclass(frozen=True)
class InstructionLslImmediateT1(BaseInstructionD3M3Imm):
    # A6.7.35 LSL (immediate) T1
    def __post_init__(self) -> None:
        assert self.imm != 0

    def __str__(self) -> str:
        return f"LSLS {self.d}, {self.m}, #0x{self.imm:0X}"


@dataclass(frozen=True)
class InstructionLslRegisterT1(BaseInstructionDn3M3):
    # A6.7.36 LSL (register) T1

    def __str__(self) -> str:
        return f"LSLS {self.dn}, {self.m}"


@dataclass(frozen=True)
class InstructionLsrImmediateT1(BaseInstructionD3M3Imm):
    # A6.7.37 LSR (immediate) T1

    def __str__(self) -> str:
        return f"LSRS {self.d}, {self.m}, #0x{self.imm:0X}"


@dataclass(frozen=True)
class InstructionLsrRegisterT1(BaseInstructionDn3M3):
    # A6.7.38 LSR (register) T1

    def __str__(self) -> str:
        return f"LSRS {self.dn}, {self.m}"


@dataclass(frozen=True)
class InstructionMovImmediateT1(BaseInstructionD3Imm):
    # A6.7.39 MOV (immediate) T1

    def __str__(self) -> str:
        return f"MOVS {self.d}, #0x{self.imm:0X}"


@dataclass(frozen=True)
class InstructionMovRegisterT1(Instruction16):
    # A6.7.40 MOV (register) T1
    d: Register4
    m: Register4

    def __str__(self) -> str:
        return f"MOV {self.d}, {self.m}"

    def affects_registers(self) -> Set[Register4]:
        return {self.d}


@dataclass(frozen=True)
class InstructionMovRegisterT2(BaseInstructionD3M3):
    # A6.7.40 MOV (register) T2

    def __str__(self) -> str:
        return f"MOVS {self.d}, {self.m}"


@dataclass(frozen=True)
class InstructionMulT1(Instruction16):
    # A6.7.44 MUL T1
    # TODO: add register/immediate/literal?
    dm: Register3
    n: Register3

    def __str__(self) -> str:
        return f"MULS {self.dm}, {self.n}, {self.dm}"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.dm)}


@dataclass(frozen=True)
class InstructionMvnRegisterT1(BaseInstructionD3M3):
    # A6.7.45 MVN (register) T1

    def __str__(self) -> str:
        return f"MVNS {self.d}, {self.m}"


@dataclass(frozen=True)
class InstructionNopT1(Instruction16):
    # A6.7.47 NOP T1

    def __str__(self) -> str:
        return "NOP"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionOrrRegisterT1(BaseInstructionDn3M3):
    # A6.7.48 ORR (register) T1

    def __str__(self) -> str:
        return f"ORRS {self.dn}, {self.m}"


@dataclass(frozen=True)
class InstructionPopT1(Instruction16):
    # A6.7.49 POP T1
    pc: bool
    registers3: Set[Register3]

    def __post_init__(self) -> None:
        assert self.pc or self.registers3

    def __str__(self) -> str:
        return f"POP {{{', '.join(chain(
            (str(register3) for register3 in Register3 if register3 in self.registers3),
            [str(Register4.PC)] if self.pc else [],
        ))}}}"

    def affects_registers(self) -> Set[Register4]:
        return set(
            chain(
                [Register4.PC] if self.pc else [],
                (Register4.from_register3(register3) for register3 in self.registers3),
                [Register4.SP],
            )
        )


@dataclass(frozen=True)
class InstructionPushT1(Instruction16):
    # A6.7.50 PUSH T1
    lr: bool
    registers3: Set[Register3]

    def __post_init__(self) -> None:
        assert self.lr or self.registers3

    def __str__(self) -> str:
        return f"PUSH {{{', '.join(chain(
            (str(register3) for register3 in Register3 if register3 in self.registers3),
            [str(Register4.LR)] if self.lr else [],
        ))}}}"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.SP}


@dataclass(frozen=True)
class InstructionRevT1(BaseInstructionD3M3):
    # A6.7.51 REV T1
    # TODO: add register/immediate/literal?

    def __str__(self) -> str:
        return f"REV {self.d}, {self.m}"


@dataclass(frozen=True)
class InstructionRev16T1(BaseInstructionD3M3):
    # A6.7.52 REV16 T1
    # TODO: add register/immediate/literal?

    def __str__(self) -> str:
        return f"REV16 {self.d}, {self.m}"


@dataclass(frozen=True)
class InstructionRevshT1(BaseInstructionD3M3):
    # A6.7.53 REVSH T1
    # TODO: add register/immediate/literal?

    def __str__(self) -> str:
        return f"REVSH {self.d}, {self.m}"


@dataclass(frozen=True)
class InstructionRorRegisterT1(BaseInstructionDn3M3):
    # A6.7.54 ROR (register) T1

    def __str__(self) -> str:
        return f"RORS {self.dn}, {self.m}"


@dataclass(frozen=True)
class InstructionRsbImmediateT1(Instruction16):
    # A6.7.55 RSB (immediate) T1
    d: Register3
    n: Register3

    def __str__(self) -> str:
        return f"RSBS {self.d}, {self.n}, #0"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.d)}


@dataclass(frozen=True)
class InstructionSbcRegisterT1(BaseInstructionDn3M3):
    # A6.7.56 SBC (register) T1

    def __str__(self) -> str:
        return f"SBCS {self.dn}, {self.m}"


@dataclass(frozen=True)
class InstructionSevT1(Instruction16):
    # A6.7.57 SEV T1

    def __str__(self) -> str:
        return "SEV"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionStmT1(Instruction16):
    # A6.7.58 STM, STMIA, STMEA T1
    # TODO: add register/immediate/literal?
    n: Register3
    registers: Set[Register3]

    def __post_init__(self) -> None:
        assert self.registers

    def __str__(self) -> str:
        return f"STM {self.n}!, {{{''.join(
            str(register3) for register3 in Register3 if register3 in self.registers
        )}}}"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.from_register3(self.n)}


@dataclass(frozen=True)
class InstructionStrImmediateT1(BaseInstructionStrImmediate):
    # A6.7.59 STR (immediate) T1

    @classmethod
    def store_size(cls) -> int:
        return 4


@dataclass(frozen=True)
class InstructionStrImmediateT2(Instruction16):
    # A6.7.59 STR (immediate) T2
    t: Register3
    imm: int  # NOTE: multiplied by 4

    def __str__(self) -> str:
        return f"STR {self.t}, [SP{f', #0x{(self.imm * 4):0X}' if self.imm else ''}]"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionStrRegisterT1(BaseInstructionStrRegister):
    # A6.7.60 STR (register) T1

    @classmethod
    def store_size(cls) -> int:
        return 4


@dataclass(frozen=True)
class InstructionStrbImmediateT1(BaseInstructionStrImmediate):
    # A6.7.61 STRB (immediate) T1

    @classmethod
    def store_size(cls) -> int:
        return 1


@dataclass(frozen=True)
class InstructionStrbRegisterT1(BaseInstructionStrRegister):
    # A6.7.62 STRB (register) T1

    @classmethod
    def store_size(cls) -> int:
        return 1


@dataclass(frozen=True)
class InstructionStrhImmediateT1(BaseInstructionStrImmediate):
    # A6.7.63 STRH (immediate) T1

    @classmethod
    def store_size(cls) -> int:
        return 2


@dataclass(frozen=True)
class InstructionStrhRegisterT1(BaseInstructionStrRegister):
    # A6.7.64 STRH (register) T1

    @classmethod
    def store_size(cls) -> int:
        return 2


@dataclass(frozen=True)
class InstructionSubImmediateT1(BaseInstructionD3N3Imm):
    # A6.7.65 SUB (immediate) T1

    def __str__(self) -> str:
        return f"SUBS {self.d}, {self.n}, #0x{self.imm:0X}"


@dataclass(frozen=True)
class InstructionSubImmediateT2(BaseInstructionDn3Imm):
    # A6.7.65 SUB (immediate) T2

    def __str__(self) -> str:
        return f"SUBS {self.dn}, #0x{self.imm:0X}"


@dataclass(frozen=True)
class InstructionSubRegisterT1(BaseInstructionD3N3M3):
    # A6.7.66 SUB (register) T1

    def __str__(self) -> str:
        return f"SUBS {self.d}, {self.n}, {self.m}"


@dataclass(frozen=True)
class InstructionSubSpMinusImmediateT1(Instruction16):
    # A6.7.67 SUB (SP minus immediate) T1
    imm: int  # NOTE: multiplied by 4

    def __str__(self) -> str:
        return f"SUB SP, SP, #0x{(self.imm * 4):0X}"

    def affects_registers(self) -> Set[Register4]:
        return {Register4.SP}


@dataclass(frozen=True)
class InstructionSvcT1(Instruction16):
    # A6.7.68 SVC T1
    # TODO: add register/immediate/literal?
    imm: int

    def __str__(self) -> str:
        return f"SVC #0x{self.imm:0X}"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionSxtbT1(BaseInstructionD3M3):
    # A6.7.69 SXTB T1
    # TODO: add register/immediate/literal?

    def __str__(self) -> str:
        return f"SXTB {self.d}, {self.m}"


@dataclass(frozen=True)
class InstructionSxthT1(BaseInstructionD3M3):
    # A6.7.70 SXTH T1
    # TODO: add register/immediate/literal?

    def __str__(self) -> str:
        return f"SXTH {self.d}, {self.m}"


@dataclass(frozen=True)
class InstructionTstRegisterT1(BaseInstructionN3M3):
    # A6.7.71 TST (register) T1

    def __str__(self) -> str:
        return f"TST {self.n}, {self.m}"


@dataclass(frozen=True)
class InstructionUdfT1(Instruction16):
    # A6.7.72 UDF T1
    # TODO: add register/immediate/literal?
    imm: int

    def __str__(self) -> str:
        return f"UDF #0x{self.imm:0X}"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionUdfT2(Instruction32):
    # A6.7.72 UDF T2
    # TODO: add register/immediate/literal?
    imm: int

    def __str__(self) -> str:
        return f"UDF.W #0x{self.imm:0X}"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionUxtbT1(BaseInstructionD3M3):
    # A6.7.73 UXTB T1
    # TODO: add register/immediate/literal?

    def __str__(self) -> str:
        return f"UXTB {self.d}, {self.m}"


@dataclass(frozen=True)
class InstructionUxthT1(BaseInstructionD3M3):
    # A6.7.74 UXTH T1
    # TODO: add register/immediate/literal?

    def __str__(self) -> str:
        return f"UXTH {self.d}, {self.m}"


@dataclass(frozen=True)
class InstructionWfeT1(Instruction16):
    # A6.7.75 WFE T1

    def __str__(self) -> str:
        return "WFE"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionWfiT1(Instruction16):
    # A6.7.76 WFI T1

    def __str__(self) -> str:
        return "WFI"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionYieldT1(Instruction16):
    # A6.7.77 YIELD T1

    def __str__(self) -> str:
        return "YIELD"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionCpsT1(Instruction16):
    # B4.2.1 CPS T1
    im: bool

    def __str__(self) -> str:
        return f"CPSI{'E' if self.im else 'D'} i"

    def affects_registers(self) -> Set[Register4]:
        return set()


@dataclass(frozen=True)
class InstructionMrsT1(Instruction32):
    # B4.2.2 MRS T1
    # TODO: add register/immediate/literal?
    d: Register4
    sys_m: SysM

    def __post_init__(self) -> None:
        assert self.d not in (Register4.SP, Register4.PC)

    def __str__(self) -> str:
        return f"MRS {self.d}, {self.sys_m}"

    def affects_registers(self) -> Set[Register4]:
        return {self.d}


@dataclass(frozen=True)
class InstructionMsrRegisterT1(Instruction32):
    # B4.2.3 MSR (register) T1
    sys_m: SysM
    n: Register4

    def __post_init__(self) -> None:
        assert self.n not in (Register4.SP, Register4.PC)

    def __str__(self) -> str:
        return f"MSR {self.sys_m}, {self.n}"

    def affects_registers(self) -> Set[Register4]:
        return set()
