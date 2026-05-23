"""
Generates a Lean 4 script that runs `#print axioms` on every theorem
in the project, then parses the output to find sorry/axiom taint.
"""
import subprocess
import re
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional


# Axioms that are part of Lean 4's blessed standard set - not taint
STANDARD_AXIOMS = {
    "propext",
    "Classical.choice",
    "Quot.sound",
    "funext",
}

SORRY_AXIOM = "sorryAx"

AXIOM_LINE = re.compile(r"'([^']+)' depends on axioms: \[([^\]]*)\]")


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


def run_axiom_queries_on_file(
    lean_bin: str,
    source_file: Path,
    theorem_names: List[str],
    lake_bin: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> str:
    """
    Appends #print axioms queries to a copy of source_file and runs Lean on it.
    If lake_bin is given, uses `lake env lean` so imports resolve against built .olean files.
    """
    original = source_file.read_text(errors="replace")
    queries = "\n".join(f"#print axioms {name}" for name in theorem_names)
    augmented = original + "\n\n-- sorryaudit queries\n" + queries + "\n"

    tmp_path = source_file.with_suffix(".sorryaudit_tmp.lean")
    try:
        tmp_path.write_text(augmented)

        if lake_bin and project_root:
            cmd = [lake_bin, "env", lean_bin, str(tmp_path.resolve())]
            cwd = project_root
        else:
            cmd = [lean_bin, tmp_path.name]
            cwd = source_file.parent

        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.stdout + result.stderr
    finally:
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
