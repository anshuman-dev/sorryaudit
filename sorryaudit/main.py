#!/usr/bin/env python3
"""
sorryaudit — Proof Trustworthiness Auditor for Lean 4

Usage:
    python main.py <path-to-lean4-project>  [--json] [--lean <lean-binary>]

Runs two passes:
  1. Syntactic: parse .lean files for sorry/admit/native_decide/Unsafe.cast
  2. Semantic:  generate #print axioms queries and run them through Lean
Then merges results into a trustworthiness report.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from parser import analyse_project
from axiom_query import run_axiom_queries_on_file, parse_axiom_output
from report import merge, render_text, render_json


def find_lean(override: Optional[str]) -> str:
    if override:
        return override
    for candidate in ["lean", str(Path.home() / ".elan/bin/lean")]:
        found = shutil.which(candidate) or (Path(candidate).exists() and candidate)
        if found:
            return str(found)
    print("ERROR: lean binary not found. Install via https://elan.lean-lang.org or pass --lean <path>")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Audit Lean 4 proofs for sorry taint")
    ap.add_argument("project", help="Path to Lean 4 project root")
    ap.add_argument("--json", action="store_true", help="Output JSON instead of text")
    ap.add_argument("--lean", default=None, help="Path to lean binary")
    ap.add_argument("--no-semantic", action="store_true",
                    help="Skip #print axioms pass (syntactic only, faster)")
    args = ap.parse_args()

    root = Path(args.project).resolve()
    if not root.exists():
        print(f"ERROR: {root} does not exist")
        sys.exit(1)

    lean_bin = find_lean(args.lean)

    print(f"[1/3] Parsing .lean files in {root} ...", file=sys.stderr)
    file_analyses = analyse_project(root)
    total_theorems = sum(len(fa.theorems) for fa in file_analyses)
    total_files = len(file_analyses)
    print(f"      Found {total_theorems} theorems across {total_files} files", file=sys.stderr)

    axiom_results = []
    if not args.no_semantic and total_theorems > 0:
        print(f"[2/3] Running #print axioms queries via Lean ...", file=sys.stderr)
        for fa in file_analyses:
            if not fa.theorems:
                continue
            names = [t.name for t in fa.theorems]
            print(f"      Querying {fa.path.name} ({len(names)} theorems) ...", file=sys.stderr)
            output = run_axiom_queries_on_file(lean_bin, fa.path, names)
            axiom_results.extend(parse_axiom_output(output))
        print(f"      Got axiom data for {len(axiom_results)} theorems", file=sys.stderr)
    else:
        print(f"[2/3] Skipping semantic pass (--no-semantic)", file=sys.stderr)

    print(f"[3/3] Building report ...", file=sys.stderr)
    report = merge(file_analyses, axiom_results)

    if args.json:
        print(json.dumps(render_json(report), indent=2))
    else:
        print(render_text(report))


if __name__ == "__main__":
    main()
