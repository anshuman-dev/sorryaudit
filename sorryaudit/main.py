#!/usr/bin/env python3
"""
sorryaudit - Proof Trustworthiness Auditor for Lean 4

Usage:
    python main.py <path-to-lean4-project> [--json] [--dot] [--tree]
                                           [--lean <path>] [--no-semantic] [--no-build]

Runs two passes:
  1. Syntactic: parse .lean files for sorry/admit/native_decide/Unsafe.cast
  2. Semantic:  run #print axioms through Lean to catch transitive taint

Then merges both into a trustworthiness report.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from parser import analyse_project
from axiom_query import run_axiom_queries_on_file, parse_axiom_output, find_lake, build_lake_project
from report import merge, render_text, render_json
from graph import render_dot, render_text_tree


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
    ap.add_argument("--json",        action="store_true", help="Output JSON")
    ap.add_argument("--dot",         action="store_true", help="Output Graphviz DOT")
    ap.add_argument("--tree",        action="store_true", help="Output compact file tree")
    ap.add_argument("--lean",        default=None, help="Path to lean binary")
    ap.add_argument("--no-semantic", action="store_true", help="Syntactic pass only")
    ap.add_argument("--no-build",    action="store_true", help="Skip lake build")
    args = ap.parse_args()

    root = Path(args.project).resolve()
    if not root.exists():
        print(f"ERROR: {root} does not exist", file=sys.stderr)
        sys.exit(1)

    lean_bin = find_lean(args.lean)

    lake_bin = find_lake(root)
    if lake_bin:
        print(f"[0/3] Lake project detected.", file=sys.stderr)
        if not args.no_semantic and not args.no_build:
            print(f"      Running lake build ...", file=sys.stderr)
            ok = build_lake_project(lake_bin, root)
            if not ok:
                print("      lake build failed - semantic pass may be incomplete", file=sys.stderr)
        else:
            print(f"      Skipping lake build (--no-build)", file=sys.stderr)

    print(f"[1/3] Parsing .lean files in {root} ...", file=sys.stderr)
    file_analyses = analyse_project(root)
    total_theorems = sum(len(fa.theorems) for fa in file_analyses)
    total_files    = len(file_analyses)
    print(f"      Found {total_theorems} theorems across {total_files} files", file=sys.stderr)

    axiom_results = []
    if not args.no_semantic and total_theorems > 0:
        print(f"[2/3] Running #print axioms queries via Lean ...", file=sys.stderr)
        for fa in file_analyses:
            if not fa.theorems:
                continue
            names = [t.name for t in fa.theorems]
            print(f"      Querying {fa.path.name} ({len(names)} theorems) ...", file=sys.stderr)
            output = run_axiom_queries_on_file(
                lean_bin, fa.path, names,
                lake_bin=lake_bin, project_root=root,
            )
            axiom_results.extend(parse_axiom_output(output))
        print(f"      Got axiom data for {len(axiom_results)} theorems", file=sys.stderr)
    else:
        print(f"[2/3] Skipping semantic pass (--no-semantic)", file=sys.stderr)

    print(f"[3/3] Building report ...", file=sys.stderr)
    report = merge(file_analyses, axiom_results)

    if args.json:
        print(json.dumps(render_json(report), indent=2))
    elif args.dot:
        print(render_dot(report))
    elif args.tree:
        print(render_text_tree(report))
    else:
        print(render_text(report))


if __name__ == "__main__":
    main()
