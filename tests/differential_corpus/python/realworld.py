"""Realistic utility module: caching, formatting, and a small pipeline.

Audit dimension: symbol extraction on realistic multi-construct code.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class Entry:
    key: str
    value: Any = None
    tags: list[str] = field(default_factory=list)


class Cache:
    """Tiny LRU-ish cache."""

    def __init__(self, capacity: int = 100) -> None:
        self._capacity = capacity
        self._store: dict[str, Entry] = {}

    def get(self, key: str) -> Any:
        entry = self._store.get(key)
        if entry is None:
            return None
        return entry.value

    def set(self, key: str, value: Any, tags: list[str] | None = None) -> None:
        if len(self._store) >= self._capacity:
            self._store.pop(next(iter(self._store)))
        self._store[key] = Entry(key=key, value=value, tags=tags or [])

    def size(self) -> int:
        return len(self._store)


def slugify(text: str) -> str:
    lower = text.lower().strip()
    return _SLUG_RE.sub("-", lower).strip("-")


def timestamp() -> str:
    return datetime.utcnow().isoformat()


def dump_payload(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, indent=2)


def process(records: list[dict], cache: Cache) -> list[dict]:
    """Public pipeline entry point."""
    out = []
    for record in records:
        key = slugify(record.get("name", "unnamed"))
        cached = cache.get(key)
        if cached is not None:
            out.append({"key": key, "cached": True, "payload": cached})
        else:
            payload = {"name": record.get("name"), "ts": timestamp()}
            cache.set(key, payload, tags=record.get("tags", []))
            out.append({"key": key, "cached": False, "payload": payload})
    return out