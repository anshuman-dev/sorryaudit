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
    r'^\s*(?:theorem|lemma|def|noncomputable def|abbrev|elab|macro|syntax|notation|@\[)\s+(\w[\w\'\.]*)',
    re.MULTILINE
)

IMPORT_RE = re.compile(r'^\s*import\s+([\w\.]+)', re.MULTILINE)

# Matches double-quoted string literals including multi-line continuations
STRING_LITERAL_RE = re.compile(r'"(?:[^"\\]|\\.)*"', re.DOTALL)


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
    transitive_sorry: bool = False


@dataclass
class FileAnalysis:
    path: Path
    imports: List[str]
    theorems: List[TheoremInfo]
    direct_taints: List[TaintHit]


def _clean_source(src: str) -> str:
    """
    Strip line comments and string literals while preserving line numbers.
    This prevents keywords inside comments or strings from being flagged as taint.
    """
    # Strip -- comments first
    lines = []
    for line in src.splitlines(keepends=True):
        pos = line.find('--')
        if pos >= 0:
            tail = line[pos:]
            line = line[:pos] + ' ' * (len(tail) - (1 if tail.endswith('\n') else 0))
            if tail.endswith('\n'):
                line += '\n'
        lines.append(line)
    cleaned = ''.join(lines)

    # Replace string literal contents with spaces (keep quotes to preserve positions)
    def blank_string(m: re.Match) -> str:
        inner = m.group(0)
        # Replace everything between the outer quotes with spaces
        return '"' + ' ' * (len(inner) - 2) + '"'

    return STRING_LITERAL_RE.sub(blank_string, cleaned)


def analyse_file(path: Path) -> FileAnalysis:
    src = path.read_text(errors="replace")
    lines = src.splitlines()
    cleaned = _clean_source(src)

    imports = IMPORT_RE.findall(src)

    direct_taints: List[TaintHit] = []
    for kind, pat in TAINT_PATTERNS.items():
        for m in pat.finditer(cleaned):
            lineno = cleaned[:m.start()].count('\n') + 1
            col = m.start() - cleaned[:m.start()].rfind('\n') - 1
            snippet = lines[lineno - 1].strip() if lineno <= len(lines) else ""
            direct_taints.append(TaintHit(kind, lineno, col, snippet))

    theorems: List[TheoremInfo] = []
    for m in THEOREM_DEF.finditer(src):
        lineno = src[:m.start()].count('\n') + 1
        theorems.append(TheoremInfo(name=m.group(1), file=path, line=lineno))

    return FileAnalysis(path=path, imports=imports, theorems=theorems, direct_taints=direct_taints)


def analyse_project(root: Path) -> List[FileAnalysis]:
    results = []
    for lean_file in sorted(root.rglob("*.lean")):
        if ".lake" in lean_file.parts:
            continue
        results.append(analyse_file(lean_file))
    return results
