"""FastMCP server exposing progressive, token-budgeted repo understanding.

Tools (read-only, idempotent):
  - repo_overview : cheap orientation — languages, layout, entry points.
  - repo_map      : ranked, token-budgeted symbol map (the flagship).

Run over stdio:  ``explain-repo-mcp [/path/to/repo]``
The repo can be set once via CLI/env and overridden per-call via ``repo_path``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .indexer import Indexer, supported_languages
from .overview import build_overview, render_overview
from .ranker import rank_tags, render_map

mcp = FastMCP(
    "explain-repo-mcp",
    instructions=(
        "Understand a codebase progressively without dumping it into context. "
        "Start with `repo_overview` to orient, then `repo_map` for a ranked, "
        "token-budgeted symbol map. Personalize the map with `focus` and scope "
        "it with `paths`. Every response is the least context that answers the "
        "question — drill down rather than dump."
    ),
)

# Default repo, set by main() from argv/env. Per-call repo_path overrides it.
_DEFAULT_REPO: Path | None = None
# Reuse one Indexer (and its SQLite cache) per repo across calls.
_indexers: dict[str, Indexer] = {}

_READONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)


# ---------------------------------------------------------------- output models
class LanguageStat(BaseModel):
    language: str
    files: int


class DirStat(BaseModel):
    dir: str
    files: int


class Overview(BaseModel):
    repo: str
    name: str
    total_files: int
    size_label: str = Field(description="tiny|small|medium|large|very large")
    languages: list[LanguageStat]
    config_files: list[str]
    entry_points: list[str]
    directories: list[DirStat]
    summary: str = Field(description="Compact human-readable orientation.")
    next_actions: list[str]


class Symbol(BaseModel):
    name: str
    line: int
    kind: str
    rank: float


class FileMap(BaseModel):
    file: str
    symbols: list[Symbol]


class RepoMap(BaseModel):
    repo: str
    focus: str | None
    paths: list[str] | None
    token_budget: int
    token_estimate: int
    truncated: bool = Field(description="True if symbols were dropped to fit budget.")
    ranked_symbol_count: int
    indexed: dict
    files: list[FileMap]
    text: str = Field(description="File-grouped ranked symbol map, budgeted.")
    next_actions: list[str]


# ----------------------------------------------------------------------- helpers
def _resolve_repo(repo_path: str | None) -> Path:
    candidate = repo_path or (str(_DEFAULT_REPO) if _DEFAULT_REPO else None) or os.getcwd()
    root = Path(candidate).expanduser().resolve()
    if not root.exists():
        raise ValueError(
            f"Repo path does not exist: {root}. Pass a valid `repo_path`, or start "
            f"the server with a path argument: `explain-repo-mcp /path/to/repo`."
        )
    if not root.is_dir():
        raise ValueError(f"Repo path is not a directory: {root}.")
    return root


def _get_indexer(root: Path) -> Indexer:
    key = str(root)
    if key not in _indexers:
        _indexers[key] = Indexer(root)
    return _indexers[key]


# ------------------------------------------------------------------------- tools
@mcp.tool(
    annotations=_READONLY,
    description=(
        "High-level orientation for a repository: languages, top-level layout, "
        "detected entry points, build/config files, and rough size. Always cheap "
        "and small — call this FIRST to decide where to look next."
    ),
)
def repo_overview(repo_path: str | None = None) -> Overview:
    root = _resolve_repo(repo_path)
    ov = build_overview(root)
    return Overview(
        repo=ov["repo"],
        name=ov["name"],
        total_files=ov["total_files"],
        size_label=ov["size_label"],
        languages=[LanguageStat(**l) for l in ov["languages"]],
        config_files=ov["config_files"],
        entry_points=ov["entry_points"],
        directories=[DirStat(**d) for d in ov["directories"]],
        summary=render_overview(ov),
        next_actions=[
            "Call repo_map to get a ranked symbol map.",
            "Pass focus=<question or filename> to repo_map to personalize ranking.",
            "Scope large repos with paths=[<subdir>].",
        ],
    )


@mcp.tool(
    annotations=_READONLY,
    description=(
        "Ranked, token-budgeted map of a repository's most central symbols, built "
        "with tree-sitter + PageRank. Returns the highest-signal definitions that "
        "fit `token_budget`, grouped by file. Use `focus` (a question, symbol, or "
        "filename) to personalize ranking toward what you care about, and `paths` "
        "to scope to sub-directories. A summary, never a full dump."
    ),
)
def repo_map(
    focus: str | None = None,
    token_budget: int = 2000,
    paths: list[str] | None = None,
    repo_path: str | None = None,
) -> RepoMap:
    root = _resolve_repo(repo_path)
    token_budget = max(200, min(token_budget, 20_000))
    indexer = _get_indexer(root)
    tags, stats = indexer.index(paths=paths)

    focus_terms = None
    focus_files = None
    if focus:
        focus_terms = [w for w in _tokenize(focus) if len(w) > 2]
        focus_files = [w for w in focus.split() if "/" in w or "." in w]

    ranked = rank_tags(tags, focus_files=focus_files, focus_terms=focus_terms)
    result = render_map(ranked, token_budget=token_budget)

    next_actions = []
    if result.truncated:
        next_actions.append(
            "Map was truncated to fit the budget. Raise token_budget, set "
            "paths=[<subdir>], or pass focus=<area> to narrow."
        )
    next_actions.append(
        "Inspect a symbol shown here with explain_symbol / find_usages / "
        "file_outline (coming in the drill-down toolset)."
    )

    return RepoMap(
        repo=str(root),
        focus=focus,
        paths=paths,
        token_budget=token_budget,
        token_estimate=result.token_estimate,
        truncated=result.truncated,
        ranked_symbol_count=result.ranked_symbol_count,
        indexed=stats,
        files=[
            FileMap(file=f["file"], symbols=[Symbol(**s) for s in f["symbols"]])
            for f in result.files
        ],
        text=result.text,
        next_actions=next_actions,
    )


def _tokenize(text: str) -> list[str]:
    out, cur = [], []
    for ch in text:
        if ch.isalnum() or ch == "_":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


# ----------------------------------------------------------------------- runtime
def main() -> None:
    global _DEFAULT_REPO
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    repo_arg = args[0] if args else os.environ.get("EXPLAIN_REPO_PATH")
    if repo_arg:
        _DEFAULT_REPO = Path(repo_arg).expanduser().resolve()
    transport = os.environ.get("EXPLAIN_REPO_TRANSPORT", "stdio")
    mcp.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
