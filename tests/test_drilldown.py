"""Drill-down tools: file_outline, explain_symbol, find_usages, search_code."""

from __future__ import annotations

import pytest

from explain_repo_mcp.drilldown import (
    explain_symbol,
    file_outline,
    find_usages,
    search_code,
)
from explain_repo_mcp.indexer import Indexer


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "core.py").write_text(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "class Service:\n"
        "    def run(self):\n"
        "        return helper()\n"
    )
    (tmp_path / "app.py").write_text(
        "from core import Service, helper\n"
        "\n"
        "def main():\n"
        "    s = Service()\n"
        "    return s.run() + helper()\n"
    )
    idx = Indexer(tmp_path, cache_dir=tmp_path / ".cache")
    yield idx
    idx.close()


def test_file_outline(repo):
    out = file_outline(repo, "core.py")
    names = {s["name"]: s["kind"] for s in out["symbols"]}
    assert names["Service"] == "class"
    assert names["helper"] == "function"
    assert out["symbol_count"] == 3
    assert any("def helper" in s["signature"] for s in out["symbols"])


def test_file_outline_missing(repo):
    out = file_outline(repo, "nope.py")
    assert out["error"]
    assert out["symbols"] == []


def test_explain_symbol(repo):
    out = explain_symbol(repo, "helper")
    assert out["found"] is True
    assert out["definitions"][0]["file"] == "core.py"
    assert out["definitions"][0]["kind"] == "function"
    assert out["reference_count"] >= 2  # core.run + app.main
    assert "def helper" in out["definitions"][0]["context"]


def test_explain_symbol_unknown(repo):
    out = explain_symbol(repo, "helpr")
    assert out["found"] is False
    assert "helper" in out["did_you_mean"]


def test_find_usages_pagination(repo):
    out = find_usages(repo, "helper", page=1, page_size=1)
    assert out["total_usages"] >= 2
    assert len(out["usages"]) == 1
    assert out["has_more"] is True
    assert out["defined_at"][0]["file"] == "core.py"


def test_search_code(repo):
    out = search_code(repo, "Service")
    assert out["total_matches"] >= 2
    assert all("Service" in m["snippet"] for m in out["matches"])


def test_search_code_regex(repo):
    out = search_code(repo, r"def \w+\(", regex=True)
    assert out["total_matches"] >= 3


def test_search_code_bad_regex(repo):
    out = search_code(repo, r"(", regex=True)
    assert out["error"]
