import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List


TAINT_PATTERNS = {
    "sorry":         re.compile(r'\bsorry\b'),
    "admit":         re.compile(r'\badmit\b'),
    "native_decide": re.compile(r'\bnative_decide\b'),
    "unsafe_cast":   re.compile(r'\bUnsafe\.cast\b'),
    "unsafeOfFn":    re.compile(r'\bUnsafe\.ofFn\b'),
}

THEOREM_DEF = re.compile(
    r'^\s*(?:theorem|lemma|def|noncomputable def|abbrev)\s+(\w[\w\'\.]*)',
    re.MULTILINE
)

IMPORT_RE = re.compile(r'^\s*import\s+([\w\.]+)', re.MULTILINE)


@dataclass
class TaintHit:
    kind: str
    line: int
    col: int
    snippet: str


@dataclass
class TheoremInfo:
    name: str
    file: Path
    line: int
    direct_taints: List[TaintHit] = field(default_factory=list)
    transitive_sorry: bool = False  # set by #print axioms output


@dataclass
class FileAnalysis:
    path: Path
    imports: List[str]
    theorems: List[TheoremInfo]
    direct_taints: List[TaintHit]


def _strip_comments(src: str) -> str:
    """Replace -- line comments with spaces to preserve line numbers."""
    result = []
    for line in src.splitlines(keepends=True):
        comment_pos = line.find('--')
        if comment_pos >= 0:
            result.append(line[:comment_pos] + ' ' * (len(line) - comment_pos - (1 if line.endswith('\n') else 0)) + ('\n' if line.endswith('\n') else ''))
        else:
            result.append(line)
    return ''.join(result)


def analyse_file(path: Path) -> FileAnalysis:
    src = path.read_text(errors="replace")
    lines = src.splitlines()
    src_no_comments = _strip_comments(src)

    imports = IMPORT_RE.findall(src)

    direct_taints: List[TaintHit] = []
    for kind, pat in TAINT_PATTERNS.items():
        for m in pat.finditer(src_no_comments):
            lineno = src_no_comments[:m.start()].count('\n') + 1
            col = m.start() - src_no_comments[:m.start()].rfind('\n') - 1
            direct_taints.append(TaintHit(kind, lineno, col, lines[lineno - 1].strip()))

    theorems: list[TheoremInfo] = []
    for m in THEOREM_DEF.finditer(src):
        lineno = src[:m.start()].count('\n') + 1
        theorems.append(TheoremInfo(name=m.group(1), file=path, line=lineno))

    return FileAnalysis(path=path, imports=imports, theorems=theorems, direct_taints=direct_taints)


def analyse_project(root: Path) -> list[FileAnalysis]:
    results = []
    for lean_file in sorted(root.rglob("*.lean")):
        if ".lake" in lean_file.parts:
            continue
        results.append(analyse_file(lean_file))
    return results
