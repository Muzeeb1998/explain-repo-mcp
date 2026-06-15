"""Tag extraction across languages (TypeScript, Go, Rust, Java in addition to
the Python/JS covered by the smoke tests)."""

from __future__ import annotations

from explain_repo_mcp.indexer import extract_tags


def _names(tags, kind):
    return {t.name for t in tags if t.kind == kind}


def test_typescript(tmp_path):
    f = tmp_path / "svc.ts"
    f.write_text(
        "interface Repo { id: number }\n"
        "class Service {\n"
        "  load(): Repo { return fetchRepo(); }\n"
        "}\n"
        "function fetchRepo(): Repo { return { id: 1 }; }\n"
    )
    tags = extract_tags(str(f), "svc.ts")
    assert "Service" in _names(tags, "def")
    assert "Repo" in _names(tags, "def")
    assert "fetchRepo" in _names(tags, "def")
    assert "fetchRepo" in _names(tags, "ref")


def test_go(tmp_path):
    f = tmp_path / "main.go"
    f.write_text(
        "package main\n"
        "type Server struct { port int }\n"
        "func (s *Server) Start() { listen() }\n"
        "func listen() {}\n"
        "func main() { s := Server{}; s.Start() }\n"
    )
    tags = extract_tags(str(f), "main.go")
    assert {"Server", "Start", "listen", "main"} <= _names(tags, "def")
    assert "listen" in _names(tags, "ref")


def test_rust(tmp_path):
    f = tmp_path / "lib.rs"
    f.write_text(
        "struct Config { n: u32 }\n"
        "fn build() -> Config { Config { n: 1 } }\n"
        "fn run() { let c = build(); }\n"
    )
    tags = extract_tags(str(f), "lib.rs")
    assert {"Config", "build", "run"} <= _names(tags, "def")
    assert "build" in _names(tags, "ref")


def test_java(tmp_path):
    f = tmp_path / "App.java"
    f.write_text(
        "class App {\n"
        "  void start() { helper(); }\n"
        "  void helper() {}\n"
        "}\n"
    )
    tags = extract_tags(str(f), "App.java")
    assert {"App", "start", "helper"} <= _names(tags, "def")
    assert "helper" in _names(tags, "ref")


def test_detail_kinds(tmp_path):
    f = tmp_path / "k.py"
    f.write_text("class C:\n    def m(self):\n        return 1\ndef f():\n    return C()\n")
    tags = extract_tags(str(f), "k.py")
    by_name = {t.name: t.detail for t in tags if t.kind == "def"}
    assert by_name.get("C") == "class"
    assert by_name.get("f") == "function"
