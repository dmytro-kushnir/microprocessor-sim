# LC-2K Assembler & Simulator (minimal course toolkit)

> **Purpose** – give every student a solid, working baseline that  
> 1. **assembles** an LC-2K source file (`*.as`) into machine code  
>    (one 32-bit word per line), and  
> 2. **simulates** that code instruction-by-instruction, dumping registers,
>    `PC`, and the final (non-zero) memory image to `result.txt`.

The baseline supports **exactly the 8 canonical LC-2K instructions** and
**one addressing mode** (register or register&nbsp;+&nbsp;16-bit displacement).
Adding extra op-codes or fancy addressing is left for individual variants.

---

## Project layout

| file / folder | purpose | language |
|---------------|---------|----------|
| **`assemble.py`** | two-pass assembler (`.as → .mc`) | Python 3 |
| **`simulate.py`** | step-by-step simulator (`.mc → result.txt`) | Python 3 |
| **`input.as`** | tiny demo program (count-down 5→0) | LC-2K asm |
| **`output.mc`** | machine code produced by `assemble.py` | decimal text |
| **`result.txt`** | execution log produced by `simulate.py` | text |

*(No external packages are required – both scripts run on stock Python 3.)*

---

## 1 Instruction set supported

| op-code | syntax | effect | decimal code |
|---------|--------|--------|--------------|
| **add**  | `add  rA rB rD`         | `R[rD] = R[rA] + R[rB]`            | 0 |
| **nand** | `nand rA rB rD`         | bitwise NAND                        | 1 |
| **lw**   | `lw   rA rB offset`     | `R[rB] = MEM[R[rA] + off]`          | 2 |
| **sw**   | `sw   rA rB offset`     | `MEM[R[rA] + off] = R[rB]`          | 3 |
| **beq**  | `beq  rA rB offset`     | if `R[rA] == R[rB]` → `PC += off+1` | 4 |
| **jalr** | `jalr rA rB`            | `R[rB] = PC+1 ; PC = R[rA]`         | 5 |
| **halt** | *(no args)*             | stop simulation                     | 6 |
| **noop** | *(no args)*             | do nothing                          | 7 |
| **.fill**| `.fill <value | label>` | assembler-time constant             | — |

* 8 general 32-bit registers (R0…R7, **R0 is hard-wired to 0**).  
* 64 K × 32-bit memory words.  
* Offsets are **signed 16-bit**.  
* `beq` offset = `target − (PC+1)` (assembler resolves labels).

> **Addressing mode note**  
> The baseline uses exactly **one memory addressing mode** –  
> register-relative displacement (`MEM[R[rA] + 16-bit offset]`)  
> and the direct register form for ALU/branch instructions.  
> Indirect, indexed, or base-index modes are **not** present;  
> you will add them yourself if required by your assignment.  
> See a short overview of addressing modes  
> <https://en.wikipedia.org/wiki/Addressing_mode>.

---

## 2 Assembler `assemble.py`

### Basic usage

```bash
# default names
python assemble.py                 # input.as  →  output.mc

# custom names / folders
python assemble.py  myprog.as       #   →  myprog.mc
python assemble.py  src/foo.as  bin/foo.mc
