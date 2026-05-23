"""
Builds and renders the trust report from parser + axiom query results.
"""
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict
from parser import FileAnalysis, TheoremInfo, TaintHit
from axiom_query import AxiomResult


@dataclass
class TheoremReport:
    name: str
    file: Path
    line: int
    direct_taints: List[TaintHit]
    has_sorry_axiom: bool
    non_standard_axioms: List[str]

    @property
    def trust_score(self) -> float:
        """0.0 = completely tainted, 1.0 = fully trusted"""
        if self.has_sorry_axiom:
            return 0.0
        penalty = min(len(self.non_standard_axioms) * 0.15, 0.6)
        if self.direct_taints:
            penalty = max(penalty, 0.4)
        return round(1.0 - penalty, 2)

    @property
    def verdict(self) -> str:
        if self.has_sorry_axiom:
            return "UNSOUND"
        if self.non_standard_axioms:
            return "SUSPECT"
        if self.direct_taints:
            return "WARN"
        return "TRUSTED"


@dataclass
class ProjectReport:
    root: Path
    theorems: List[TheoremReport] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.theorems)

    @property
    def unsound(self) -> List[TheoremReport]:
        return [t for t in self.theorems if t.verdict == "UNSOUND"]

    @property
    def suspect(self) -> List[TheoremReport]:
        return [t for t in self.theorems if t.verdict == "SUSPECT"]

    @property
    def trusted(self) -> List[TheoremReport]:
        return [t for t in self.theorems if t.verdict == "TRUSTED"]

    @property
    def overall_score(self) -> float:
        if not self.theorems:
            return 1.0
        return round(sum(t.trust_score for t in self.theorems) / len(self.theorems), 3)


def merge(
    file_analyses: List[FileAnalysis],
    axiom_results: List[AxiomResult],
) -> ProjectReport:
    axiom_map: Dict[str, AxiomResult] = {r.theorem: r for r in axiom_results}

    root = file_analyses[0].path.parent if file_analyses else Path(".")
    report = ProjectReport(root=root)

    for fa in file_analyses:
        theorems = fa.theorems
        for i, thm in enumerate(theorems):
            ar = axiom_map.get(thm.name)
            non_std = ar.non_standard_axioms if ar else []

            # Assign taints that fall within this theorem's line range
            next_line = theorems[i + 1].line if i + 1 < len(theorems) else float("inf")
            direct = [
                h for h in fa.direct_taints
                if thm.line <= h.line < next_line
            ]

            # In semantic mode use #print axioms; in syntactic mode fall back to direct hits
            if ar is not None:
                has_sorry = ar.has_sorry
            else:
                has_sorry = any(h.kind in ("sorry", "admit") for h in direct)

            report.theorems.append(TheoremReport(
                name=thm.name,
                file=thm.file,
                line=thm.line,
                direct_taints=direct,
                has_sorry_axiom=has_sorry,
                non_standard_axioms=non_std,
            ))

    return report


VERDICT_ICON = {
    "UNSOUND": "✗",
    "SUSPECT": "?",
    "WARN":    "!",
    "TRUSTED": "✓",
}


def render_text(report: ProjectReport) -> str:
    lines = []
    lines.append("=" * 64)
    lines.append("  SORRY AUDIT — Proof Trustworthiness Report")
    lines.append(f"  Project : {report.root}")
    lines.append(f"  Theorems: {report.total}  |  Overall score: {report.overall_score:.1%}")
    lines.append(f"  Trusted : {len(report.trusted)}  |  Unsound: {len(report.unsound)}  |  Suspect: {len(report.suspect)}")
    lines.append("=" * 64)

    if report.unsound:
        lines.append("\n[UNSOUND — depends on sorryAx]")
        for t in report.unsound:
            rel = t.file.name
            lines.append(f"  ✗  {t.name}  ({rel}:{t.line})")
            for hit in t.direct_taints[:3]:
                lines.append(f"       line {hit.line}: {hit.snippet[:72]}")

    if report.suspect:
        lines.append("\n[SUSPECT — non-standard axioms]")
        for t in report.suspect:
            rel = t.file.name
            lines.append(f"  ?  {t.name}  ({rel}:{t.line})")
            lines.append(f"       axioms: {', '.join(t.non_standard_axioms)}")

    warn = [t for t in report.theorems if t.verdict == "WARN"]
    if warn:
        lines.append("\n[WARN — suspicious patterns (native_decide / Unsafe)]")
        for t in warn:
            rel = t.file.name
            lines.append(f"  !  {t.name}  ({rel}:{t.line})")
            for hit in t.direct_taints[:3]:
                lines.append(f"       line {hit.line}: {hit.kind} — {hit.snippet[:72]}")

    if report.trusted:
        lines.append(f"\n[TRUSTED — {len(report.trusted)} theorems fully sound]")
        for t in report.trusted:
            lines.append(f"  ✓  {t.name}")

    lines.append("\n" + "=" * 64)
    return "\n".join(lines)


def render_json(report: ProjectReport) -> dict:
    return {
        "overall_score": report.overall_score,
        "total": report.total,
        "unsound_count": len(report.unsound),
        "suspect_count": len(report.suspect),
        "trusted_count": len(report.trusted),
        "theorems": [
            {
                "name": t.name,
                "file": str(t.file),
                "line": t.line,
                "verdict": t.verdict,
                "trust_score": t.trust_score,
                "has_sorry_axiom": t.has_sorry_axiom,
                "non_standard_axioms": t.non_standard_axioms,
                "direct_taint_kinds": list({h.kind for h in t.direct_taints}),
            }
            for t in report.theorems
        ],
    }
