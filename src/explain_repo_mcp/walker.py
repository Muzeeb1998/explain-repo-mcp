"""gitignore-aware repository file walking.

Prunes VCS dirs, dependency/build dirs, binaries and oversized files so the
index only ever touches real source. Respects the repo-root ``.gitignore``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pathspec

# Directories never worth descending into.
DEFAULT_IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".bzr",
    "node_modules", "bower_components", "jspm_packages",
    "__pycache__", ".venv", "venv", "env", ".env", ".tox", ".nox",
    "dist", "build", "out", ".next", ".nuxt", ".svelte-kit", "target",
    "vendor", "Pods", "Carthage", ".gradle", ".cargo",
    ".idea", ".vscode", ".vs",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", ".cache",
    "coverage", ".coverage", "htmlcov", ".terraform",
    "site-packages", "__snapshots__", ".explain_repo_cache",
    ".git-rewrite", ".history",
}

# Extensions we treat as binary / non-source and skip outright.
BINARY_EXT = {
    # images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".ico", ".webp",
    ".svg", ".psd", ".ai", ".heic",
    # fonts
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    # media
    ".mp3", ".mp4", ".wav", ".flac", ".avi", ".mov", ".mkv", ".webm", ".ogg",
    # archives
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".jar", ".war",
    # compiled / binary
    ".pyc", ".pyo", ".o", ".obj", ".so", ".dylib", ".dll", ".a", ".lib",
    ".exe", ".bin", ".class", ".wasm", ".node",
    # data / docs that aren't source
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".db", ".sqlite", ".sqlite3", ".parquet", ".pack", ".idx",
    # lockfiles (huge, low signal)
    ".lock",
}

MAX_FILE_BYTES = 1_000_000  # skip files larger than ~1MB (generated/minified)


def load_ignore_spec(root: Path) -> pathspec.PathSpec | None:
    """Build a PathSpec from the repo-root ``.gitignore`` if present."""
    gi = root / ".gitignore"
    if not gi.is_file():
        return None
    try:
        lines = gi.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def _is_minified(name: str) -> bool:
    return name.endswith((".min.js", ".min.css", ".bundle.js", ".map"))


def walk_files(
    root: os.PathLike | str,
    paths: list[str] | None = None,
    max_files: int = 50_000,
) -> Iterator[str]:
    """Yield repo-relative paths of indexable source files.

    ``paths`` optionally scopes the walk to one or more sub-directories or
    files (relative to ``root``). ``max_files`` is a safety cap for monorepos.
    """
    root = Path(root).resolve()
    spec = load_ignore_spec(root)

    scopes: list[Path]
    if paths:
        scopes = [(root / p).resolve() for p in paths]
    else:
        scopes = [root]

    count = 0
    seen: set[str] = set()
    for scope in scopes:
        if not scope.exists():
            continue
        if scope.is_file():
            rel = _accept(scope, root, spec)
            if rel and rel not in seen:
                seen.add(rel)
                count += 1
                yield rel
            continue
        for dirpath, dirnames, filenames in os.walk(scope):
            # prune ignored dirs in-place
            dirnames[:] = [
                d for d in dirnames
                if d not in DEFAULT_IGNORE_DIRS and not d.startswith(".")
                or d in (".github",)  # keep a couple useful dotdirs
            ]
            for fn in filenames:
                fp = Path(dirpath) / fn
                rel = _accept(fp, root, spec)
                if not rel or rel in seen:
                    continue
                seen.add(rel)
                count += 1
                if count > max_files:
                    return
                yield rel


def _accept(fp: Path, root: Path, spec: pathspec.PathSpec | None) -> str | None:
    """Return the repo-relative path if the file should be indexed, else None."""
    name = fp.name
    if name.startswith("."):
        return None
    ext = fp.suffix.lower()
    if ext in BINARY_EXT or _is_minified(name):
        return None
    try:
        st = fp.stat()
    except OSError:
        return None
    if not fp.is_file() or st.st_size == 0 or st.st_size > MAX_FILE_BYTES:
        return None
    try:
        rel = fp.resolve().relative_to(root).as_posix()
    except ValueError:
        return None
    if spec is not None and spec.match_file(rel):
        return None
    return rel
