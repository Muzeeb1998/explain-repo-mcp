"""Index layer: tree-sitter tag extraction + mtime-keyed SQLite cache.

A *tag* is a single definition or reference of a symbol at a file:line. Tags are
extracted with tree-sitter using each language's ``tags.scm`` query (Aider's
capture convention: ``@name.definition.*`` / ``@name.reference.*``).

Parsed tags are cached in SQLite keyed by ``(path, mtime, size)`` so re-indexing
an unchanged repo is near-instant and only changed files are re-parsed.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections import namedtuple
from importlib.resources import files
from pathlib import Path
from typing import Iterable

import tree_sitter as ts
from grep_ast import filename_to_lang, tsl

from .walker import walk_files

# rel_fname: repo-relative posix path. fname: absolute path.
# line: 0-based row. name: identifier text. kind: "def" | "ref".
Tag = namedtuple("Tag", "rel_fname fname line name kind")

# tsl language name -> tags query file stem (in queries/).
LANG_TO_QUERY = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "tsx": "typescript",
    "go": "go",
    "rust": "rust",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "ruby": "ruby",
    "php": "php",
    "csharp": "csharp",
}

_DEF_PREFIX = "name.definition."
_REF_PREFIX = "name.reference."

# (language, parser, query) objects are expensive to build — cache per language.
_lang_cache: dict[str, tuple | None] = {}
_query_text_cache: dict[str, str] = {}


def supported_languages() -> list[str]:
    return sorted(set(LANG_TO_QUERY))


def _query_text(stem: str) -> str:
    if stem not in _query_text_cache:
        path = files("explain_repo_mcp").joinpath("queries", f"{stem}-tags.scm")
        _query_text_cache[stem] = path.read_text(encoding="utf-8")
    return _query_text_cache[stem]


def _lang_objs(lang: str):
    """Return (parser, query) for a language, or None if unsupported."""
    if lang in _lang_cache:
        return _lang_cache[lang]
    stem = LANG_TO_QUERY.get(lang)
    if stem is None:
        _lang_cache[lang] = None
        return None
    try:
        language = tsl.get_language(lang)
        parser = ts.Parser(language)
        query = ts.Query(language, _query_text(stem))
    except Exception:
        _lang_cache[lang] = None
        return None
    _lang_cache[lang] = (parser, query)
    return _lang_cache[lang]


def extract_tags(fname: str, rel_fname: str) -> list[Tag]:
    """Parse one file and return its definition/reference tags."""
    lang = filename_to_lang(fname)
    if not lang:
        return []
    objs = _lang_objs(lang)
    if objs is None:
        return []
    parser, query = objs
    try:
        src = Path(fname).read_bytes()
    except OSError:
        return []
    try:
        tree = parser.parse(src)
        cursor = ts.QueryCursor(query)
        captures = cursor.captures(tree.root_node)
    except Exception:
        return []

    tags: list[Tag] = []
    for cap_name, nodes in captures.items():
        if cap_name.startswith(_DEF_PREFIX):
            kind = "def"
        elif cap_name.startswith(_REF_PREFIX):
            kind = "ref"
        else:
            continue
        for node in nodes:
            try:
                text = node.text.decode("utf-8", "replace")
            except Exception:
                continue
            tags.append(Tag(rel_fname, fname, node.start_point[0], text, kind))
    return tags


class Indexer:
    """Builds and caches the tag set for a repository."""

    def __init__(self, repo_path: os.PathLike | str, cache_dir: Path | None = None):
        self.root = Path(repo_path).resolve()
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "explain-repo-mcp"
        cache_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(str(self.root).encode()).hexdigest()[:16]
        self.db_path = cache_dir / f"{digest}.sqlite"
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS file_tags ("
            "  rel TEXT PRIMARY KEY,"
            "  mtime REAL NOT NULL,"
            "  size INTEGER NOT NULL,"
            "  tags TEXT NOT NULL)"
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _cached(self, rel: str, mtime: float, size: int) -> list[Tag] | None:
        row = self._conn.execute(
            "SELECT mtime, size, tags FROM file_tags WHERE rel = ?", (rel,)
        ).fetchone()
        if row and row[0] == mtime and row[1] == size:
            fname = str(self.root / rel)
            return [Tag(rel, fname, ln, nm, kd) for ln, nm, kd in json.loads(row[2])]
        return None

    def _store(self, rel: str, mtime: float, size: int, tags: list[Tag]) -> None:
        payload = json.dumps([[t.line, t.name, t.kind] for t in tags])
        self._conn.execute(
            "INSERT INTO file_tags(rel, mtime, size, tags) VALUES(?,?,?,?) "
            "ON CONFLICT(rel) DO UPDATE SET mtime=?, size=?, tags=?",
            (rel, mtime, size, payload, mtime, size, payload),
        )

    def tags_for_file(self, rel: str) -> list[Tag]:
        fname = str(self.root / rel)
        try:
            st = os.stat(fname)
        except OSError:
            return []
        cached = self._cached(rel, st.st_mtime, st.st_size)
        if cached is not None:
            return cached
        tags = extract_tags(fname, rel)
        self._store(rel, st.st_mtime, st.st_size, tags)
        return tags

    def index(
        self, paths: list[str] | None = None
    ) -> tuple[list[Tag], dict]:
        """Walk the repo (or ``paths`` subset) and return all tags + stats.

        Re-uses the SQLite cache; only changed/new files are re-parsed.
        """
        all_tags: list[Tag] = []
        files_scanned = 0
        files_with_tags = 0
        langs: dict[str, int] = {}
        for rel in walk_files(self.root, paths):
            files_scanned += 1
            tags = self.tags_for_file(rel)
            if tags:
                files_with_tags += 1
                lang = filename_to_lang(str(self.root / rel)) or "?"
                langs[lang] = langs.get(lang, 0) + 1
                all_tags.extend(tags)
        self._conn.commit()
        stats = {
            "files_scanned": files_scanned,
            "files_with_tags": files_with_tags,
            "total_tags": len(all_tags),
            "languages": langs,
        }
        return all_tags, stats
