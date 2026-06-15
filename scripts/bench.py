"""Token-efficiency benchmark + smoke run for explain-repo-mcp.

For each target repo: spins the server over stdio, calls every tool, and compares
the cost of *orienting* (repo_overview + repo_map) against the "pack-the-repo"
baseline (tiktoken count of all source concatenated). Prints a savings table.

Usage:
    python scripts/bench.py <repo_path> [<repo_path> ...]
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# import package bits directly for the baseline
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from explain_repo_mcp.tokens import count_tokens  # noqa: E402
from explain_repo_mcp.walker import walk_files  # noqa: E402

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

SERVER = str(Path(__file__).resolve().parent.parent / ".venv" / "bin" / "explain-repo-mcp")


def dump_baseline_tokens(repo: str) -> tuple[int, int]:
    """Tokens to pack the whole repo into context (the thing we beat)."""
    root = Path(repo)
    total_tokens = 0
    files = 0
    for rel in walk_files(root):
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        total_tokens += count_tokens(text)
        files += 1
    return total_tokens, files


async def bench_repo(repo: str) -> dict:
    baseline_tokens, files = dump_baseline_tokens(repo)
    params = StdioServerParameters(command=SERVER, args=[repo])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            ov = (await s.call_tool("repo_overview", {})).structuredContent
            ov_tokens = count_tokens(ov["summary"])

            mp = (await s.call_tool("repo_map", {"token_budget": 2000})).structuredContent
            map_tokens = mp["token_estimate"]

            # pick the top-ranked symbol and drill into it
            top = None
            for f in mp["files"]:
                if f["symbols"]:
                    top = f["symbols"][0]["name"]
                    break

            explain = usages = outline = search = None
            if top:
                es = (await s.call_tool("explain_symbol", {"symbol": top})).structuredContent
                explain = {
                    "symbol": top,
                    "found": es["found"],
                    "defs": es["definition_count"],
                    "refs": es["reference_count"],
                    "tokens": count_tokens(json.dumps(es)),
                }
                fu = (await s.call_tool("find_usages", {"symbol": top})).structuredContent
                usages = {"symbol": top, "total": fu["total_usages"]}

            first_file = mp["files"][0]["file"] if mp["files"] else None
            if first_file:
                fo = (await s.call_tool("file_outline", {"file": first_file})).structuredContent
                outline = {"file": first_file, "symbols": fo["symbol_count"]}

            sc = (await s.call_tool("search_code", {"query": top or "def"})).structuredContent
            search = {"query": top or "def", "matches": sc["total_matches"]}

    orient_tokens = ov_tokens + map_tokens
    savings = (1 - orient_tokens / baseline_tokens) * 100 if baseline_tokens else 0.0
    return {
        "repo": Path(repo).name,
        "files": files,
        "baseline_tokens": baseline_tokens,
        "overview_tokens": ov_tokens,
        "map_tokens": map_tokens,
        "orient_tokens": orient_tokens,
        "savings_pct": round(savings, 1),
        "map_languages": mp["indexed"]["languages"],
        "map_truncated": mp["truncated"],
        "explain": explain,
        "usages": usages,
        "outline": outline,
        "search": search,
    }


async def main(repos: list[str]) -> None:
    results = []
    for repo in repos:
        try:
            results.append(await bench_repo(repo))
        except Exception as e:  # noqa: BLE001
            print(f"!! {repo}: {type(e).__name__}: {e}")

    print("\n" + "=" * 78)
    print("TOKEN EFFICIENCY — orient (overview+map) vs pack-the-repo dump")
    print("=" * 78)
    hdr = f"{'repo':<14}{'files':>6}{'dump tok':>10}{'orient tok':>12}{'savings':>9}"
    print(hdr)
    print("-" * 78)
    for r in results:
        print(f"{r['repo']:<14}{r['files']:>6}{r['baseline_tokens']:>10}"
              f"{r['orient_tokens']:>12}{r['savings_pct']:>8}%")
    print("-" * 78)

    print("\nTOOL SMOKE (per repo):")
    for r in results:
        print(f"\n• {r['repo']}  langs={r['map_languages']} map_truncated={r['map_truncated']}")
        print(f"    overview={r['overview_tokens']}tok  map={r['map_tokens']}tok")
        if r["explain"]:
            e = r["explain"]
            print(f"    explain_symbol({e['symbol']}): found={e['found']} "
                  f"defs={e['defs']} refs={e['refs']} ({e['tokens']}tok)")
        if r["usages"]:
            print(f"    find_usages({r['usages']['symbol']}): {r['usages']['total']} usages")
        if r["outline"]:
            print(f"    file_outline({r['outline']['file']}): {r['outline']['symbols']} symbols")
        if r["search"]:
            print(f"    search_code({r['search']['query']}): {r['search']['matches']} matches")


if __name__ == "__main__":
    targets = sys.argv[1:]
    if not targets:
        print("usage: python scripts/bench.py <repo> [<repo> ...]")
        sys.exit(1)
    asyncio.run(main(targets))
