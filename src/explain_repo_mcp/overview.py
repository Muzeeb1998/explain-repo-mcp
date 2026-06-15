"""High-level repo orientation — the cheap, always-fits-budget first call.

Languages, top-level layout, detected entry points, build/config files, and a
rough size. No parsing; just a filesystem pass over indexable files.
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from grep_ast import filename_to_lang

from .walker import walk_files

# Root-level files that signal the build system / package manager.
CONFIG_FILES = {
    "package.json", "pnpm-lock.yaml", "yarn.lock", "tsconfig.json",
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile",
    "go.mod", "go.sum", "Cargo.toml", "pom.xml", "build.gradle",
    "build.gradle.kts", "Makefile", "CMakeLists.txt", "Dockerfile",
    "docker-compose.yml", "docker-compose.yaml", "composer.json", "Gemfile",
    ".csproj", "*.csproj", "build.sbt", "mix.exs", "deno.json",
}

# Filenames that commonly serve as program entry points.
ENTRY_HINTS = {
    "main.py", "__main__.py", "manage.py", "app.py", "wsgi.py", "asgi.py",
    "index.js", "index.ts", "main.js", "main.ts", "server.js", "server.ts",
    "main.go", "main.rs", "Main.java", "Program.cs", "index.php",
}


def build_overview(repo_path: os.PathLike | str) -> dict:
    root = Path(repo_path).resolve()
    lang_counts: Counter = Counter()
    ext_counts: Counter = Counter()
    top_dirs: Counter = Counter()
    entry_points: list[str] = []
    total_files = 0
    total_bytes = 0

    for rel in walk_files(root):
        total_files += 1
        fp = root / rel
        try:
            total_bytes += fp.stat().st_size
        except OSError:
            pass
        lang = filename_to_lang(str(fp))
        if lang:
            lang_counts[lang] += 1
        ext = fp.suffix.lower().lstrip(".")
        if ext:
            ext_counts[ext] += 1

        parts = rel.split("/")
        top_dirs[parts[0] if len(parts) > 1 else "(root)"] += 1

        base = parts[-1]
        if base in ENTRY_HINTS or (
            len(parts) >= 2 and parts[0] == "cmd" and base == "main.go"
        ):
            entry_points.append(rel)

    config_files = sorted(
        rel for rel in _root_files(root)
        if rel in CONFIG_FILES or rel.endswith(".csproj")
    )

    return {
        "repo": str(root),
        "name": root.name,
        "total_files": total_files,
        "total_bytes": total_bytes,
        "size_label": _size_label(total_files),
        "languages": [
            {"language": k, "files": v}
            for k, v in lang_counts.most_common(12)
        ],
        "top_extensions": [
            {"ext": k, "files": v} for k, v in ext_counts.most_common(10)
        ],
        "directories": [
            {"dir": k, "files": v} for k, v in top_dirs.most_common(20)
        ],
        "config_files": config_files,
        "entry_points": sorted(set(entry_points))[:20],
    }


def _root_files(root: Path) -> list[str]:
    try:
        return [p.name for p in root.iterdir() if p.is_file()]
    except OSError:
        return []


def _size_label(n: int) -> str:
    if n < 50:
        return "tiny"
    if n < 300:
        return "small"
    if n < 1500:
        return "medium"
    if n < 6000:
        return "large"
    return "very large"


def render_overview(ov: dict) -> str:
    """Compact human-readable rendering for the text content block."""
    lines = [f"# {ov['name']} ({ov['size_label']}, {ov['total_files']} files)"]
    if ov["languages"]:
        langs = ", ".join(f"{l['language']}({l['files']})" for l in ov["languages"][:8])
        lines.append(f"Languages: {langs}")
    if ov["config_files"]:
        lines.append(f"Build/config: {', '.join(ov['config_files'][:12])}")
    if ov["entry_points"]:
        lines.append(f"Entry points: {', '.join(ov['entry_points'][:10])}")
    if ov["directories"]:
        dirs = ", ".join(f"{d['dir']}/({d['files']})" for d in ov["directories"][:12])
        lines.append(f"Layout: {dirs}")
    return "\n".join(lines)
