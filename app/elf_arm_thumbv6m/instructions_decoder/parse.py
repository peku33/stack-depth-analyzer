from collections.abc import Generator, Sequence, Set
from itertools import chain

from more_itertools import chunked_even

from . import model


def instructions_from_opcodes(opcodes_bytes: bytes) -> Generator[model.Instruction]:
    opcodes_halfword_iterator = chunked_even(opcodes_bytes, 2)

    while True:
        try:
            opcode_halfword_bytes = next(opcodes_halfword_iterator)
        except StopIteration:
            break

        instruction: model.Instruction

        # A5.1 Thumb instruction set encoding
        if opcode_halfword_bytes[1] >> 3 in (0b11101, 0b11110, 0b11111):
            # this is 32 bit instruction
            try:
                opcode_halfword_bytes_2 = next(opcodes_halfword_iterator)
            except StopIteration:
                raise ValueError("32 bit instruction ended prematurely.")  # pylint: disable=raise-missing-from

            opcode_word = int.from_bytes(chain(opcode_halfword_bytes_2, opcode_halfword_bytes), "little")

            try:
                instruction = instruction_from_opcode_word(opcode_word)
            except (model.InstructionUndefined, model.InstructionUnpredictable) as exception:
                exception.add_note(f"opcode: {opcode_word:08X}")
                raise

            assert instruction.size() == 4
        else:
            # this is 16 bit instruction
            opcode_halfword = int.from_bytes(opcode_halfword_bytes, "little")

            try:
                instruction = instruction_from_opcode_halfword(opcode_halfword)
            except (model.InstructionUndefined, model.InstructionUnpredictable) as exception:
                exception.add_note(f"opcode: {opcode_halfword:04X}")
                raise

            assert instruction.size() == 2

        yield instruction


def instruction_from_opcode_halfword(opcode_halfword: int) -> model.Instruction16:
    assert 0 <= opcode_halfword < (1 << 16)

    # A5.2 16-bit Thumb instruction encoding
    opcode_1 = _bits_msb_from_int(opcode_halfword >> 10, 6)
    match opcode_1:
        case [False, False, _, _, _, _]:
            # A5.2.1 Shift (immediate), add, subtract, move, and compare
            opcode_2 = _bits_msb_from_int(opcode_halfword >> 9, 5)
            match opcode_2:
                case [False, False, False, _, _]:
                    # A6.7.35 LSL (immediate) T1
                    imm = _imm_from_opcode(opcode_halfword, 5, 6)
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    if imm == 0:
                        return model.InstructionMovRegisterT2(rd, rm)

                    return model.InstructionLslImmediateT1(rd, rm, imm)
                case [False, False, True, _, _]:
                    # A6.7.37 LSR (immediate) T1
                    imm = _imm_from_opcode(opcode_halfword, 5, 6)
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionLsrImmediateT1(rd, rm, imm)
                case [False, True, False, _, _]:
                    # A6.7.8 ASR (immediate) T1
                    imm = _imm_from_opcode(opcode_halfword, 5, 6)
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionAsrImmediateT1(rd, rm, imm)
                case [False, True, True, False, False]:
                    # A6.7.3 ADD (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 6)
                    rn = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionAddRegisterT1(rd, rn, rm)
                case [False, True, True, False, True]:
                    # A6.7.66 SUB (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 6)
                    rn = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionSubRegisterT1(rd, rn, rm)
                case [False, True, True, True, False]:
                    # A6.7.2 ADD (immediate) T1
                    imm = _imm_from_opcode(opcode_halfword, 3, 6)
                    rn = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionAddImmediateT1(rd, rn, imm)
                case [False, True, True, True, True]:
                    # A6.7.65 SUB (immediate) T1
                    imm = _imm_from_opcode(opcode_halfword, 3, 6)
                    rn = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionSubImmediateT1(rd, rn, imm)
                case [True, False, False, _, _]:
                    # A6.7.39 MOV (immediate) T1
                    rd = _register3_from_opcode(opcode_halfword, 8)
                    imm = _imm_from_opcode(opcode_halfword, 8, 0)

                    return model.InstructionMovImmediateT1(rd, imm)
                case [True, False, True, _, _]:
                    # A6.7.17 CMP (immediate) T1
                    rn = _register3_from_opcode(opcode_halfword, 8)
                    imm = _imm_from_opcode(opcode_halfword, 8, 0)

                    return model.InstructionCmpImmediateT1(rn, imm)
                case [True, True, False, _, _]:
                    # A6.7.2 ADD (immediate) T2
                    rdn = _register3_from_opcode(opcode_halfword, 8)
                    imm = _imm_from_opcode(opcode_halfword, 8, 0)

                    return model.InstructionAddImmediateT2(rdn, imm)
                case [True, True, True, _, _]:
                    # A6.7.65 SUB (immediate) T2
                    rdn = _register3_from_opcode(opcode_halfword, 8)
                    imm = _imm_from_opcode(opcode_halfword, 8, 0)

                    return model.InstructionSubImmediateT2(rdn, imm)
                case _:
                    raise model.InstructionUndefined()
            assert False
        case [False, True, False, False, False, False]:
            # A5.2.2 Data processing
            opcode_2 = _bits_msb_from_int(opcode_halfword >> 6, 4)
            match opcode_2:
                case [False, False, False, False]:
                    # A6.7.7 AND (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rdn = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionAndRegisterT1(rdn, rm)
                case [False, False, False, True]:
                    # A6.7.23 EOR (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rdn = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionEorRegisterT1(rdn, rm)
                case [False, False, True, False]:
                    # A6.7.36 LSL (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rdn = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionLslRegisterT1(rdn, rm)
                case [False, False, True, True]:
                    # A6.7.38 LSR (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rdn = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionLsrRegisterT1(rdn, rm)
                case [False, True, False, False]:
                    # A6.7.9 ASR (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rdn = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionAsrRegisterT1(rdn, rm)
                case [False, True, False, True]:
                    # A6.7.1 ADC (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rdn = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionAdcRegisterT1(rdn, rm)
                case [False, True, True, False]:
                    # A6.7.56 SBC (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rdn = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionSbcRegisterT1(rdn, rm)
                case [False, True, True, True]:
                    # A6.7.54 ROR (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rdn = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionRorRegisterT1(rdn, rm)
                case [True, False, False, False]:
                    # A6.7.71 TST (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rn = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionTstRegisterT1(rn, rm)
                case [True, False, False, True]:
                    # A6.7.55 RSB (immediate) T1
                    rn = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionRsbImmediateT1(rd, rn)
                case [True, False, True, False]:
                    # A6.7.18 CMP (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rn = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionCmpRegisterT1(rn, rm)
                case [True, False, True, True]:
                    # A6.7.16 CMN (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rn = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionCmnRegisterT1(rn, rm)
                case [True, True, False, False]:
                    # A6.7.48 ORR (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rdn = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionOrrRegisterT1(rdn, rm)
                case [True, True, False, True]:
                    # A6.7.44 MUL T1
                    rn = _register3_from_opcode(opcode_halfword, 3)
                    rdm = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionMulT1(rdm, rn)
                case [True, True, True, False]:
                    # A6.7.11 BIC (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rdn = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionBicRegisterT1(rdn, rm)
                case [True, True, True, True]:
                    # A6.7.45 MVN (register) T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionMvnRegisterT1(rd, rm)
                case _:
                    assert False
            assert False
        case [False, True, False, False, False, True]:
            # A5.2.3 Special data instructions and branch and exchange
            opcode_2 = _bits_msb_from_int(opcode_halfword >> 6, 4)
            match opcode_2:
                case [False, False, _, _]:
                    # A6.7.3 ADD (register) T2 + A6.7.5 ADD (SP plus register) T1 + T2
                    rdn4 = _register4_7210_from_opcode(opcode_halfword)
                    rm4 = _register4_from_opcode(opcode_halfword, 3)

                    if rm4 is model.Register4.SP:
                        return model.InstructionAddSpPlusRegisterT1(rdn4)
                    elif rdn4 is model.Register4.SP:
                        return model.InstructionAddSpPlusRegisterT2(rm4)
                    elif rdn4 is model.Register4.PC and rm4 is model.Register4.PC:
                        raise model.InstructionUnpredictable()
                    else:
                        return model.InstructionAddRegisterT2(rdn4, rm4)
                case [False, True, False, False]:
                    raise model.InstructionUnpredictable()
                case [False, True, False, True] | [False, True, True, _]:
                    # A6.7.18 CMP (register) T2
                    rn4 = _register4_7210_from_opcode(opcode_halfword)
                    rm4 = _register4_from_opcode(opcode_halfword, 3)

                    if rn4.value < 8 and rm4.value < 8:
                        raise model.InstructionUnpredictable()
                    if rn4 is model.Register4.PC or rm4 is model.Register4.PC:
                        raise model.InstructionUnpredictable()

                    return model.InstructionCmpRegisterT2(rn4, rm4)
                case [True, False, _, _]:
                    # A6.7.40 MOV (register) T1
                    rd4 = _register4_7210_from_opcode(opcode_halfword)
                    rm4 = _register4_from_opcode(opcode_halfword, 3)

                    return model.InstructionMovRegisterT1(rd4, rm4)
                case [True, True, False, _]:
                    # A6.7.15 BX T1
                    rm4 = _register4_from_opcode(opcode_halfword, 3)

                    if rm4 is model.Register4.PC:
                        raise model.InstructionUnpredictable()

                    return model.InstructionBxT1(rm4)
                case [True, True, True, _]:
                    # A6.7.14 BLX (register) T1
                    rm4 = _register4_from_opcode(opcode_halfword, 3)

                    if rm4 is model.Register4.PC:
                        raise model.InstructionUnpredictable()

                    return model.InstructionBlxRegisterT1(rm4)
                case _:
                    raise model.InstructionUndefined()
            assert False
        case [False, True, False, False, True, _]:
            # A6.7.27 LDR (literal) T1
            rt = _register3_from_opcode(opcode_halfword, 8)
            imm = _imm_from_opcode(opcode_halfword, 8, 0)

            return model.InstructionLdrLiteralT1(rt, imm)
        case [False, True, False, True, _, _] | [False, True, True, _, _, _] | [True, False, False, _, _, _]:
            # A5.2.4 Load/store single data item
            opcode_a = _bits_msb_from_int(opcode_halfword >> 12, 4)
            opcode_b = _bits_msb_from_int(opcode_halfword >> 9, 3)

            match opcode_a:
                case [False, True, False, True]:
                    rm = _register3_from_opcode(opcode_halfword, 6)
                    rn = _register3_from_opcode(opcode_halfword, 3)
                    rt = _register3_from_opcode(opcode_halfword, 0)

                    match opcode_b:
                        case [False, False, False]:
                            # A6.7.60 STR (register) T1
                            return model.InstructionStrRegisterT1(rt, rn, rm)
                        case [False, False, True]:
                            # A6.7.64 STRH (register) T1
                            return model.InstructionStrhRegisterT1(rt, rn, rm)
                        case [False, True, False]:
                            # A6.7.62 STRB (register) T1
                            return model.InstructionStrbRegisterT1(rt, rn, rm)
                        case [False, True, True]:
                            # A6.7.33 LDRSB (register) T1
                            return model.InstructionLdrsbRegisterT1(rt, rn, rm)
                        case [True, False, False]:
                            # A6.7.28 LDR (register) T1
                            return model.InstructionLdrRegisterT1(rt, rn, rm)
                        case [True, False, True]:
                            # A6.7.32 LDRH (register) T1
                            return model.InstructionLdrhRegisterT1(rt, rn, rm)
                        case [True, True, False]:
                            # A6.7.30 LDRB (register) T1
                            return model.InstructionLdrbRegisterT1(rt, rn, rm)
                        case [True, True, True]:
                            # A6.7.34 LDRSH (register) T1
                            return model.InstructionLdrshRegisterT1(rt, rn, rm)
                        case _:
                            assert False
                    assert False
                case [False, True, True, False]:
                    imm = _imm_from_opcode(opcode_halfword, 5, 6)
                    rn = _register3_from_opcode(opcode_halfword, 3)
                    rt = _register3_from_opcode(opcode_halfword, 0)

                    match opcode_b:
                        case [False, _, _]:
                            # A6.7.59 STR (immediate) T1
                            return model.InstructionStrImmediateT1(rt, rn, imm)
                        case [True, _, _]:
                            # A6.7.26 LDR (immediate) T1
                            return model.InstructionLdrImmediateT1(rt, rn, imm)
                        case _:
                            assert False
                    assert False
                case [False, True, True, True]:
                    imm = _imm_from_opcode(opcode_halfword, 5, 6)
                    rn = _register3_from_opcode(opcode_halfword, 3)
                    rt = _register3_from_opcode(opcode_halfword, 0)

                    match opcode_b:
                        case [False, _, _]:
                            # A6.7.61 STRB (immediate) T1
                            return model.InstructionStrbImmediateT1(rt, rn, imm)
                        case [True, _, _]:
                            # A6.7.29 LDRB (immediate) T1
                            return model.InstructionLdrbImmediateT1(rt, rn, imm)
                        case _:
                            assert False
                    assert False
                case [True, False, False, False]:
                    imm = _imm_from_opcode(opcode_halfword, 5, 6)
                    rn = _register3_from_opcode(opcode_halfword, 3)
                    rt = _register3_from_opcode(opcode_halfword, 0)

                    match opcode_b:
                        case [False, _, _]:
                            # A6.7.63 STRH (immediate) T1
                            return model.InstructionStrhImmediateT1(rt, rn, imm)
                        case [True, _, _]:
                            # A6.7.31 LDRH (immediate) T1
                            return model.InstructionLdrhImmediateT1(rt, rn, imm)
                        case _:
                            assert False
                    assert False
                case [True, False, False, True]:
                    rt = _register3_from_opcode(opcode_halfword, 8)
                    imm = _imm_from_opcode(opcode_halfword, 8, 0)

                    match opcode_b:
                        case [False, _, _]:
                            # A6.7.59 STR (immediate) T2
                            return model.InstructionStrImmediateT2(rt, imm)
                        case [True, _, _]:
                            # A6.7.26 LDR (immediate) T2
                            return model.InstructionLdrImmediateT2(rt, imm)
                        case _:
                            assert False
                    assert False
                case _:
                    raise model.InstructionUndefined()
            assert False
        case [True, False, True, False, False, _]:
            # A6.7.6 ADR T1
            rd = _register3_from_opcode(opcode_halfword, 8)
            imm = _imm_from_opcode(opcode_halfword, 8, 0)

            return model.InstructionAdrT1(rd, imm)
        case [True, False, True, False, True, _]:
            # A6.7.4 ADD (SP plus immediate) T1
            rd = _register3_from_opcode(opcode_halfword, 8)
            imm = _imm_from_opcode(opcode_halfword, 8, 0)

            return model.InstructionAddSpPlusImmediateT1(rd, imm)
        case [True, False, True, True, _, _]:
            # A5.2.5 Miscellaneous 16-bit instructions
            opcode_2 = _bits_msb_from_int(opcode_halfword >> 5, 7)
            match opcode_2:
                case [False, False, False, False, False, _, _]:
                    # A6.7.4 ADD (SP plus immediate) T2
                    imm = _imm_from_opcode(opcode_halfword, 7, 0)

                    return model.InstructionAddSpPlusImmediateT2(imm)
                case [False, False, False, False, True, _, _]:
                    # A6.7.67 SUB (SP minus immediate) T1
                    imm = _imm_from_opcode(opcode_halfword, 7, 0)

                    return model.InstructionSubSpMinusImmediateT1(imm)
                case [False, False, True, False, False, False, _]:
                    # A6.7.70 SXTH T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionSxthT1(rd, rm)
                case [False, False, True, False, False, True, _]:
                    # A6.7.69 SXTB T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionSxtbT1(rd, rm)
                case [False, False, True, False, True, False, _]:
                    # A6.7.74 UXTH T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionUxthT1(rd, rm)
                case [False, False, True, False, True, True, _]:
                    # A6.7.74 UXTB T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionUxtbT1(rd, rm)
                case [False, True, False, _, _, _, _]:
                    # A6.7.50 PUSH T1
                    [lr] = _bits_msb_from_int(opcode_halfword >> 8, 1)
                    registers3 = _registers3_from_opcode(opcode_halfword)

                    if not (lr or registers3):
                        raise model.InstructionUnpredictable()

                    return model.InstructionPushT1(lr, registers3)
                case [False, True, True, False, False, True, True]:
                    # B4.2.1 CPS T1
                    [im] = _bits_msb_from_int(opcode_halfword >> 4, 1)

                    return model.InstructionCpsT1(im)
                case [True, False, True, False, False, False, _]:
                    # A6.7.51 REV T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionRevT1(rd, rm)
                case [True, False, True, False, False, True, _]:
                    # A6.7.52 REV16 T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionRev16T1(rd, rm)
                case [True, False, True, False, True, True, _]:
                    # A6.7.53 REVSH T1
                    rm = _register3_from_opcode(opcode_halfword, 3)
                    rd = _register3_from_opcode(opcode_halfword, 0)

                    return model.InstructionRevshT1(rd, rm)
                case [True, True, False, _, _, _, _]:
                    # A6.7.49 POP T1
                    [pc] = _bits_msb_from_int(opcode_halfword >> 8, 1)
                    registers3 = _registers3_from_opcode(opcode_halfword)

                    if not (pc or registers3):
                        raise model.InstructionUnpredictable()

                    return model.InstructionPopT1(pc, registers3)
                case [True, True, True, False, _, _, _]:
                    # A6.7.12 BKPT T1
                    imm = _imm_from_opcode(opcode_halfword, 8, 0)

                    return model.InstructionBkptT1(imm)
                case [True, True, True, True, _, _, _]:
                    # Hint instructions
                    opcode_a = _bits_msb_from_int(opcode_halfword >> 4, 4)
                    opcode_b = _bits_msb_from_int(opcode_halfword >> 0, 4)
                    if opcode_b != [False, False, False, False]:
                        raise model.InstructionUndefined()
                    match opcode_a:
                        case [False, False, False, False]:
                            # A6.7.47 NOP T1
                            return model.InstructionNopT1()
                        case [False, False, False, True]:
                            # A6.7.77 YIELD T1
                            return model.InstructionYieldT1()
                        case [False, False, True, False]:
                            # A6.7.75 WFE T1
                            return model.InstructionWfeT1()
                        case [False, False, True, True]:
                            # A6.7.76 WFI T1
                            return model.InstructionWfiT1()
                        case [False, True, False, False]:
                            # A6.7.57 SEV T1
                            return model.InstructionSevT1()
                        case _:
                            raise model.InstructionUndefined()
                    assert False
                case _:
                    raise model.InstructionUndefined()
            assert False
        case [True, True, False, False, False, _]:
            # A6.7.58 STM, STMIA, STMEA T1
            rn = _register3_from_opcode(opcode_halfword, 8)
            registers3 = _registers3_from_opcode(opcode_halfword)

            if not registers3:
                raise model.InstructionUnpredictable()

            return model.InstructionStmT1(rn, registers3)
        case [True, True, False, False, True, _]:
            # A6.7.25 LDM, LDMIA, LDMFD T1
            rn = _register3_from_opcode(opcode_halfword, 8)
            registers3 = _registers3_from_opcode(opcode_halfword)

            if not registers3:
                raise model.InstructionUnpredictable()

            return model.InstructionLdmT1(rn, registers3)
        case [True, True, False, True, _, _]:
            opcode_2 = _bits_msb_from_int(opcode_halfword >> 8, 4)
            match opcode_2:
                case [True, True, True, False]:
                    # A6.7.72 UDF T1
                    imm = _imm_from_opcode(opcode_halfword, 8, 0)

                    return model.InstructionUdfT1(imm)
                case [True, True, True, True]:
                    # A6.7.68 SVC T1
                    imm = _imm_from_opcode(opcode_halfword, 8, 0)

                    return model.InstructionSvcT1(imm)
                case _:
                    # A6.7.10 B T1
                    cond = model.Condition(_imm_from_opcode(opcode_halfword, 4, 8))
                    imm = _imm_from_opcode(opcode_halfword, 8, 0, True)

                    return model.InstructionBT1(cond, imm)
            assert False
        case [True, True, True, False, False, _]:
            # A6.7.10 B T2
            imm = _imm_from_opcode(opcode_halfword, 11, 0, True)

            return model.InstructionBT2(imm)
        case _:
            raise model.InstructionUndefined()
    assert False


def instruction_from_opcode_word(opcode_word: int) -> model.Instruction32:
    assert 0 <= opcode_word < (1 << 32)

    opcode_1 = _bits_msb_from_int(opcode_word >> 27, 2)
    match opcode_1:
        case [_, True]:
            raise model.InstructionUndefined()
        case [True, False]:
            opcode_2 = _bits_msb_from_int(opcode_word >> 15, 1)
            match opcode_2:
                case [True]:
                    # A5.3.1 Branch and miscellaneous control
                    opcode_bis_1 = _bits_msb_from_int(opcode_word >> 20, 7)
                    opcode_bis_2 = _bits_msb_from_int(opcode_word >> 12, 3)

                    match opcode_bis_2:
                        case [False, _, False]:
                            match opcode_bis_1:
                                case [False, True, True, True, False, False, _]:
                                    # B4.2.3 MSR (register) T1
                                    rd4 = _register4_from_opcode(opcode_word, 16)
                                    sys_m = model.SysM(_imm_from_opcode(opcode_word, 8, 0))

                                    if rd4 in (model.Register4.SP, model.Register4.PC):
                                        raise model.InstructionUnpredictable()

                                    return model.InstructionMsrRegisterT1(sys_m, rd4)
                                case [False, True, True, True, False, True, True]:
                                    # Miscellaneous control instructions
                                    opcode_bis_bis = _bits_msb_from_int(opcode_word >> 4, 4)
                                    match opcode_bis_bis:
                                        case [False, True, False, False]:
                                            # A6.7.22 DSB T1
                                            option = _imm_from_opcode(opcode_word, 4, 0)

                                            return model.InstructionDsbT1(option)
                                        case [False, True, False, True]:
                                            # A6.7.21 DMB T1
                                            option = _imm_from_opcode(opcode_word, 4, 0)

                                            return model.InstructionDmbT1(option)
                                        case [False, True, True, False]:
                                            # A6.7.24 ISB T1
                                            option = _imm_from_opcode(opcode_word, 4, 0)

                                            return model.InstructionIsbT1(option)
                                        case _:
                                            raise model.InstructionUndefined()
                                    assert False
                                case [False, True, True, True, True, True, _]:
                                    # B4.2.2 MRS T1
                                    rd4 = _register4_from_opcode(opcode_word, 8)
                                    sys_m = model.SysM(_imm_from_opcode(opcode_word, 8, 0))

                                    if rd4 in (model.Register4.SP, model.Register4.PC):
                                        raise model.InstructionUnpredictable()

                                    return model.InstructionMrsT1(rd4, sys_m)
                                case [True, True, True, True, True, True, True]:
                                    # A6.7.72 UDF T2
                                    imm4 = _imm_from_opcode(opcode_word, 4, 16)
                                    imm12 = _imm_from_opcode(opcode_word, 12, 0)

                                    imm = (imm4 << 12) | imm12

                                    return model.InstructionUdfT2(imm)
                                case _:
                                    raise model.InstructionUndefined()
                            assert False
                        case [True, _, True]:
                            # A6.7.13 BL T1
                            s = (opcode_word >> 26) & 0b1 == 1
                            imm10 = _bits_msb_from_int(opcode_word >> 16, 10)
                            j1 = (opcode_word >> 13) & 0b1 == 1
                            j2 = (opcode_word >> 11) & 0b1 == 1
                            imm11 = _bits_msb_from_int(opcode_word, 11)

                            i1 = not j1 ^ s
                            i2 = not j2 ^ s

                            imm = _sint_from_bits_msb([s, i1, i2, *imm10, *imm11])

                            return model.InstructionBlT1(imm)
                        case _:
                            raise model.InstructionUndefined()
                    assert False
                case [False]:
                    raise model.InstructionUndefined()
                case _:
                    assert False
            assert False
        case _:
            raise model.InstructionUndefined()
    assert False


def _bits_msb_from_int(input_: int, output_bits: int) -> Sequence[bool]:
    """
    Converts `input_` integer into `output_bits` of boolean bits, assuming that first output value is MSB.
    """

    output = [False] * output_bits

    for bit in range(output_bits):
        output[bit] = bool(input_ & (1 << (output_bits - bit - 1)))

    return output


def _sint_from_bits_msb(bits: Sequence[bool]) -> int:
    """
    Converts `bits` into integer, assuming MSB go first and the value is signed.
    """
    assert bits

    output = 0
    for shift, bit in enumerate(reversed(bits)):
        if bit:
            output |= 1 << shift

    if bits[0]:
        output = output - (1 << len(bits))

    return output


def _register3_from_opcode(opcode: int, lsb_index: int) -> model.Register3:
    """
    Takes 3 bits, starting from `lsb_index` from `opcode` and converts them to 3-bit register (0-7).
    """
    return model.Register3((opcode >> lsb_index) & 0b111)


def _registers3_from_opcode(opcode: int) -> Set[model.Register3]:
    registers3 = set[model.Register3]()
    for register3 in model.Register3:
        if opcode & (1 << register3.value):
            registers3.add(register3)
    return registers3


def _register4_from_opcode(opcode: int, lsb_index: int) -> model.Register4:
    """
    Takes 4 bits, starting from `lsb_index` from `opcode` and converts them to 4-bit register (0-15).
    """
    return model.Register4((opcode >> lsb_index) & 0b1111)


def _register4_7210_from_opcode(opcode: int) -> model.Register4:
    """
    Converts bits 7, 2, 1, 0 of `opcode` into 4-bit register (0-15).
    """
    return model.Register4(((opcode >> 4) & 0b1000) | (opcode & 0b111))


def _imm_from_opcode(opcode: int, width: int, lsb_index: int, signed: bool = False) -> int:
    """
    Takes bits `width` bits from `opcode` starting at `lsb_index` and converts them to integer, either signed or
    unsigned, depending on `signed` parameter.
    """

    imm = (opcode >> lsb_index) & ((1 << width) - 1)
    if signed and (opcode & (1 << (lsb_index + width - 1))) > 0:
        imm = imm - (1 << width)
    return imm
