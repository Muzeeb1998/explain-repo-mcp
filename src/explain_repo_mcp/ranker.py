"""Ranking layer: symbol graph + (personalized) PageRank + token budgeting.

Adapts Aider's repo-map algorithm. Files/symbols form a directed graph where an
edge ``referencer -> definer`` means the referencer uses a symbol the definer
declares. PageRank surfaces the most central definitions; an optional ``focus``
personalizes the walk toward the files/terms the agent cares about.

The serialized map is *budgeted*: highest-ranked definitions are emitted until a
token budget is hit, so the output is always a summary, never a dump.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import networkx as nx

from .indexer import Tag
from .tokens import count_tokens


@dataclass
class RankedDef:
    rel_fname: str
    name: str
    kind: str          # def kind label from capture (function/class/...) — best effort
    line: int
    rank: float


@dataclass
class MapResult:
    text: str
    files: list[dict] = field(default_factory=list)  # {file, symbols:[{name,line,kind,rank}]}
    token_estimate: int = 0
    truncated: bool = False
    ranked_symbol_count: int = 0


def rank_tags(
    tags: list[Tag],
    focus_files: list[str] | None = None,
    focus_terms: list[str] | None = None,
) -> list[RankedDef]:
    """Return definitions sorted by PageRank-derived importance (desc)."""
    defines: dict[str, set[str]] = defaultdict(set)        # ident -> {rel_fname}
    references: dict[str, list[str]] = defaultdict(list)   # ident -> [rel_fname]
    definitions: dict[tuple[str, str], list[Tag]] = defaultdict(list)

    for tag in tags:
        if tag.kind == "def":
            defines[tag.name].add(tag.rel_fname)
            definitions[(tag.rel_fname, tag.name)].append(tag)
        else:  # ref
            references[tag.name].append(tag.rel_fname)

    # If a repo has no references (tiny / unsupported), treat defs as self-refs
    # so PageRank still has a graph to rank.
    if not references:
        references = {k: list(v) for k, v in defines.items()}

    focus_terms_lc = [t.lower() for t in (focus_terms or [])]
    idents = set(defines) & set(references)

    graph = nx.MultiDiGraph()
    for ident in idents:
        definers = defines[ident]
        # boost symbols that match a focus term
        mul = 10.0 if any(t in ident.lower() for t in focus_terms_lc) else 1.0
        for referencer, num_refs in Counter(references[ident]).items():
            weight = mul * math.sqrt(num_refs)
            for definer in definers:
                graph.add_edge(referencer, definer, weight=weight, ident=ident)

    if graph.number_of_nodes() == 0:
        # no edges — fall back to flat ordering of defs
        flat = [
            RankedDef(rel, name, _kind_of(tag_list), tag_list[0].line, 0.0)
            for (rel, name), tag_list in definitions.items()
        ]
        flat.sort(key=lambda d: (d.rel_fname, d.line))
        return flat

    personalization = _build_personalization(graph, focus_files)
    try:
        ranked = nx.pagerank(graph, weight="weight", personalization=personalization)
    except (ZeroDivisionError, nx.PowerIterationFailedConvergence):
        ranked = {n: 1.0 / graph.number_of_nodes() for n in graph.nodes}

    # distribute each node's rank across its outgoing edges (by ident)
    ranked_def_score: dict[tuple[str, str], float] = defaultdict(float)
    for src in graph.nodes:
        src_rank = ranked.get(src, 0.0)
        out_edges = list(graph.out_edges(src, data=True))
        total_w = sum(d["weight"] for _, _, d in out_edges) or 1.0
        for _, dst, data in out_edges:
            ranked_def_score[(dst, data["ident"])] += src_rank * data["weight"] / total_w

    results: list[RankedDef] = []
    seen: set[tuple[str, str]] = set()
    for (rel, ident), score in ranked_def_score.items():
        tag_list = definitions.get((rel, ident))
        if not tag_list:
            continue
        seen.add((rel, ident))
        results.append(RankedDef(rel, ident, _kind_of(tag_list), tag_list[0].line, score))

    # include definitions that were never referenced (rank 0) so they still show
    for (rel, ident), tag_list in definitions.items():
        if (rel, ident) not in seen:
            results.append(RankedDef(rel, ident, _kind_of(tag_list), tag_list[0].line, 0.0))

    results.sort(key=lambda d: (-d.rank, d.rel_fname, d.line))
    return results


def _kind_of(tag_list: list[Tag]) -> str:
    # Tags only carry def/ref; without per-capture kind we label generically.
    return "def"


def _build_personalization(
    graph: nx.MultiDiGraph, focus_files: list[str] | None
) -> dict | None:
    if not focus_files:
        return None
    nodes = set(graph.nodes)
    pers = {}
    for f in focus_files:
        for n in nodes:
            if n == f or n.endswith(f) or f in n:
                pers[n] = pers.get(n, 0.0) + 1.0
    if not pers:
        return None
    total = sum(pers.values())
    return {n: pers.get(n, 0.0) / total for n in nodes}


def render_map(
    ranked: list[RankedDef],
    token_budget: int = 2000,
) -> MapResult:
    """Serialize the ranked defs into a budgeted, file-grouped text map."""
    if not ranked:
        return MapResult(text="(no symbols found)", token_estimate=0)

    # Greedily select highest-ranked defs until the rendered text hits budget.
    # Group selected defs by file, preserving best-rank file ordering.
    chosen: list[RankedDef] = []
    by_file: dict[str, list[RankedDef]] = defaultdict(list)
    file_order: list[str] = []
    running = ""
    truncated = False

    for rd in ranked:
        # tentative rendering of this line (+ header if a new file)
        header = "" if rd.rel_fname in by_file else f"{rd.rel_fname}:\n"
        line = f"  {rd.line + 1}: {rd.name}\n"
        candidate = running + header + line
        if count_tokens(candidate) > token_budget and chosen:
            truncated = True
            break
        running = candidate
        if rd.rel_fname not in by_file:
            file_order.append(rd.rel_fname)
        by_file[rd.rel_fname].append(rd)
        chosen.append(rd)

    files_out = []
    text_blocks = []
    for f in file_order:
        defs = sorted(by_file[f], key=lambda d: d.line)
        files_out.append({
            "file": f,
            "symbols": [
                {"name": d.name, "line": d.line + 1, "kind": d.kind,
                 "rank": round(d.rank, 6)}
                for d in defs
            ],
        })
        block = f"{f}:\n" + "".join(f"  {d.line + 1}: {d.name}\n" for d in defs)
        text_blocks.append(block)

    text = "".join(text_blocks).rstrip("\n")
    return MapResult(
        text=text,
        files=files_out,
        token_estimate=count_tokens(text),
        truncated=truncated or len(chosen) < len(ranked),
        ranked_symbol_count=len(ranked),
    )
