"""Drill-down layer: outline, usages, symbol explanation, keyword search.

Each function returns the *least* context that answers the question — signatures
not bodies, paginated references not dumps — so the agent stays well under the
token cost of pack-the-repo tools.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from .indexer import Indexer
from .walker import walk_files

_DEF_PRIORITY = {  # nicer ordering when a name has several def kinds
    "class": 0, "interface": 1, "type": 2, "enum": 3,
    "function": 4, "method": 5, "module": 6, "macro": 7,
}


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def file_outline(indexer: Indexer, rel: str) -> dict:
    """Signatures/headings of one file — no bodies."""
    root = indexer.root
    path = root / rel
    if not path.is_file():
        return {"file": rel, "error": f"File not found: {rel}", "symbols": []}
    tags = [t for t in indexer.tags_for_file(rel) if t.kind == "def"]
    lines = _read_lines(path)
    symbols = []
    for t in sorted(tags, key=lambda x: x.line):
        sig = lines[t.line].strip() if 0 <= t.line < len(lines) else ""
        symbols.append({
            "name": t.name,
            "kind": t.detail or "def",
            "line": t.line + 1,
            "signature": sig[:200],
        })
    return {
        "file": rel,
        "language_lines": len(lines),
        "symbol_count": len(symbols),
        "symbols": symbols,
    }


def find_usages(
    indexer: Indexer, name: str, page: int = 1, page_size: int = 50,
    paths: list[str] | None = None,
) -> dict:
    """All references to a symbol across the repo, paginated."""
    tags, _ = indexer.index(paths=paths)
    refs = [t for t in tags if t.kind == "ref" and t.name == name]
    defs = [t for t in tags if t.kind == "def" and t.name == name]
    refs.sort(key=lambda t: (t.rel_fname, t.line))
    total = len(refs)
    page = max(1, page)
    start = (page - 1) * page_size
    window = refs[start:start + page_size]
    return {
        "symbol": name,
        "total_usages": total,
        "page": page,
        "page_size": page_size,
        "has_more": start + page_size < total,
        "defined_at": [
            {"file": d.rel_fname, "line": d.line + 1, "kind": d.detail or "def"}
            for d in sorted(defs, key=lambda t: (t.rel_fname, t.line))
        ],
        "usages": [{"file": t.rel_fname, "line": t.line + 1} for t in window],
    }


def explain_symbol(
    indexer: Indexer, name: str, context_lines: int = 4, max_refs: int = 25,
) -> dict:
    """Signature + defining file:line + surrounding context + where referenced."""
    tags, _ = indexer.index()
    defs = [t for t in tags if t.kind == "def" and t.name == name]
    refs = [t for t in tags if t.kind == "ref" and t.name == name]
    if not defs:
        all_def_names = sorted({t.name for t in tags if t.kind == "def"})
        suggestions = difflib.get_close_matches(name, all_def_names, n=10, cutoff=0.5)
        # also include substring matches not already suggested
        for nm in all_def_names:
            if name.lower() in nm.lower() and nm not in suggestions:
                suggestions.append(nm)
        return {
            "symbol": name,
            "found": False,
            "error": f"No definition found for '{name}'.",
            "did_you_mean": suggestions,
        }

    defs.sort(key=lambda t: (_DEF_PRIORITY.get(t.detail, 9), t.rel_fname, t.line))
    definitions = []
    for d in defs[:5]:
        lines = _read_lines(indexer.root / d.rel_fname)
        lo = max(0, d.line - 0)
        hi = min(len(lines), d.line + context_lines + 1)
        snippet = "\n".join(lines[lo:hi])
        definitions.append({
            "file": d.rel_fname,
            "line": d.line + 1,
            "kind": d.detail or "def",
            "signature": lines[d.line].strip()[:200] if d.line < len(lines) else "",
            "context": snippet,
        })

    ref_locs = sorted({(t.rel_fname, t.line) for t in refs})
    return {
        "symbol": name,
        "found": True,
        "definition_count": len(defs),
        "definitions": definitions,
        "reference_count": len(refs),
        "referenced_in_files": sorted({t.rel_fname for t in refs})[:20],
        "sample_references": [
            {"file": f, "line": ln + 1} for f, ln in ref_locs[:max_refs]
        ],
    }


def search_code(
    indexer: Indexer, query: str, page: int = 1, page_size: int = 30,
    regex: bool = False, paths: list[str] | None = None, max_scan: int = 5000,
) -> dict:
    """Keyword/regex search returning ranked file:line snippets, paginated."""
    if not query:
        return {"query": query, "error": "Empty query.", "matches": []}
    try:
        pattern = re.compile(query if regex else re.escape(query), re.IGNORECASE)
    except re.error as e:
        return {"query": query, "error": f"Invalid regex: {e}", "matches": []}

    hits: list[dict] = []
    scanned = 0
    for rel in walk_files(indexer.root, paths):
        if scanned >= max_scan:
            break
        scanned += 1
        for i, line in enumerate(_read_lines(indexer.root / rel)):
            if pattern.search(line):
                hits.append({
                    "file": rel,
                    "line": i + 1,
                    "snippet": line.strip()[:200],
                })
                if len(hits) > 2000:  # safety cap
                    break
    total = len(hits)
    page = max(1, page)
    start = (page - 1) * page_size
    window = hits[start:start + page_size]
    return {
        "query": query,
        "regex": regex,
        "total_matches": total,
        "files_scanned": scanned,
        "page": page,
        "page_size": page_size,
        "has_more": start + page_size < total,
        "matches": window,
    }
