from collections.abc import Callable, Collection
from dataclasses import dataclass
from functools import partial

from ...common import Address
from ...instructions_decoder.model import (
    BaseInstructionLdrImmediate,
    Condition,
    Instruction,
    InstructionAddRegisterT2,
    InstructionAddSpPlusRegisterT1,
    InstructionBlT1,
    InstructionBlxRegisterT1,
    InstructionBT1,
    InstructionBT2,
    InstructionBxT1,
    InstructionLdrLiteralT1,
    InstructionLslImmediateT1,
    InstructionMovRegisterT1,
    InstructionPopT1,
    InstructionUdfT1,
    InstructionUdfT2,
    Register4,
)
from ..s03_instructions.cursor import CursorFunctionRegionData, CursorFunctionRegionInstructions
from .config import ConfigCallOverrides


@dataclass(frozen=True, kw_only=True)
class EffectBranch:
    conditional: bool
    target_function_offsets: frozenset[Address]  # relative to function address

    def __post_init__(self) -> None:
        # must have at least one target
        assert self.target_function_offsets

        # targets must be aligned
        assert all(target_function_offset % 2 == 0 for target_function_offset in self.target_function_offsets)


@dataclass(frozen=True, kw_only=True)
class EffectCall:
    target_addresses: frozenset[Address]

    def __post_init__(self) -> None:
        # must call at least one target
        assert self.target_addresses

        # target addresses must be aligned
        assert all(target_address % 2 == 0 for target_address in self.target_addresses)


@dataclass(frozen=True, kw_only=True)
class EffectReturn:
    pass


@dataclass(frozen=True, kw_only=True)
class EffectInvalid:
    pass


type Effect = EffectBranch | EffectCall | EffectReturn | EffectInvalid


class ResolveException(Exception):
    _address: Address

    def __init__(self, address: Address, message: str):
        super().__init__(message)

        self._address = address

    @property
    def address(self) -> Address:
        return self._address


def resolve(
    cursor_function_region_instructions: CursorFunctionRegionInstructions, config_call_overrides: ConfigCallOverrides
) -> Effect | None:
    address = cursor_function_region_instructions.address()
    instruction = cursor_function_region_instructions.instruction()

    match instruction:
        case InstructionAddRegisterT2():
            if instruction.dn is Register4.PC:
                # PC = PC + register
                effect_branch = resolve_add_register_t2_pc(cursor_function_region_instructions)

                return effect_branch

            return None
        case InstructionAddSpPlusRegisterT1():
            if instruction.dm is Register4.PC:
                # PC = SP + PC ???

                # not seen in the wild
                raise ResolveUnsupportedInstructionException(instruction, address)
            else:
                return None
        case InstructionBT1():
            # current position + branch-pc offset (4) + instruction immediate
            target_function_offset = cursor_function_region_instructions.function_offset() + 4 + instruction.imm * 2

            return EffectBranch(
                conditional=instruction.cond is not Condition.AL,  # this will always be true, AL is forbidden
                target_function_offsets=frozenset([target_function_offset]),
            )
        case InstructionBT2():
            # current position + branch-pc offset (4) + instruction immediate
            target_function_offset = cursor_function_region_instructions.function_offset() + 4 + instruction.imm * 2

            return EffectBranch(
                conditional=False,
                target_function_offsets=frozenset([target_function_offset]),
            )
        case InstructionBlT1():
            # current address + branch-pc offset (4) + instruction immediate
            target_address = address + 4 + instruction.imm * 2

            return EffectCall(
                target_addresses=frozenset([target_address]),
            )
        case InstructionBlxRegisterT1():
            # PC = register
            # requires non-trivial handling
            effect_call = resolve_blx_register_t1(cursor_function_region_instructions, config_call_overrides)

            return effect_call
        case InstructionBxT1():
            # PC = register

            # special case - BX LR is technically a return
            if instruction.m is Register4.LR:
                return EffectReturn()

            # other patterns not seen in the wild
            raise ResolveUnsupportedInstructionException(instruction, address)
        case InstructionMovRegisterT1():
            if instruction.d is Register4.PC:
                # PC = register

                # special case - MOV PC, LR is technically a return
                if instruction.m is Register4.LR:
                    return EffectReturn()

                # other patterns not seen in the wild
                raise ResolveUnsupportedInstructionException(instruction, address)
            else:
                return None
        case InstructionPopT1():
            if instruction.pc:
                # POP PC
                return EffectReturn()

            return None
        case InstructionUdfT1():
            return EffectInvalid()
        case InstructionUdfT2():
            return EffectInvalid()
        case _:
            # other instructions should not have affect on PC. if they have - we've missed something in this list
            assert Register4.PC not in instruction.affects_registers()

            return None


class ResolveUnsupportedInstructionException(ResolveException):
    _instruction: Instruction

    def __init__(self, instruction: Instruction, address: Address) -> None:
        super().__init__(address, self._format_message(instruction, address))

        self._instruction = instruction

    @classmethod
    def _format_message(cls, instruction: Instruction, address: Address) -> str:
        return (
            f"Unsupported instruction affecting program flow ({instruction}) encountered at address 0x{address:04X}.\n"
            "This usually means one of the following:\n"
            " - Compile time optimizations, especially LTO were not enabled. This causes the final program to use "
            "local optimization (like tail-call BX) which we expect to be optimized out. Set up your compiler to "
            "optimize aggressively (for size, lto, etc).\n"
            " - Not commonly used instruction (like SP-relative branch) was found and we don't support it yet. Please "
            "review the assembly and establish if target address can be resolved automatically. If yes - please open "
            "an issue to help us improve this tool, providing as many details as possible."
        )


def resolve_call_config(
    config_call_overrides: ConfigCallOverrides, cursor_function_region_instructions: CursorFunctionRegionInstructions
) -> EffectCall | None:
    target_addresses = config_call_overrides.targets_by_source.get(cursor_function_region_instructions.address())
    if target_addresses is None:
        return None

    return EffectCall(
        target_addresses=frozenset(target_addresses),
    )


def resolve_add_register_t2_pc(cursor_function_region_instructions: CursorFunctionRegionInstructions) -> EffectBranch:
    RESOLVERS = [
        resolve_add_register_t2_pc_offset_table,
    ]

    effects_branch = {
        effect_branch
        for effect_branch in (resolver(cursor_function_region_instructions) for resolver in RESOLVERS)
        if effect_branch is not None
    }
    match list(effects_branch):
        case []:
            # no resolver resolved anything
            address = cursor_function_region_instructions.address()

            raise ResolveAddRegisterT2PcUnknownException(address)
        case [effect_branch]:
            # one or many resolver resolved our target effect

            return effect_branch
        case _:
            # multiple resolvers resolved multiple effects
            assert False


def resolve_add_register_t2_pc_offset_table(
    cursor_function_region_instructions: CursorFunctionRegionInstructions,
) -> EffectBranch | None:
    # register contains jump table index [0 - ?]
    # add register, pc # advances register to pc + jump table index
    # ldrb/h/- register, [register, 4] # adds 4 (to jump over ldrb, lsl, add) to register and loads branch offset
    # lsls register, register, #0x1 # multiplies branch offset by 2
    # add pc, register # performs the branch
    # data region containing offsets (divided by 2)
    # may contain 00 byte at the end as padding
    #
    # solve this by examining the pattern and extracting branch offsets from data region
    #
    # TODO: this is susceptible to situations in which our control jumps from other place to somewhere in the sequence,
    # possibly altering the flow. let's skip this for now

    # parse the add pc, register, this should be always true as it was what caused entry to this block
    instruction = cursor_function_region_instructions.instruction()
    match instruction:
        case InstructionAddRegisterT2():
            assert instruction.dn is Register4.PC

            # extract the register, cast it to Register3 (all other functions can operate on 3-bit only)
            register = instruction.m.to_register3()
            if register is None:
                # is not R0-R7?
                return None
        case _:
            # so who and why called us?
            assert False

    # parse the lsls, register, register, #0x1
    cursor_function_region_instructions_lsls = cursor_function_region_instructions.previous()
    if cursor_function_region_instructions_lsls is None:
        # function ended prematurely?
        return None
    instruction_lsls = cursor_function_region_instructions_lsls.instruction()
    match instruction_lsls:
        case InstructionLslImmediateT1():
            # we've got LSLS, yay

            # arguments must match our patter
            if instruction_lsls.d is not register:
                return None
            if instruction_lsls.m is not register:
                return None
            if instruction_lsls.imm != 1:
                return None
        case _:
            # other instruction
            return None

    # parse the ldr(b/h) register, [register, 4]
    cursor_function_region_instructions_ldr = cursor_function_region_instructions_lsls.previous()
    if cursor_function_region_instructions_ldr is None:
        # function ended prematurely?
        return None
    instruction_ldr = cursor_function_region_instructions_ldr.instruction()
    match instruction_ldr:
        case BaseInstructionLdrImmediate():
            # we've got LDR(B/H), yay

            # arguments must match our patter
            if instruction_ldr.t is not register:
                return None
            if instruction_ldr.n is not register:
                return None
            if instruction_ldr.imm * instruction_ldr.load_size() != 4:
                return None

            # extract load size
            load_size = instruction_ldr.load_size()
        case _:
            # other instruction
            return None

    # parse add register, pc
    cursor_function_region_instructions_add = cursor_function_region_instructions_ldr.previous()
    if cursor_function_region_instructions_add is None:
        # function ended prematurely?
        return None
    instructions_add = cursor_function_region_instructions_add.instruction()
    match instructions_add:
        case InstructionAddRegisterT2():
            # we've got ADD

            # arguments must match our patter
            if instructions_add.dn is not Register4.from_register3(register):
                return None
            if instructions_add.m is not Register4.PC:
                return None
        case _:
            # other instruction
            return None

    # instruction pattern matches, now lets resolve branch targets from data section that should follow
    cursor_function_region_data = cursor_function_region_instructions.cursor_function.region_data(
        cursor_function_region_instructions.function_end_offset()
    )
    if cursor_function_region_data is None:
        # region covering this address does not exist?
        return None
    if cursor_function_region_data.function_region_data_offset != 0:
        # is not immediately after the instruction?
        return None

    # extract all branch targets
    target_instruction_offsets = set[Address]()
    cursor_function_region_data_item: CursorFunctionRegionData | None = cursor_function_region_data
    while True:
        # we reached end of data region
        if cursor_function_region_data_item is None:
            break

        # load target offset and next cursor
        target_instruction_offset, cursor_function_region_data_item = cursor_function_region_data_item.read_unsigned(
            load_size
        )

        # it's a bit tricky situation to handle padding (and never-happening patterns) in those data regions. if the
        # load_size is 1 (byte), the jump-table may contain padding byte at the end to keep next instructions aligned.
        # if there are impossible patterns, the jump table may contain some sentinel value there.
        #
        # for now be assume that 0 is used in such scenario. the only situation in which 0 could be a valid offset,
        # would be if the jump table contains only 2 bytes. otherwise the 0 offset targets the data region. I believe
        # that we will never see a two item jump table, as it will be cheaper for the compiler to make a conditional
        # branch.
        #
        # when validating the output of this resolver we will generally check if branches point to valid instructions,
        # to minimize false negatives.
        if target_instruction_offset == 0:
            continue

        # all checks passed, let's add the value (multiplied by 2 by LSLS) to our target list
        target_instruction_offsets.add(target_instruction_offset * 2)

    # data region must not be empty and we started from the beginning
    assert target_instruction_offsets

    instruction_function_offset = cursor_function_region_instructions.function_offset()

    # convert to function-relative offsets
    # use current instruction offset + 4 (pc on next instruction) + offset from current instruction
    target_function_offsets = {
        instruction_function_offset + 4 + target_instruction_offset
        for target_instruction_offset in target_instruction_offsets
    }

    return EffectBranch(
        conditional=False,
        target_function_offsets=frozenset(target_function_offsets),
    )


class ResolveAddRegisterT2PcUnknownException(ResolveException):
    def __init__(self, address: Address) -> None:
        super().__init__(address, self._format_message(address))

    @classmethod
    def _format_message(cls, address: Address) -> str:
        return (
            f"Unable to automatically resolve target of ADD PC, Register instruction at 0x{address:04X}.\n"
            "Please open an issue to help us improve this tool, providing as many details as possible."
        )


def resolve_blx_register_t1(
    cursor_function_region_instructions: CursorFunctionRegionInstructions, config_call_overrides: ConfigCallOverrides
) -> EffectCall:
    RESOLVERS: Collection[Callable[[CursorFunctionRegionInstructions], EffectCall | None]] = [
        resolve_blx_register_t1_pc_relative_load,
        partial(resolve_call_config, config_call_overrides),
    ]

    # resolve effect of this instruction by trying multiple resolvers
    # they may return the same effect (will be flattened by set comprehensions)
    effects_call = {
        effect_call
        for effect_call in (resolver(cursor_function_region_instructions) for resolver in RESOLVERS)
        if effect_call is not None
    }
    match list(effects_call):
        case []:
            # no resolver resolved anything
            address = cursor_function_region_instructions.address()

            raise ResolveBlxRegisterT1UnknownException(address)
        case [effect_call]:
            # one or many resolver resolved our target effect

            return effect_call
        case _:
            # multiple resolvers resolved multiple effects
            assert False


class ResolveBlxRegisterT1UnknownException(ResolveException):
    def __init__(self, address: Address) -> None:
        super().__init__(address, self._format_message(address))

    @classmethod
    def _format_message(cls, address: Address) -> str:
        return (
            f"Unable to automatically resolve target of BLX instruction at 0x{address:04X}.\n"
            "This can be caused by the following reasons:\n"
            " - Call target looks like it can be statically resolved, but we can't do it yet. Please open an issue to "
            "help us improve this tool, providing as many details as possible. Temporarily use fallback below.\n"
            " - Call target is truly dynamic (eg. function pointer call) and there is no easy way to resolve it "
            "automatically. Please provide all possible call targets for this instruction manually, using config."
        )


def resolve_blx_register_t1_pc_relative_load(
    cursor_function_region_instructions: CursorFunctionRegionInstructions,
) -> EffectCall | None:
    # ldr register, [pc, #imm]
    # < some other instructions >
    # blx register
    #
    # solve this by looking back from blx for first instruction affecting register, it should be ldr register, [pc,
    # #imm]
    # TODO: this is susceptible to situations in which our control jumps from other place to somewhere between ldr and
    # blx, possibly having different register value. let's skip this for now
    # NOTE: although R0-R3 are not preserved by the calls in between (ldr and blx), we don't consider this a problem, as
    # they will be saved/restored by some instruction we will encounter while traversing

    # we should have our instruction at offset
    instruction = cursor_function_region_instructions.instruction()
    match instruction:
        case InstructionBlxRegisterT1():
            pass
        case _:
            # so who called us?
            assert False

    # start from previous instruction, look for first thing that modifies the `register`
    cursor_function_region_instructions_modifying: CursorFunctionRegionInstructions | None = (
        cursor_function_region_instructions.previous()
    )
    while True:
        # stop iterating if we reached beginning of the function
        if cursor_function_region_instructions_modifying is None:
            break

        # stop iterating if we reached instruction modifying `register`
        if instruction.m in cursor_function_region_instructions_modifying.instruction().affects_registers():
            break

        cursor_function_region_instructions_modifying = cursor_function_region_instructions_modifying.previous()

    # now `cursor_function_region_instructions_modifying` either contains None if we didn't find anything or an
    # instruction modifying the register
    if cursor_function_region_instructions_modifying is None:
        # we've reached the beginning of the function and nobody set the value of the register
        return None

    instructions_modifying = cursor_function_region_instructions_modifying.instruction()
    match instructions_modifying:
        case InstructionLdrLiteralT1():
            # target register must be our branch sources
            assert Register4.from_register3(instructions_modifying.t) == instruction.m

            # relative to current instruction address + 4 (instruction spec) + instruction immediate
            data_function_offset = (
                cursor_function_region_instructions_modifying.function_offset() + 4 + instructions_modifying.imm * 4
            )

            # resolve data region containing target address
            cursor_function_region_data_target = (
                cursor_function_region_instructions_modifying.cursor_function.region_data(data_function_offset)
            )
            if cursor_function_region_data_target is None:
                return None

            # get the address
            target_address, _ = cursor_function_region_data_target.read_word_unsigned()

            # lsb bit must always be set to signify thumb execution
            if target_address & 1 != 1:
                raise ValueError(
                    f"Thumb bit not set for immediate in {cursor_function_region_instructions}? "
                    "This would cause a HardFault..."
                )

            # clear it to align to the address
            target_address &= ~1

            return EffectCall(
                target_addresses=frozenset([target_address]),
            )
        case _:
            # unsupported instruction
            return None
