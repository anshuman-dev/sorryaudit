"""
Generates and runs `#print axioms` queries against Lean 4 projects,
then parses the output to find sorry/axiom taint.
"""
import subprocess
import re
import shutil
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple


# Axioms that are part of Lean 4's blessed standard set - not taint
STANDARD_AXIOMS = {
    "propext",
    "Classical.choice",
    "Quot.sound",
    "funext",
}

SORRY_AXIOM = "sorryAx"

AXIOM_LINE = re.compile(r"'([^']+)' depends on axioms: \[([^\]]*)\]")
NAMESPACE_RE = re.compile(r'^\s*namespace\s+(\S+)', re.MULTILINE)
OPEN_RE = re.compile(r'^\s*open\s+([\w\.]+(?:\s+[\w\.]+)*)', re.MULTILINE)


@dataclass
class AxiomResult:
    theorem: str
    axioms: List[str]

    @property
    def has_sorry(self) -> bool:
        return SORRY_AXIOM in self.axioms

    @property
    def non_standard_axioms(self) -> List[str]:
        return [a for a in self.axioms if a not in STANDARD_AXIOMS and a != SORRY_AXIOM]


def find_lake(project_root: Path) -> Optional[str]:
    """Return lake binary path if the project uses Lake, else None."""
    has_lakefile = (project_root / "lakefile.lean").exists() or \
                   (project_root / "lakefile.toml").exists()
    if not has_lakefile:
        return None
    lake = shutil.which("lake") or str(Path.home() / ".elan/bin/lake")
    return lake if Path(lake).exists() else None


def build_lake_project(lake_bin: str, project_root: Path) -> bool:
    """Run lake build. Returns True on success."""
    result = subprocess.run(
        [lake_bin, "build"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return result.returncode == 0


SRCDIR_RE = re.compile(r'srcDir\s*:=\s*["\']([^"\']*)["\']')


def _lake_src_roots(project_root: Path) -> List[Path]:
    """
    Parse lakefile.lean / lakefile.toml for srcDir declarations.
    Returns a list of resolved source root paths, most specific first.
    Falls back to [project_root] if nothing found.
    """
    roots = []
    for lakefile in ["lakefile.lean", "lakefile.toml"]:
        lf = project_root / lakefile
        if lf.exists():
            text = lf.read_text(errors="replace")
            for m in SRCDIR_RE.finditer(text):
                src = m.group(1).strip()
                if src == ".":
                    candidate = project_root
                else:
                    candidate = project_root / src
                if candidate.exists() and candidate not in roots:
                    roots.append(candidate)
    if project_root not in roots:
        roots.append(project_root)
    # Sort longest path first so most specific root matches first
    return sorted(roots, key=lambda p: len(str(p)), reverse=True)


def _module_name_from_path(source_file: Path, project_root: Path) -> str:
    """
    Derive a Lean module name by finding which srcDir the file belongs to.
    e.g. lean-tcb/test/LeanTcbTest/Soundness.lean
         with srcDir "test" -> LeanTcbTest.Soundness
    """
    src_roots = _lake_src_roots(project_root)
    resolved = source_file.resolve()
    for root in src_roots:
        try:
            rel = resolved.relative_to(root.resolve())
            parts = list(rel.with_suffix("").parts)
            return ".".join(parts)
        except ValueError:
            continue
    return source_file.stem


def _extract_opens(source: str) -> List[str]:
    """
    Collect all namespace and open declarations from the source
    so we can reproduce the name resolution context in our query file.
    """
    opens = []
    for m in NAMESPACE_RE.finditer(source):
        opens.append(m.group(1))
    for m in OPEN_RE.finditer(source):
        for name in m.group(1).split():
            opens.append(name)
    return list(dict.fromkeys(opens))  # deduplicate, preserve order


def run_axiom_queries_on_file(
    lean_bin: str,
    source_file: Path,
    theorem_names: List[str],
    lake_bin: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> str:
    """
    Query #print axioms for each theorem in source_file.

    For plain projects: appends queries directly to a copy of the source file.
    For Lake projects: creates a standalone import-based query file at the
    project root so namespace resolution and module imports work correctly.
    """
    if lake_bin and project_root:
        return _run_lake_query(lean_bin, lake_bin, source_file, theorem_names, project_root)
    else:
        return _run_inline_query(lean_bin, source_file, theorem_names)


def _run_inline_query(lean_bin: str, source_file: Path, theorem_names: List[str]) -> str:
    """Append #print axioms to the source file and run lean on it."""
    original = source_file.read_text(errors="replace")
    queries = "\n".join(f"#print axioms {name}" for name in theorem_names)
    augmented = original + "\n\n-- sorryaudit\n" + queries + "\n"

    tmp_path = source_file.with_suffix(".sorryaudit_tmp.lean")
    try:
        tmp_path.write_text(augmented)
        result = subprocess.run(
            [lean_bin, tmp_path.name],
            cwd=source_file.parent,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.stdout + result.stderr
    finally:
        tmp_path.unlink(missing_ok=True)


def _run_lake_query(
    lean_bin: str,
    lake_bin: str,
    source_file: Path,
    theorem_names: List[str],
    project_root: Path,
) -> str:
    """
    Create a standalone query file at the project root that imports the
    module and opens its namespaces, then runs #print axioms.
    This avoids the namespace-closed / path-resolution problems that arise
    when appending queries directly to a submodule file.
    """
    source = source_file.read_text(errors="replace")
    module = _module_name_from_path(source_file, project_root)
    opens = _extract_opens(source)

    lines = [f"import {module}"]
    for ns in opens:
        lines.append(f"open {ns}")
    lines.append("")
    for name in theorem_names:
        lines.append(f"#print axioms {name}")

    script = "\n".join(lines)

    tmp_fd, tmp_str = tempfile.mkstemp(suffix=".lean", dir=project_root, prefix="sorryaudit_")
    tmp_path = Path(tmp_str)
    try:
        tmp_path.write_text(script)
        result = subprocess.run(
            [lake_bin, "env", lean_bin, str(tmp_path.resolve())],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.stdout + result.stderr
    finally:
        import os
        os.close(tmp_fd)
        tmp_path.unlink(missing_ok=True)


def parse_axiom_output(output: str) -> List[AxiomResult]:
    results = []
    for line in output.splitlines():
        m = AXIOM_LINE.search(line)
        if m:
            name = m.group(1)
            raw_axioms = m.group(2).strip()
            axioms = [a.strip() for a in raw_axioms.split(",") if a.strip()] if raw_axioms else []
            results.append(AxiomResult(theorem=name, axioms=axioms))
    return results
