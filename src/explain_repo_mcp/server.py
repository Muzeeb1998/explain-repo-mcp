"""FastMCP server exposing progressive, token-budgeted repo understanding.

Tools (all read-only, idempotent):
  - repo_overview : cheap orientation — languages, layout, entry points.
  - repo_map      : ranked, token-budgeted symbol map (the flagship).
  - file_outline  : signatures of one file — no bodies.
  - explain_symbol: signature + context + references for one symbol.
  - find_usages   : all references to a symbol, paginated.
  - search_code   : keyword/regex search, ranked snippets, paginated.

Run over stdio:  ``explain-repo-mcp [/path/to/repo]``
The repo can be set once via CLI/env and overridden per-call via ``repo_path``.

Environment:
  EXPLAIN_REPO_PATH       default repo path
  EXPLAIN_REPO_TRANSPORT  stdio (default) | streamable-http | sse
  EXPLAIN_REPO_CACHE_DIR  override SQLite cache location
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .drilldown import explain_symbol, file_outline, find_usages, search_code
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


# --- drill-down models (fields optional so error paths validate cleanly) ----
class OutlineSymbol(BaseModel):
    name: str
    kind: str
    line: int
    signature: str = ""


class FileOutline(BaseModel):
    file: str
    error: str | None = None
    language_lines: int = 0
    symbol_count: int = 0
    symbols: list[OutlineSymbol] = []
    next_actions: list[str] = []


class Loc(BaseModel):
    file: str
    line: int


class DefLoc(BaseModel):
    file: str
    line: int
    kind: str = "def"


class SymbolDef(BaseModel):
    file: str
    line: int
    kind: str
    signature: str = ""
    context: str = ""


class ExplainResult(BaseModel):
    symbol: str
    found: bool
    error: str | None = None
    did_you_mean: list[str] = []
    definition_count: int = 0
    definitions: list[SymbolDef] = []
    reference_count: int = 0
    referenced_in_files: list[str] = []
    sample_references: list[Loc] = []
    next_actions: list[str] = []


class Usages(BaseModel):
    symbol: str
    total_usages: int = 0
    page: int = 1
    page_size: int = 50
    has_more: bool = False
    defined_at: list[DefLoc] = []
    usages: list[Loc] = []
    next_actions: list[str] = []


class Match(BaseModel):
    file: str
    line: int
    snippet: str = ""


class SearchResult(BaseModel):
    query: str
    error: str | None = None
    regex: bool = False
    total_matches: int = 0
    files_scanned: int = 0
    page: int = 1
    page_size: int = 30
    has_more: bool = False
    matches: list[Match] = []
    next_actions: list[str] = []


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
        cache_env = os.environ.get("EXPLAIN_REPO_CACHE_DIR")
        cache_dir = Path(cache_env).expanduser() if cache_env else None
        _indexers[key] = Indexer(root, cache_dir=cache_dir)
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
        "Inspect a symbol shown here with explain_symbol, find_usages, or "
        "file_outline. Use search_code for keyword/regex lookups."
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


@mcp.tool(
    name="file_outline",
    annotations=_READONLY,
    description=(
        "Skeleton of a single file: every definition's name, kind, line, and "
        "signature line — no bodies. Lets you decide what's worth reading fully "
        "before spending tokens on it."
    ),
)
def file_outline_tool(file: str, repo_path: str | None = None) -> FileOutline:
    root = _resolve_repo(repo_path)
    indexer = _get_indexer(root)
    out = file_outline(indexer, file)
    out["next_actions"] = [
        "Read a specific symbol's full body with your editor/file tools, or call "
        "explain_symbol for its definition + references.",
    ]
    return FileOutline.model_validate(out)


@mcp.tool(
    name="explain_symbol",
    annotations=_READONLY,
    description=(
        "Explain one symbol: its signature, defining file:line, a few lines of "
        "surrounding context, and where it is referenced across the repo. "
        "Drill-down, not a dump. If the symbol is unknown, suggests near matches."
    ),
)
def explain_symbol_tool(
    symbol: str, context_lines: int = 4, repo_path: str | None = None
) -> ExplainResult:
    root = _resolve_repo(repo_path)
    indexer = _get_indexer(root)
    out = explain_symbol(indexer, symbol, context_lines=max(0, min(context_lines, 20)))
    out["next_actions"] = [
        "Call find_usages for the full, paginated reference list.",
        "Call file_outline on a defining file to see its other symbols.",
    ]
    return ExplainResult.model_validate(out)


@mcp.tool(
    name="find_usages",
    annotations=_READONLY,
    description=(
        "All references to a symbol across the repo, paginated. Returns where it "
        "is defined plus a page of usage file:line locations."
    ),
)
def find_usages_tool(
    symbol: str, page: int = 1, page_size: int = 50,
    paths: list[str] | None = None, repo_path: str | None = None,
) -> Usages:
    root = _resolve_repo(repo_path)
    indexer = _get_indexer(root)
    out = find_usages(indexer, symbol, page=page,
                      page_size=max(1, min(page_size, 200)), paths=paths)
    if out.get("has_more"):
        out["next_actions"] = [f"Call again with page={out['page'] + 1} for more usages."]
    return Usages.model_validate(out)


@mcp.tool(
    name="search_code",
    annotations=_READONLY,
    description=(
        "Keyword or regex search across the repo's source. Returns ranked "
        "file:line snippets, paginated. Set regex=true for pattern search. Scope "
        "with paths=[<subdir>]."
    ),
)
def search_code_tool(
    query: str, page: int = 1, page_size: int = 30, regex: bool = False,
    paths: list[str] | None = None, repo_path: str | None = None,
) -> SearchResult:
    root = _resolve_repo(repo_path)
    indexer = _get_indexer(root)
    out = search_code(indexer, query, page=page,
                      page_size=max(1, min(page_size, 100)), regex=regex, paths=paths)
    if out.get("has_more"):
        out["next_actions"] = [f"Call again with page={out['page'] + 1} for more matches."]
    return SearchResult.model_validate(out)


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
