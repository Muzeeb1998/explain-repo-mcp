# Publishing `explain-repo-mcp`

How to publish this Python MCP server to **PyPI** and the **official MCP Registry**.

| Field | Value |
|-------|-------|
| Package name | `explain-repo-mcp` |
| Version | `0.1.0` |
| GitHub repo | https://github.com/Muzeeb1998/explain-repo-mcp |
| Registry namespace | `io.github.Muzeeb1998/explain-repo-mcp` |

The repo already has a `server.json` at the root and an `<!-- mcp-name: io.github.Muzeeb1998/explain-repo-mcp -->` marker as the first line of `README.md`.

---

## 1. Build

Build the wheel and source distribution into `dist/`:

```bash
uv build
```

This produces both a wheel (`.whl`) and an sdist (`.tar.gz`) in `dist/`.

---

## 2. Publish to PyPI

You need a PyPI account and an API token. Create one at:
https://pypi.org/manage/account/token/

**Recommended — publish with `uv`:**

```bash
uv publish --token <PYPI_TOKEN>
```

Or pass the token via environment variable:

```bash
export UV_PUBLISH_TOKEN=<PYPI_TOKEN>
uv publish
```

**Alternative — publish with `twine`:**

```bash
twine upload dist/*
```

> **Note:** The package name must be available on PyPI. If `explain-repo-mcp` is already taken, rename the project under `[project] name` in `pyproject.toml` (and update `server.json` to match) before publishing.

**Verify** (allow a minute or two for index propagation):

```bash
uvx explain-repo-mcp --help
# or
uvx explain-repo-mcp /path/to/repo
```

---

## 3. Publish to the official MCP Registry

The registry stores **metadata only** — the package must already be live on PyPI. **Do step 2 first.**

1. **Install the publisher CLI** (`mcp-publisher`, from github.com/modelcontextprotocol/registry):

   ```bash
   brew install mcp-publisher
   ```

   If Homebrew doesn't have it, download a release binary from the [registry releases page](https://github.com/modelcontextprotocol/registry/releases) and put it on your `PATH`.

2. **Authenticate the namespace.** The `io.github.*` namespace is verified via GitHub OIDC. Run the interactive login as the GitHub account that owns the namespace (`Muzeeb1998`):

   ```bash
   mcp-publisher login github
   ```

3. **Confirm the README marker.** The `README.md` must contain the `mcp-name:` marker (already present as its first line) so the registry can verify package ownership:

   ```
   <!-- mcp-name: io.github.Muzeeb1998/explain-repo-mcp -->
   ```

4. **Validate and publish.** Make sure `server.json` matches the registry schema, then publish from the repo root:

   ```bash
   mcp-publisher publish
   ```

**Reference docs:**
- https://modelcontextprotocol.io/registry/quickstart
- https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/quickstart.mdx

---

## 4. Post-publish checklist

- [ ] PyPI package live (`uvx explain-repo-mcp` works)
- [ ] README `mcp-name:` marker present
- [ ] `server.json` namespace + package ref correct
- [ ] GitHub OIDC namespace verified
- [ ] `mcp-publisher publish` succeeded → live on official registry
- [ ] Config examples in README for Claude Desktop/Code + Cursor
- [ ] Listed on glama.ai, mcpservers.org; PR to awesome-mcp-servers
- [ ] Launch post (Show HN / r/mcp)

---

## 5. Versioning

For each release, bump the `version` in **all** of these and keep them in sync:

- `version` in `pyproject.toml`
- `version` in `server.json`
- the `version` inside the `packages` entry of `server.json`

Then tag the release in git:

```bash
git tag v0.1.0
git push origin v0.1.0
```
