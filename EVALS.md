# Evaluation Suite

Ten questions for wiring a model to the server and checking it (a) picks the
right tool, (b) gets a correct answer, and (c) stays token-cheap. Questions are
**independent, read-only, complex, verifiable, and stable** (answers are pinned
to this repository's own source, so they don't drift).

Run the server against its own repo:

```bash
explain-repo-mcp /path/to/explain-repo-mcp
```

| # | Question | Expected tool(s) | Verifiable answer |
|---|---|---|---|
| 1 | What languages and build system does this repo use? | `repo_overview` | Python; `pyproject.toml`; languages include python + scheme (the bundled `.scm` queries). |
| 2 | What are the core symbols of the ranking layer? | `repo_map` (focus="rank") | Ranking symbols from `ranker.py` — `RankedDef`, `render_map`, `rank_tags` — surface near the top of the focused map. |
| 3 | Where is `count_tokens` defined and how many times is it used? | `explain_symbol` or `find_usages` | Defined in `src/explain_repo_mcp/tokens.py`; referenced from `ranker.py` (≥2 usages). |
| 4 | What functions/classes does `ranker.py` contain, without reading the whole file? | `file_outline` | `RankedDef`, `MapResult`, `rank_tags`, `_kind_of`, `_build_personalization`, `render_map`. |
| 5 | How is the SQLite cache invalidated? | `search_code` ("mtime") then `explain_symbol` / read | Keyed by `(path, mtime, size)` in `indexer.py` `_cached`/`tags_for_file`. |
| 6 | Which file defines the MCP tools, and how many tools are registered? | `search_code` ("@mcp.tool") | `src/explain_repo_mcp/server.py`; 6 tools. |
| 7 | What is the default token budget for `repo_map` and where is it clamped? | `explain_symbol("repo_map")` / `search_code` | Default 2000; clamped to 200–20000 in `server.py` `repo_map`. |
| 8 | Where is `.gitignore` honored during the file walk? | `find_usages("load_ignore_spec")` / `file_outline` | `walker.py` — `load_ignore_spec` + `_accept` (pathspec match). |
| 9 | Which languages have tag queries bundled? | `repo_overview` + `search_code("LANG_TO_QUERY")` | 12: python, javascript, typescript/tsx, go, rust, java, c, cpp, ruby, php, csharp. |
| 10 | Give a budgeted map of just the index layer. | `repo_map` (paths=["src/explain_repo_mcp"], focus="index cache") | Surfaces `Indexer`, `extract_tags`, `tags_for_file`, `index` under budget. |

## What to grade

- **Tool choice.** Did the model reach for the smallest sufficient tool (e.g.
  `file_outline` for #4, not dumping the file)?
- **Correctness.** Does the answer match the pinned answer above?
- **Token cost.** Record `token_estimate` for map calls and total response size.
  The bar (from the build plan): orient in **<2k tokens**; drill-down answers a
  fraction of a pack-the-repo tool's cost.

## Quick harness

`tests/` already covers the pipeline deterministically (19 tests). For
model-in-the-loop evals, point any MCP client at the server and walk the table
above, logging tool name + token counts per turn.
