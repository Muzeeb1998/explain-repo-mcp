"""Token counting for budget enforcement.

Uses tiktoken's ``cl100k_base`` as a stable, model-agnostic proxy. Falls back to
a ~4-chars-per-token heuristic if the encoder can't be loaded (e.g. offline).
"""

from __future__ import annotations

_encoder = None
_tried = False


def _get_encoder():
    global _encoder, _tried
    if not _tried:
        _tried = True
        try:
            import tiktoken
            _encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _encoder = None
    return _encoder


def count_tokens(text: str) -> int:
    if not text:
        return 0
    enc = _get_encoder()
    if enc is None:
        return max(1, len(text) // 4)
    return len(enc.encode(text, disallowed_special=()))
