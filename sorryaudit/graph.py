"""
Taint dependency graph renderer.
Outputs DOT format (Graphviz) and a plain-text tree view.
"""
from pathlib import Path
from typing import List, Dict, Set
from report import ProjectReport, TheoremReport


VERDICT_COLOR = {
    "UNSOUND": "red",
    "SUSPECT": "orange",
    "WARN":    "yellow",
    "TRUSTED": "green",
}

VERDICT_SHAPE = {
    "UNSOUND": "box",
    "SUSPECT": "diamond",
    "WARN":    "ellipse",
    "TRUSTED": "ellipse",
}


def render_dot(report: ProjectReport) -> str:
    """Render a DOT graph showing all theorems colored by verdict."""
    lines = ["digraph sorryaudit {"]
    lines.append('  rankdir=LR;')
    lines.append('  node [fontname="monospace", fontsize=10];')

    for t in report.theorems:
        color = VERDICT_COLOR[t.verdict]
        shape = VERDICT_SHAPE[t.verdict]
        label = f"{t.name}\\n{t.file.name}:{t.line}"
        style = 'filled' if t.verdict in ("UNSOUND", "SUSPECT") else 'solid'
        lines.append(
            f'  "{t.name}" [label="{label}", color="{color}", '
            f'shape="{shape}", style="{style}"];'
        )

    lines.append("}")
    return "\n".join(lines)


def render_text_tree(report: ProjectReport) -> str:
    """
    Render a compact text summary grouped by file,
    showing taint propagation with indentation.
    """
    by_file: Dict[Path, List[TheoremReport]] = {}
    for t in report.theorems:
        by_file.setdefault(t.file, []).append(t)

    lines = []
    icon = {"UNSOUND": "x", "SUSPECT": "?", "WARN": "!", "TRUSTED": "v"}

    for fpath, theorems in sorted(by_file.items()):
        lines.append(f"\n{fpath.name}")
        for t in theorems:
            prefix = icon[t.verdict]
            detail = ""
            if t.has_sorry_axiom:
                detail = " [sorryAx]"
            elif t.non_standard_axioms:
                detail = f" [{', '.join(t.non_standard_axioms[:2])}]"
            elif t.direct_taints:
                kinds = list({h.kind for h in t.direct_taints})
                detail = f" [{', '.join(kinds)}]"
            lines.append(f"  {prefix}  {t.name}{detail}")

    return "\n".join(lines)
