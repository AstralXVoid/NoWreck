"""File-level scan result cache for NoWreck.

Caches per-file parsed output keyed on ``(path, mtime, size)``.  Stored
in ``.nowreck/cache/`` under the repository root.  Transparent to every
other component — ``ScanResult`` produced from cache must be identical
to one produced from a fresh scan.

Cache version is bumped when the schema changes (field added/removed,
encoding changes, language enum changes).  A version mismatch triggers
a full re-parse and overwrites the old cache.

See ``docs/nowreck-v12-scope.md`` for the full design rationale.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)


def file_content_hash(path: Path) -> str:
    """Return MD5 hex digest of a file's contents.

    Used to detect same-size rewrites within the same filesystem
    timestamp quantum.
    """
    h = hashlib.md5()
    try:
        h.update(path.read_bytes())
    except OSError:
        return ""
    return h.hexdigest()


CACHE_DIR = ".nowreck/cache"
CACHE_FILE = "scan_cache.json"
CACHE_VERSION = 1


@dataclass
class CacheEntry:
    """A single cached file result.

    For Python files, *source* is the file text (needed to reconstruct
    ``ast.Module`` on load).  For JS/TS/Rust/Go files, *symbols* holds
    the serialised symbol list.

    Attributes:
        mtime: File modification time at parse time.
        size: File size in bytes at parse time.
        language: One of ``"python"``, ``"javascript"``, ``"typescript"``,
            ``"rust"``, ``"go"``.
        source: Source text for Python files.  ``None`` for other languages.
        symbols: Serialised symbol list for JS/TS/Rust/Go.  ``None`` for
            Python.
    """

    mtime: float
    size: int
    language: str
    content_hash: str = ""
    source: str | None = None
    symbols: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        d: dict[str, Any] = {
            "mtime": self.mtime,
            "size": self.size,
            "language": self.language,
            "content_hash": self.content_hash,
        }
        if self.source is not None:
            d["source"] = self.source
        if self.symbols:
            d["symbols"] = self.symbols
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CacheEntry:
        """Deserialise from a JSON dict."""
        return cls(
            mtime=d["mtime"],
            size=d["size"],
            language=d["language"],
            content_hash=d.get("content_hash", ""),
            source=d.get("source"),
            symbols=d.get("symbols", []),
        )


class ScanCache:
    """File-level scan result cache.

    Caches per-file parsed output keyed on ``(path, mtime, size)``.
    Stored in ``.nowreck/cache/`` under the repository root.

    Usage::

        cache = ScanCache(repo_root)
        entry = cache.get(file_path, mtime, size)
        if entry is not None:
            # use cached result
        else:
            # parse, then cache
            cache.put(file_path, mtime, size, CacheEntry(...))
        cache.save()
    """

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._cache_dir = repo_root / CACHE_DIR
        self._cache_file = self._cache_dir / CACHE_FILE
        self._entries: dict[str, CacheEntry] = {}
        self._load()

    def _load(self) -> None:
        """Load cache from disk.  Silently returns on any error."""
        if not self._cache_file.is_file():
            return

        try:
            raw = self._cache_file.read_text(encoding="utf-8")
            data: dict[str, object] = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read scan cache: %s", exc)
            return

        if data.get("version") != CACHE_VERSION:
            logger.info(
                "Scan cache version mismatch (%s vs %s), ignoring cache",
                data.get("version"),
                CACHE_VERSION,
            )
            return

        raw_entries: object = data.get("entries")
        if not isinstance(raw_entries, dict):
            return

        entries: dict[str, object] = cast("dict[str, object]", raw_entries)
        for key, val in entries.items():
            if isinstance(val, dict):
                entry_dict: dict[str, object] = cast("dict[str, object]", val)
                self._entries[str(key)] = CacheEntry.from_dict(entry_dict)

    def get(
        self,
        file_path: Path,
        mtime: float,
        size: int,
        content_hash: str = "",
    ) -> CacheEntry | None:
        """Return cached result if valid, ``None`` if missing or stale.

        Args:
            file_path: Path relative to the repository root.
            mtime: Current file modification time.
            size: Current file size in bytes.
            content_hash: MD5 hex digest of file content.  Compared
                against the stored hash to catch same-size rewrites
                within the same filesystem timestamp quantum.

        Returns:
            A :class:`CacheEntry` if the cache is valid for this file,
            ``None`` otherwise.
        """
        key = str(file_path)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.mtime != mtime or entry.size != size:
            return None
        # Content hash guards against same-size rewrites within the same
        # filesystem timestamp quantum (e.g. replacing "Old" with "New"
        # in a same-length string within the same second).
        if content_hash and entry.content_hash and content_hash != entry.content_hash:
            return None
        return entry

    def put(
        self,
        file_path: Path,
        mtime: float,
        size: int,
        entry: CacheEntry,
    ) -> None:
        """Store a parsed result in the cache.

        Args:
            file_path: Path relative to the repository root.
            mtime: File modification time at parse time.
            size: File size in bytes at parse time.
            entry: The :class:`CacheEntry` to store.
        """
        key = str(file_path)
        self._entries[key] = entry

    def remove(self, file_path: Path) -> None:
        """Remove a single entry from the cache.

        Args:
            file_path: Path relative to the repository root.
        """
        key = str(file_path)
        self._entries.pop(key, None)

    def save(self) -> None:
        """Persist cache to disk atomically.

        Writes to a temporary file, then renames to the final path.
        A crash mid-write leaves either the old cache or the new cache
        intact — never a half-written file.

        Raises:
            OSError: If the write fails.
        """
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": CACHE_VERSION,
            "entries": {key: entry.to_dict() for key, entry in self._entries.items()},
        }

        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._cache_dir),
                prefix=".scan_cache_",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, str(self._cache_file))
                logger.debug("Scan cache saved (%d entries)", len(self._entries))
            except BaseException:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as exc:
            logger.warning("Failed to save scan cache: %s", exc)

    def clear(self) -> None:
        """Clear all entries from the in-memory cache."""
        self._entries.clear()

    @property
    def entry_count(self) -> int:
        """Number of entries currently in the cache."""
        return len(self._entries)
