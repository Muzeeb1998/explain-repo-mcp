<!-- mcp-name: io.github.Muzeeb1998/explain-repo-mcp -->

# Explain-Repo MCP

**Progressive, token-budgeted repo understanding for any MCP client — zero setup, language-agnostic.**

Explain-Repo gives Claude, Cursor, and other MCP clients the ability to *understand* a
codebase — its architecture, key symbols, and how things connect — **without dumping the
whole repo into context**. It is ruthlessly token-efficient: start with a small ranked map
that always fits a budget, then drill down on demand.

- 🧠 **Ranked, not raw.** tree-sitter + PageRank surface the most *central* symbols first (Aider's repo-map algorithm).
- 💸 **Token-budgeted.** Every map fits a budget you set. A summary, never a dump.
- ⚡ **Incremental.** mtime-keyed SQLite cache — re-indexing a changed repo is near-instant.
- 🔌 **Zero setup.** No language servers, no config. Point it at a repo and go.
- 🌍 **Language-agnostic.** tree-sitter grammars: Python, JS, TS/TSX, Go, Rust, Java, C, C++, Ruby, PHP, C#.

---

## Quickstart

```bash
# zero-install run with uv
uvx explain-repo-mcp /path/to/your/repo
```

or install:

```bash
pip install explain-repo-mcp
explain-repo-mcp /path/to/your/repo
```

### Claude Desktop / Claude Code

```jsonc
{
  "mcpServers": {
    "explain-repo": {
      "command": "uvx",
      "args": ["explain-repo-mcp", "/path/to/your/repo"]
    }
  }
}
```

### Cursor (`~/.cursor/mcp.json`)

```jsonc
{
  "mcpServers": {
    "explain-repo": {
      "command": "uvx",
      "args": ["explain-repo-mcp", "/path/to/your/repo"]
    }
  }
}
```

The repo path can also be set with the `EXPLAIN_REPO_PATH` env var, or overridden per-call
via the `repo_path` tool argument.

---

## Tools

| Tool | What it does | Cost |
|---|---|---|
| `repo_overview` | Languages, top-level layout, entry points, build files, size. **Call first.** | tiny |
| `repo_map` | Ranked, token-budgeted symbol map. `focus`, `token_budget`, `paths`. | budgeted |

> Drill-down tools (`search_code`, `explain_symbol`, `find_usages`, `file_outline`) are
> next on the roadmap.

### `repo_map` parameters

- `focus` — a question, symbol, or filename. Personalizes PageRank toward what you care about.
- `token_budget` — hard cap on output size (default 2000, clamped 200–20000).
- `paths` — scope to sub-directories, e.g. `["src/auth"]`.
- `repo_path` — override the default repo for this call.

---

## Why it wins

The #1 complaint about code MCP servers is **token bloat** — both schema bloat (too many
tools) and response bloat (dumping files). Explain-Repo attacks both: a small tool surface
and outputs that are *always* budgeted summaries.

| Approach | Behavior | Cost on a big repo |
|---|---|---|
| Pack-the-repo (Repomix-style) | Dumps entire repo into context | Breaks past ~10k files; massive tokens |
| LSP-backed (Serena) | Powerful, symbol-level | Heavy per-language setup |
| **Explain-Repo** | **Ranked map + on-demand drill-down** | **Orientation in <2k tokens, zero setup** |

---

## How it works

```
MCP layer (FastMCP)  →  6-tool surface, structured output, read-only
Retrieval layer      →  PageRank ranking + token budgeting
Index layer          →  tree-sitter tags (grep-ast) → symbol graph → SQLite cache
```

Built on Aider's battle-tested repo-map algorithm via `grep-ast` and
`tree-sitter-language-pack`.

---

## Development

```bash
uv venv --python 3.11 && uv pip install -e ".[dev]"
EXPLAIN_REPO_PATH=. python -m explain_repo_mcp.server   # stdio
npx @modelcontextprotocol/inspector uvx explain-repo-mcp .   # inspect
```

## License

MIT
