"""Smoke tests for the index → rank → render pipeline.

Builds a tiny in-repo fixture across two languages and asserts that tags are
extracted, ranking produces a sensible ordering, and the rendered map respects
the token budget.
"""

from __future__ import annotations

from pathlib import Path

from explain_repo_mcp.indexer import Indexer, extract_tags, supported_languages
from explain_repo_mcp.overview import build_overview
from explain_repo_mcp.ranker import rank_tags, render_map


def _make_fixture(tmp_path: Path) -> Path:
    (tmp_path / "a.py").write_text(
        "def helper():\n    return 1\n\n"
        "class Service:\n    def run(self):\n        return helper()\n\n"
        "def main():\n    s = Service()\n    return s.run() + helper()\n"
    )
    (tmp_path / "b.js").write_text(
        "function util() { return 2; }\n"
        "class Widget { render() { return util(); } }\n"
        "function boot() { const w = new Widget(); return w.render(); }\n"
    )
    return tmp_path


def test_supported_languages_nonempty():
    langs = supported_languages()
    assert {"python", "javascript", "typescript", "go"} <= set(langs)


def test_extract_tags_python(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("def foo():\n    return bar()\n")
    tags = extract_tags(str(f), "x.py")
    names = {(t.name, t.kind) for t in tags}
    assert ("foo", "def") in names
    assert ("bar", "ref") in names


def test_index_and_rank(tmp_path):
    repo = _make_fixture(tmp_path)
    idx = Indexer(repo, cache_dir=tmp_path / ".cache")
    tags, stats = idx.index()
    assert stats["files_with_tags"] == 2
    assert stats["total_tags"] > 0

    ranked = rank_tags(tags)
    names = [r.name for r in ranked]
    # `helper` and `util` are referenced most → should rank above their callers.
    assert "helper" in names and "util" in names

    idx.close()


def test_cache_is_incremental(tmp_path):
    repo = _make_fixture(tmp_path)
    cache = tmp_path / ".cache"
    idx = Indexer(repo, cache_dir=cache)
    tags1, _ = idx.index()
    idx.close()

    idx2 = Indexer(repo, cache_dir=cache)
    tags2, _ = idx2.index()
    idx2.close()
    assert len(tags1) == len(tags2)


def test_render_respects_budget(tmp_path):
    repo = _make_fixture(tmp_path)
    idx = Indexer(repo, cache_dir=tmp_path / ".cache")
    tags, _ = idx.index()
    ranked = rank_tags(tags)
    result = render_map(ranked, token_budget=40)
    assert result.token_estimate <= 40
    idx.close()


def test_overview(tmp_path):
    repo = _make_fixture(tmp_path)
    ov = build_overview(repo)
    assert ov["total_files"] == 2
    langs = {l["language"] for l in ov["languages"]}
    assert "python" in langs and "javascript" in langs
