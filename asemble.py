#!/usr/bin/env python3
"""LC‑2K assembler – reference implementation (**assemble.py**)
================================================================

Usage (all parameters **optional**) ──────────────────────────────────────
    $ python assemble.py               # assemble ./input.as → ./output.mc
    $ python assemble.py prog.as       # assemble prog.as   → output.mc
    $ python assemble.py prog.as out.mc

Якщо аргумент *source* пропущено, збирається файл **input.as** з поточної
теки. Якщо *output* не вказано, результат записується у файл **output.mc**
у цій же теці (незалежно від імені вхідного файла).

Example *input.as* ───────────────────────────────────────────────────────
    # Count‑down from 5 to 0
        lw   0 1 five      # R1 ← 5
        lw   0 2 neg1      # R2 ← −1
loop    add  1 2 1         # R1 = R1 + R2
        beq  0 1 done      # if R1 == 0 → halt
        beq  0 0 loop      # unconditional jump

done    halt               # stop simulation

# data section
five    .fill 5
neg1    .fill -1

Алгоритм: два проходи — (1) збір міток; (2) кодування інструкцій / директив
`.fill` у 32‑бітові слова, записані десятковими числами по одному на рядок.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

# ────────────────────────────────────────────────────────────────────────────
# Constants & helpers
# ────────────────────────────────────────────────────────────────────────────

OPCODES: Dict[str, int] = {
    "add": 0,   # R‑type
    "nand": 1,  # R‑type
    "lw": 2,    # I‑type
    "sw": 3,    # I‑type
    "beq": 4,   # I‑type
    "jalr": 5,  # J‑type
    "halt": 6,  # O‑type
    "noop": 7,  # O‑type
}

LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,5}$")
TOKEN_RE = re.compile(r"[^\s]+")  # split by runs of space / tab

MAX_16 = 1 << 16
MASK_32 = 0xFFFFFFFF


def sign_extend_16(value: int) -> int:
    """Return *value* treated as signed 16‑bit integer promoted to Python int."""
    value &= 0xFFFF
    return value if value < 0x8000 else value - 0x10000


@dataclass(slots=True)
class Line:
    """A pre‑parsed line of assembly with metadata."""
    lineno: int
    label: str | None
    opcode: str
    args: Tuple[str, ...]
    raw: str  # original text, useful for diagnostics

    def __iter__(self):
        return iter((self.label, self.opcode, *self.args))


# ────────────────────────────────────────────────────────────────────────────
# Pass 1 – parsing & symbol table
# ────────────────────────────────────────────────────────────────────────────

def parse_lines(text: str) -> List[Line]:
    """Parse *text* into a list of *Line* objects (ignores blank & comment lines)."""
    lines: List[Line] = []
    for idx, raw in enumerate(text.splitlines()):
        code = raw.split('#', 1)[0]  # strip inline comment
        if not code.strip():
            continue
        tokens = TOKEN_RE.findall(code)
        label: str | None = None
        op_idx = 0
        # First token = label only if it is NOT an opcode or .fill
        if LABEL_RE.match(tokens[0]) and tokens[0] not in OPCODES and tokens[0] != ".fill":
            label = tokens[0]
            op_idx = 1
        if op_idx >= len(tokens):
            raise AsmError(idx, "Missing opcode", raw)
        opcode = tokens[op_idx]
        args = tuple(tokens[op_idx + 1 :])
        lines.append(Line(idx, label, opcode, args, raw))
    return lines


def build_symbol_table(lines: List[Line]) -> Dict[str, int]:
    symbols: Dict[str, int] = {}
    for pc, line in enumerate(lines):
        if line.label is not None:
            if line.label in symbols:
                raise AsmError(line.lineno, f"Duplicate label '{line.label}'", line.raw)
            symbols[line.label] = pc
    return symbols


# ────────────────────────────────────────────────────────────────────────────
# Pass 2 – encoding
# ────────────────────────────────────────────────────────────────────────────

def encode(lines: List[Line], symbols: Dict[str, int]) -> List[int]:
    code: List[int] = []
    for pc, line in enumerate(lines):
        op = line.opcode
        args = line.args

        # ----- директива .fill ------------------------------------------------
        if op == ".fill":
            check_argc(line, 1)
            code.append(resolve_value(args[0], symbols))
            continue

        # ----- валідація опкоду ----------------------------------------------
        if op not in OPCODES:
            raise AsmError(line.lineno, f"Unknown opcode '{op}'", line.raw)
        opc_val = OPCODES[op]

        # ----- R-формат -------------------------------------------------------
        if op in {"add", "nand"}:            # op rA rB rD
            check_argc(line, 3)
            rA, rB, rD = map(int_reg, args)
            instr = (opc_val << 22) | (rA << 19) | (rB << 16) | rD

        # ----- I-формат: lw / sw ---------------------------------------------
        elif op in {"lw", "sw"}:             # op rA rB offset
            check_argc(line, 3)
            rA, rB = map(int_reg, args[:2])
            offset = resolve_value(args[2], symbols, allow_label=True)

            if not (-MAX_16 // 2 <= offset < MAX_16 // 2):
                raise AsmError(line.lineno, "offset out of 16-bit range", line.raw)
            instr = (opc_val << 22) | (rA << 19) | (rB << 16) | (offset & 0xFFFF)

        # ----- I-формат: beq --------------------------------------------------
        elif op == "beq":                    # op rA rB label/imm
            check_argc(line, 3)
            rA, rB = map(int_reg, args[:2])

            # якщо аргумент – мітка → обчислюємо Δ = target − (pc + 1)
            if args[2] in symbols:
                offset = symbols[args[2]] - (pc + 1)
            else:
                offset = resolve_value(args[2], symbols)

            if not (-MAX_16 // 2 <= offset < MAX_16 // 2):
                raise AsmError(line.lineno, "branch offset out of 16-bit range", line.raw)
            instr = (opc_val << 22) | (rA << 19) | (rB << 16) | (offset & 0xFFFF)

        # ----- J-формат -------------------------------------------------------
        elif op == "jalr":                   # op rA rB
            check_argc(line, 2)
            rA, rB = map(int_reg, args)
            instr = (opc_val << 22) | (rA << 19) | (rB << 16)

        # ----- O-формат (halt / noop) ----------------------------------------
        else:                                # безоперандні
            check_argc(line, 0)
            instr = opc_val << 22

        code.append(instr & MASK_32)
    return code


# ────────────────────────────────────────────────────────────────────────────
# CLI / main entry
# ────────────────────────────────────────────────────────────────────────────

def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="LC‑2K assembler (Python)",
        epilog="If *source* is omitted, 'input.as' is used. "
               "If *output* is omitted, the default 'output.mc' is used.",
    )
    parser.add_argument("source", type=Path, nargs="?", default=Path("input.as"),
                        help="Assembly source file (.as). Default: ./input.as")
    parser.add_argument("output", type=Path, nargs="?", default=Path("output.mc"),
                        help="Destination machine‑code file (.mc). Default: ./output.mc")
    ns = parser.parse_args(argv)

    if not ns.source.exists():
        parser.error(f"Source file '{ns.source}' does not exist")

    text = ns.source.read_text(encoding="utf‑8")
    lines = parse_lines(text)
    symbols = build_symbol_table(lines)
    words = encode(lines, symbols)

    ns.output.write_text("\n".join(str(w) for w in words) + "\n", encoding="utf‑8")
    print(f"Assembled {len(words)} words → {ns.output}")


# ────────────────────────────────────────────────────────────────────────────
# Utilities & error handling
# ────────────────────────────────────────────────────────────────────────────

class AsmError(RuntimeError):
    """Custom exception carrying line context."""

    def __init__(self, lineno: int, msg: str, line: str = "") -> None:
        super().__init__(f"Line {lineno + 1}: {msg}\n    {line.strip()}")


def resolve_value(token: str, symbols: Dict[str, int], *, allow_label: bool = False) -> int:
    """Convert *token* to int, possibly resolving a label."""
    if token.isdigit() or (token.startswith("-") and token[1:].isdigit()):
        return int(token)
    if allow_label and token in symbols:
        return symbols[token]
    raise AsmError(-1, f"Undefined symbol '{token}'")


def check_argc(line: Line, expected: int) -> None:
    """Ensure instruction *line* has exactly *expected* operands."""
    if len(line.args) != expected:
        raise AsmError(line.lineno, f"Expected {expected} arguments, got {len(line.args)}", line.raw)


def int_reg(token: str) -> int:
    """Return register number ensuring 0≤id<8."""
    if not token.isdigit():
        raise AsmError(-1, f"Register id must be numeric: '{token}'")
    reg = int(token)
    if not (0 <= reg < 8):
        raise AsmError(-1, f"Register id out of range 0..7: {reg}")
    return reg


# ────────────────────────────────────────────────────────────────────────────
# Script entry
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        main()
    except AsmError as exc:
        sys.exit(str(exc))