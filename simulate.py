#!/usr/bin/env python3
"""
simulate.py ─ мінімальний симулятор LC-2K (8 інструкцій, 8 регістрів).

▪ Якщо запустити без аргументів, виконує ./output.mc
▪ Увесь лог дублюється в result.txt
▪ --quiet прибирає покроковий друк на консоль (але лишає його в файлі)
"""

from __future__ import annotations
import argparse, sys, io
from dataclasses import dataclass, field
from pathlib import Path

MEM_SIZE   = 1 << 16        # 65 536 слів
STEP_LIMIT = 1_000_000
MASK_32    = 0xFFFF_FFFF
LOG_FILE   = Path("result.txt")

# ── ISA ──────────────────────────────────────────────────────────
OP_ADD, OP_NAND, OP_LW, OP_SW, OP_BEQ, OP_JALR, OP_HALT, OP_NOOP = range(8)

# ── helpers ─────────────────────────────────────────────────────
def sext16(x: int) -> int:
    """Sign-extend 16-bit value to Python int (-32768…32767)."""
    return (x & 0x7FFF) - (x & 0x8000)

def load_mc(path: str) -> list[int]:
    with open(path, encoding="utf-8") as f:
        words = [int(line) & MASK_32 for line in f]
    if len(words) > MEM_SIZE:
        sys.exit(f"Program too big: {len(words)} > {MEM_SIZE}")
    return words + [0] * (MEM_SIZE - len(words))

# ── state ───────────────────────────────────────────────────────
@dataclass(slots=True)
class State:
    mem:  list[int]
    log:  io.TextIOBase
    reg:  list[int] = field(default_factory=lambda: [0] * 8)
    pc:   int = 0
    steps:int = 0
    trace:bool = True

    def _out(self, msg: str) -> None:
        self.log.write(msg + "\n")
        if self.trace:
            print(msg)

    def dump(self) -> None:
        regs = " ".join(f"r{i}:{self.reg[i]}" for i in range(8))
        self._out(f"pc:{self.pc}  {regs}")

# ── handlers (True → pc+1) ──────────────────────────────────────
def op_add (s,a,b,dst,*_): s.reg[dst] = (s.reg[a] +  s.reg[b]) & MASK_32; return True
def op_nand(s,a,b,dst,*_): s.reg[dst] = ~(s.reg[a] & s.reg[b]) & MASK_32; return True

def op_lw(s,a,b,off,*_):
    s.reg[b] = s.mem[(s.reg[a] + sext16(off)) & (MEM_SIZE - 1)]; return True

def op_sw(s,a,b,off,*_):
    s.mem[(s.reg[a] + sext16(off)) & (MEM_SIZE - 1)] = s.reg[b] & MASK_32; return True

def op_beq(s,a,b,off,*_):
    if s.reg[a] == s.reg[b]:
        s.pc = (s.pc + 1 + sext16(off)) & (MEM_SIZE - 1); return False
    return True

def op_jalr(s,a,b,*_):
    s.reg[b] = (s.pc + 1) & MASK_32
    s.pc = s.reg[a] & (MEM_SIZE - 1);                     return False

# ── нова утиліта для друку пам’яті ──────────────────────────────
def dump_memory(s: State) -> None:
    """Вивести всі слова пам’яті ≠0 (адреса: значення)."""
    for addr, val in enumerate(s.mem):
        if val != 0:
            s._out(f"mem[{addr}] = {val}")

def op_halt(s,*_):
    s._out("machine halted")
    s._out(f"instructions executed: {s.steps}")
    s.dump()
    s._out("--- memory state ---")
    dump_memory(s)                       # ← новий виклик
    s.log.close()
    sys.exit(0)

def op_noop(*_): return True

HANDLERS = {
    OP_ADD: op_add,  OP_NAND: op_nand, OP_LW: op_lw,  OP_SW: op_sw,
    OP_BEQ: op_beq,  OP_JALR: op_jalr, OP_HALT: op_halt, OP_NOOP: op_noop,
}

# ── single step ─────────────────────────────────────────────────
def step(s: State):
    word = s.mem[s.pc]
    op   = (word >> 22) & 0b111
    a    = (word >> 19) & 0b111
    b    = (word >> 16) & 0b111
    imm  =  word & 0xFFFF
    dst  =  word & 0b111

    s.dump()
    advance = HANDLERS[op](s, a, b, imm, dst)
    if advance:
        s.pc = (s.pc + 1) & (MEM_SIZE - 1)
    s.reg[0] = 0
    s.steps += 1
    if s.steps > STEP_LIMIT:
        s._out(f"Step limit {STEP_LIMIT} exceeded")
        s.log.close()
        sys.exit(1)

# ── cli ─────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="LC-2K simulator → result.txt")
    p.add_argument("program", nargs="?", default="output.mc",
                   help="machine-code file (default: output.mc)")
    p.add_argument("--quiet", action="store_true",
                   help="suppress per-step console output (still logged)")
    ns = p.parse_args()

    log_fh = LOG_FILE.open("w", encoding="utf-8")
    state  = State(mem=load_mc(ns.program),
                   log=log_fh,
                   trace=not ns.quiet)
    while True:
        step(state)

if __name__ == "__main__":
    main()
