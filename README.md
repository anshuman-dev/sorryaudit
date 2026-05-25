# sorryaudit

Proof trustworthiness auditor for Lean 4 codebases.

## The problem

`sorry` in Lean 4 is a proof placeholder. It makes any goal compile while silently marking the result as unsound. AI proof assistants use it constantly, filling in the parts they cannot prove and leaving the rest for "later."

The deeper issue is transitive taint. If theorem B depends on theorem A, and theorem A uses `sorry` anywhere in its proof chain, then B is also unsound - even if B's own proof is complete. Lean 4 warns at the point of `sorry`, not at every downstream dependent. A codebase can compile clean, show no errors, and still have half its theorems sitting on broken foundations.

This is not hypothetical. The "Who Watches the Watchers?" post by Kiran found a heap buffer overflow in a formally verified Lean 4 zlib implementation through fuzzing - the proof was correct, the bug lived at the boundary between verified code and the unverified C++ runtime. As AI tools generate more proof code, the gap between "compiles" and "actually proved" grows.

`sorryaudit` makes that gap visible.

## What it checks

- `sorry` and `admit` in proof bodies
- `native_decide` - evaluates at compile time, bypasses the kernel checker
- `Unsafe.cast` and related unsafe namespace calls
- Non-standard axioms introduced beyond Lean 4's trusted core (`propext`, `Classical.choice`, `Quot.sound`, `funext`)
- Transitive taint via `#print axioms` - if a theorem depends on `sorryAx` anywhere in its chain, it is flagged unsound regardless of whether `sorry` appears in its own proof text

## Two-pass design

**Syntactic pass**: parses `.lean` files directly, strips comments, finds taint patterns by line. Fast, works on any `.lean` file without needing a compiled project.

**Semantic pass**: appends `#print axioms <theorem>` queries to each source file, runs them through Lean (or `lake env lean` for Lake projects), and parses the output. This catches transitive taint that the syntactic pass cannot see.

Both passes run by default. The semantic pass result takes precedence where available; the syntactic pass covers the rest.

## Quickstart

```bash
# 1. Clone this repo
git clone https://github.com/anshuman-dev/sorryaudit.git
cd sorryaudit

# 2. Install Lean 4 via elan (skip if already installed)
curl https://elan.lean-lang.org/elan-init.sh -sSf | sh

# 3. Run on the included demo file (no extra setup needed)
python3 sorryaudit/main.py demo
```

The demo file (`demo/AIGenerated.lean`) simulates AI-generated proof output with 8 theorems — some directly sorry-tainted, some with no sorry visible in their body but transitively tainted, and some fully trusted. Expected output: 4 UNSOUND, 1 SUSPECT, 3 TRUSTED, overall score 45%.

To run on a real-world project:

```bash
# Clone lean-tcb (a Lean 4 library with a deliberate sorry for testing)
git clone https://github.com/OathTech/lean-tcb.git

# Run sorryaudit - lake build runs automatically
python3 sorryaudit/main.py lean-tcb
```

## Usage

```
python3 sorryaudit/main.py <path-to-lean4-project-or-file>
```

Options:

```
--no-semantic     syntactic pass only, faster, no Lean required
--no-build        skip lake build (use if project is already built)
--json            output JSON instead of text
--lean <path>     path to lean binary if not on PATH
```

## Output

```
================================================================
  SORRY AUDIT - Proof Trustworthiness Report
  Project : /path/to/project
  Theorems: 117  |  Overall score: 98.3%
  Trusted : 113  |  Unsound: 1  |  Suspect: 2
================================================================

[UNSOUND - depends on sorryAx]
  x  sorryThm  (Soundness.lean:18)
       line 19: theorem sorryThm : 1 + 1 = 3 := by sorry

[SUSPECT - non-standard axioms]
  ?  nativeThm  (Soundness.lean:20)
       axioms: nativeThm._native.native_decide.ax_1_1

[WARN - suspicious patterns (native_decide / Unsafe)]
  !  someTheorem  (Core.lean:42)
       line 43: native_decide - ...

[TRUSTED - 113 theorems fully sound]
  v  isTcbAnnotated
  ...
================================================================
```

Verdicts:

| Verdict  | Meaning |
|----------|---------|
| UNSOUND  | Depends on `sorryAx` - the proof is not complete |
| SUSPECT  | Uses non-standard axioms beyond the trusted core |
| WARN     | Contains `native_decide` or `Unsafe` calls |
| TRUSTED  | Depends only on `propext`, `Classical.choice`, `Quot.sound`, `funext` |

## Example: running on lean-tcb

`lean-tcb` is a Lean 4 library for auditing trusted computing bases. Running sorryaudit on it:

```
$ python3 sorryaudit/main.py lean-tcb
[0/3] Lake project detected.
      Running lake build ...
[1/3] Parsing .lean files in lean-tcb ...
      Found 117 theorems across 23 files
[2/3] Running #print axioms queries via Lean ...
      Got axiom data for 117 theorems
[3/3] Building report ...

Theorems: 117  |  Overall score: 98.7%
Trusted : 114  |  Unsound: 1  |  Suspect: 2
```

The one UNSOUND theorem is `sorryThm : 1 + 1 = 3` - a theorem lean-tcb includes deliberately to test its own soundness checker. sorryaudit catches it via Lean's own `#print axioms` machinery, not by grepping for the word `sorry`.

## Requirements

- Python 3.9+
- Lean 4 via [elan](https://github.com/leanprover/elan) (only needed for the semantic pass)
- No additional Python packages

## Hackathon context

Built for the Apart Research Secure Program Synthesis Hackathon (May 2026), Track 4: Adversarial Robustness for Interactive Theorem Provers.

The motivating question: as AI tools generate more Lean 4 proof code, how do you know what your codebase actually proves vs. what it claims to prove? `sorryaudit` answers that question by running Lean's own trusted axiom-inspection machinery across an entire project and reporting the result clearly.
