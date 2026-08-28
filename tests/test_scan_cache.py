"""Tests for the scan cache (ScanCache, CacheEntry) and its integration
with RepositoryScanner.scan().

Every test verifies that caching is transparent — the returned ScanResult
is identical whether the cache is warm or cold.
"""

from __future__ import annotations

import ast
import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from nowreck.scanner.repository_scanner import RepositoryScanner
from nowreck.scanner.scan_cache import (
    CACHE_DIR,
    CACHE_FILE,
    CACHE_VERSION,
    CacheEntry,
    ScanCache,
)
from nowreck.scanner.symbol_index import Symbol, SymbolType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def python_repo(tmp_path: Path) -> Path:
    """A repo with a valid Python file."""
    (tmp_path / "math_utils.py").write_text(
        textwrap.dedent("""\
            def add(a, b):
                return a + b

            class Calculator:
                def compute(self, x):
                    return x * 2
        """),
    )
    return tmp_path


@pytest.fixture
def js_repo(tmp_path: Path) -> Path:
    """A repo with a valid JavaScript file."""
    (tmp_path / "utils.js").write_text(
        "function greet(name) { return 'Hello ' + name; }\n"
        "const add = (a, b) => a + b;\n",
    )
    return tmp_path


@pytest.fixture
def multi_file_repo(tmp_path: Path) -> Path:
    """A repo with multiple Python files."""
    (tmp_path / "a.py").write_text("def func_a(): ...\n")
    (tmp_path / "b.py").write_text("class MyClass:\n    pass\n")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("x = 1\n")
    return tmp_path


@pytest.fixture
def repo_with_syntax_error(tmp_path: Path) -> Path:
    """A repo with one valid and one broken file."""
    (tmp_path / "good.py").write_text("y = 42\n")
    (tmp_path / "bad.py").write_text("def broken(\n")
    return tmp_path


# ---------------------------------------------------------------------------
# ScanCache unit tests
# ---------------------------------------------------------------------------


class TestScanCacheUnit:
    """Unit tests for ScanCache and CacheEntry."""

    def test_cache_entry_round_trip(self) -> None:
        """CacheEntry serialises and deserialises correctly."""
        entry = CacheEntry(
            mtime=1693000000.0,
            size=1234,
            language="python",
            source="def foo(): ...\n",
        )
        d = entry.to_dict()
        restored = CacheEntry.from_dict(d)
        assert restored.mtime == entry.mtime
        assert restored.size == entry.size
        assert restored.language == entry.language
        assert restored.source == entry.source

    def test_cache_entry_js_round_trip(self) -> None:
        """CacheEntry with symbols serialises correctly."""
        entry = CacheEntry(
            mtime=1693000001.0,
            size=567,
            language="javascript",
            symbols=[
                {"name": "greet", "type": "function", "file": "utils.js", "line": 1},
            ],
        )
        d = entry.to_dict()
        restored = CacheEntry.from_dict(d)
        assert restored.symbols == entry.symbols
        assert restored.source is None

    def test_empty_cache_load(self, tmp_path: Path) -> None:
        """Loading from a nonexistent cache file succeeds silently."""
        cache = ScanCache(tmp_path)
        assert cache.entry_count == 0

    def test_cache_get_miss_on_empty(self, tmp_path: Path) -> None:
        """get() returns None when cache is empty."""
        cache = ScanCache(tmp_path)
        assert cache.get(Path("a.py"), 1.0, 100) is None

    def test_cache_put_and_get(self, tmp_path: Path) -> None:
        """put() then get() returns the same entry."""
        cache = ScanCache(tmp_path)
        entry = CacheEntry(mtime=1.0, size=100, language="python", source="x = 1\n")
        cache.put(Path("a.py"), 1.0, 100, entry)
        result = cache.get(Path("a.py"), 1.0, 100)
        assert result is not None
        assert result.source == "x = 1\n"

    def test_cache_get_stale_by_mtime(self, tmp_path: Path) -> None:
        """get() returns None when mtime differs."""
        cache = ScanCache(tmp_path)
        entry = CacheEntry(mtime=1.0, size=100, language="python", source="x = 1\n")
        cache.put(Path("a.py"), 1.0, 100, entry)
        assert cache.get(Path("a.py"), 2.0, 100) is None  # mtime changed

    def test_cache_get_stale_by_size(self, tmp_path: Path) -> None:
        """get() returns None when size differs."""
        cache = ScanCache(tmp_path)
        entry = CacheEntry(mtime=1.0, size=100, language="python", source="x = 1\n")
        cache.put(Path("a.py"), 1.0, 100, entry)
        assert cache.get(Path("a.py"), 1.0, 200) is None  # size changed

    def test_cache_remove(self, tmp_path: Path) -> None:
        """remove() deletes an entry."""
        cache = ScanCache(tmp_path)
        entry = CacheEntry(mtime=1.0, size=100, language="python", source="x = 1\n")
        cache.put(Path("a.py"), 1.0, 100, entry)
        cache.remove(Path("a.py"))
        assert cache.get(Path("a.py"), 1.0, 100) is None

    def test_cache_remove_nonexistent(self, tmp_path: Path) -> None:
        """remove() on missing key does not raise."""
        cache = ScanCache(tmp_path)
        cache.remove(Path("nope.py"))  # should not raise

    def test_cache_clear(self, tmp_path: Path) -> None:
        """clear() empties the cache."""
        cache = ScanCache(tmp_path)
        entry = CacheEntry(mtime=1.0, size=100, language="python", source="x = 1\n")
        cache.put(Path("a.py"), 1.0, 100, entry)
        cache.clear()
        assert cache.entry_count == 0

    def test_cache_save_and_load(self, tmp_path: Path) -> None:
        """Cache survives save/load cycle."""
        cache = ScanCache(tmp_path)
        entry = CacheEntry(mtime=1.0, size=100, language="python", source="x = 1\n")
        cache.put(Path("a.py"), 1.0, 100, entry)
        cache.save()

        # Load fresh instance
        cache2 = ScanCache(tmp_path)
        assert cache2.entry_count == 1
        result = cache2.get(Path("a.py"), 1.0, 100)
        assert result is not None
        assert result.source == "x = 1\n"

    def test_cache_persists_across_instances(self, tmp_path: Path) -> None:
        """Simulates process restart: save, create new ScanCache, verify."""
        # First "process"
        cache1 = ScanCache(tmp_path)
        entry = CacheEntry(mtime=10.0, size=50, language="python", source="z = 9\n")
        cache1.put(Path("mod.py"), 10.0, 50, entry)
        cache1.save()

        # Second "process" — completely fresh ScanCache
        cache2 = ScanCache(tmp_path)
        hit = cache2.get(Path("mod.py"), 10.0, 50)
        assert hit is not None
        assert hit.source == "z = 9\n"

    def test_cache_invalidated_by_version_bump(self, tmp_path: Path) -> None:
        """Version mismatch causes cache to be ignored on load."""
        cache = ScanCache(tmp_path)
        entry = CacheEntry(mtime=1.0, size=100, language="python", source="x = 1\n")
        cache.put(Path("a.py"), 1.0, 100, entry)
        cache.save()

        # Tamper: overwrite version in the JSON file
        cache_file = tmp_path / CACHE_DIR / CACHE_FILE
        data = json.loads(cache_file.read_text())
        data["version"] = 9999
        cache_file.write_text(json.dumps(data))

        # Fresh load — should ignore stale version
        cache2 = ScanCache(tmp_path)
        assert cache2.entry_count == 0

    def test_cache_atomic_write(self, tmp_path: Path) -> None:
        """save() uses atomic rename — no .tmp files left behind."""
        cache = ScanCache(tmp_path)
        entry = CacheEntry(mtime=1.0, size=100, language="python", source="x = 1\n")
        cache.put(Path("a.py"), 1.0, 100, entry)
        cache.save()

        cache_dir = tmp_path / CACHE_DIR
        tmp_files = list(cache_dir.glob(".scan_cache_*.tmp"))
        assert tmp_files == []  # no temp files left

    def test_cache_creates_directory(self, tmp_path: Path) -> None:
        """save() creates .nowreck/cache/ if it doesn't exist."""
        cache_dir = tmp_path / CACHE_DIR
        assert not cache_dir.exists()
        cache = ScanCache(tmp_path)
        entry = CacheEntry(mtime=1.0, size=100, language="python", source="x = 1\n")
        cache.put(Path("a.py"), 1.0, 100, entry)
        cache.save()
        assert cache_dir.is_dir()


# ---------------------------------------------------------------------------
# Symbol serialisation tests
# ---------------------------------------------------------------------------


class TestSymbolSerialisation:
    """Symbol to_dict/from_dict round-trip."""

    def test_basic_symbol_round_trip(self) -> None:
        sym = Symbol(
            name="greet",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("app.js"),
            line_number=1,
        )
        d = sym.to_dict()
        restored = Symbol.from_dict(d)
        assert restored.name == sym.name
        assert restored.symbol_type == sym.symbol_type
        assert restored.file_path == sym.file_path
        assert restored.line_number == sym.line_number
        assert restored.parent_class is None

    def test_method_symbol_round_trip(self) -> None:
        sym = Symbol(
            name="render",
            symbol_type=SymbolType.METHOD,
            file_path=Path("widget.ts"),
            line_number=10,
            parent_class="Widget",
        )
        d = sym.to_dict()
        restored = Symbol.from_dict(d)
        assert restored.parent_class == "Widget"
        assert restored.symbol_type == SymbolType.METHOD

    def test_to_dict_types(self) -> None:
        sym = Symbol(
            name="test",
            symbol_type=SymbolType.CLASS,
            file_path=Path("mod.py"),
            line_number=5,
        )
        d = sym.to_dict()
        assert isinstance(d["symbol_type"], str)
        assert d["symbol_type"] == "CLASS"
        assert isinstance(d["file_path"], str)
        assert d["file_path"] == "mod.py"


# ---------------------------------------------------------------------------
# Integration: cache + RepositoryScanner
# ---------------------------------------------------------------------------


class TestCacheIntegration:
    """Integration tests verifying cache transparency with RepositoryScanner."""

    def test_cache_hit_returns_same_ast(self, python_repo: Path) -> None:
        """Cached Python scan produces identical ast.Module (via ast.dump)."""
        scanner = RepositoryScanner(python_repo)
        # Cold scan — populates cache
        result_cold = scanner.scan()
        # Warm scan — uses cache
        result_warm = scanner.scan()

        for path in result_cold.modules:
            assert path in result_warm.modules
            cold_dump = ast.dump(result_cold.modules[path])
            warm_dump = ast.dump(result_warm.modules[path])
            assert cold_dump == warm_dump

    def test_cache_hit_returns_same_js_symbols(self, js_repo: Path) -> None:
        """Cached JS scan produces identical symbols."""
        scanner = RepositoryScanner(js_repo)
        result_cold = scanner.scan()
        result_warm = scanner.scan()

        for path in result_cold.js_files:
            assert path in result_warm.js_files
            cold_syms = [(s.name, s.symbol_type) for s in result_cold.js_files[path]]
            warm_syms = [(s.name, s.symbol_type) for s in result_warm.js_files[path]]
            assert cold_syms == warm_syms

    def test_cache_hit_returns_same_file_set(self, multi_file_repo: Path) -> None:
        """Cached file discovery matches fresh scan."""
        scanner = RepositoryScanner(multi_file_repo)
        result_cold = scanner.scan()
        result_warm = scanner.scan()

        assert set(result_cold.modules.keys()) == set(result_warm.modules.keys())

    def test_cache_miss_parses_and_caches(self, python_repo: Path) -> None:
        """New file is parsed and cached."""
        scanner = RepositoryScanner(python_repo)
        scanner.scan()  # initial scan

        # Add a new file
        (python_repo / "new_file.py").write_text("def new_func(): ...\n")
        result = scanner.scan()

        assert Path("new_file.py") in result.modules

        # Verify it's in the cache
        cache = ScanCache(python_repo)
        new_file = python_repo / "new_file.py"
        new_stat = new_file.stat()
        assert (
            cache.get(Path("new_file.py"), new_stat.st_mtime, new_stat.st_size)
            is not None
        )

    def test_cache_invalidated_by_mtime(self, python_repo: Path) -> None:
        """Changed file triggers re-parse."""
        scanner = RepositoryScanner(python_repo)
        result1 = scanner.scan()
        old_dump = ast.dump(result1.modules[Path("math_utils.py")])

        # Modify the file
        (python_repo / "math_utils.py").write_text("def different(): ...\n")
        result2 = scanner.scan()
        new_dump = ast.dump(result2.modules[Path("math_utils.py")])

        assert old_dump != new_dump

    def test_cache_invalidated_by_size(self, python_repo: Path) -> None:
        """Changed file size triggers re-parse."""
        scanner = RepositoryScanner(python_repo)
        result1 = scanner.scan()
        old_dump = ast.dump(result1.modules[Path("math_utils.py")])

        # Modify the file (change content, which changes size)
        (python_repo / "math_utils.py").write_text("x = 1\n")
        result2 = scanner.scan()
        new_dump = ast.dump(result2.modules[Path("math_utils.py")])

        assert old_dump != new_dump

    def test_cache_deleted_file_removed(self, python_repo: Path) -> None:
        """Deleted file is handled correctly."""
        scanner = RepositoryScanner(python_repo)
        result1 = scanner.scan()
        assert Path("math_utils.py") in result1.modules

        # Delete the file
        (python_repo / "math_utils.py").unlink()
        result2 = scanner.scan()
        assert Path("math_utils.py") not in result2.modules

    def test_cache_deterministic_output(self, python_repo: Path) -> None:
        """Same repo produces same ScanResult with or without cache."""
        # Cold scan (cache disabled)
        scanner_no_cache = RepositoryScanner(python_repo, use_cache=False)
        result_no_cache = scanner_no_cache.scan()

        # Warm scan (cache enabled)
        scanner_cached = RepositoryScanner(python_repo, use_cache=True)
        result_cached = scanner_cached.scan()

        assert set(result_no_cache.modules.keys()) == set(result_cached.modules.keys())
        for path in result_no_cache.modules:
            assert ast.dump(result_no_cache.modules[path]) == ast.dump(
                result_cached.modules[path]
            )

    def test_cache_hit_skips_parse(self, python_repo: Path) -> None:
        """On cache hit, _parse_file is not called for cached files."""
        scanner = RepositoryScanner(python_repo, use_cache=True)
        scanner.scan()  # populate cache

        parse_fn = scanner._parse_file
        with patch.object(scanner, "_parse_file", wraps=parse_fn) as mock_parse:
            scanner.scan()
            # All Python files should be cache hits → _parse_file not called
            assert mock_parse.call_count == 0

    def test_cache_persists_across_scanner_instances(self, python_repo: Path) -> None:
        """Cache survives when a new RepositoryScanner is created."""
        scanner1 = RepositoryScanner(python_repo)
        result1 = scanner1.scan()

        # New scanner instance — simulates process restart
        scanner2 = RepositoryScanner(python_repo)
        result2 = scanner2.scan()

        assert set(result1.modules.keys()) == set(result2.modules.keys())

    def test_cache_with_syntax_error_files(self, repo_with_syntax_error: Path) -> None:
        """Cache handles repos with both valid and broken files."""
        scanner = RepositoryScanner(repo_with_syntax_error)
        result1 = scanner.scan()
        result2 = scanner.scan()

        # Same results both times
        assert set(result1.modules.keys()) == set(result2.modules.keys())
        assert set(result1.failed_files.keys()) == set(result2.failed_files.keys())

    def test_no_cache_mode(self, python_repo: Path) -> None:
        """use_cache=False skips all cache logic."""
        scanner = RepositoryScanner(python_repo, use_cache=False)
        result = scanner.scan()

        assert Path("math_utils.py") in result.modules
        # No cache file created
        assert not (python_repo / CACHE_DIR / CACHE_FILE).exists()

    def test_cache_file_is_json(self, python_repo: Path) -> None:
        """Cache file is valid JSON with expected structure."""
        scanner = RepositoryScanner(python_repo)
        scanner.scan()

        cache_file = python_repo / CACHE_DIR / CACHE_FILE
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert data["version"] == CACHE_VERSION
        assert "entries" in data
        assert isinstance(data["entries"], dict)


# ---------------------------------------------------------------------------
# Regression: existing scanner tests still pass
# ---------------------------------------------------------------------------


class TestRegression:
    """Ensure cached scanning doesn't break existing scanner behaviour."""

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        scanner = RepositoryScanner(tmp_path)
        result = scanner.scan()
        assert result.success_count == 0
        assert result.failure_count == 0

    def test_scan_non_existent_directory(self, tmp_path: Path) -> None:
        scanner = RepositoryScanner(tmp_path / "nope")
        result = scanner.scan()
        assert result.success_count == 0

    def test_scan_nested_packages(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg" / "sub"
        pkg.mkdir(parents=True)
        (pkg / "mod.py").write_text("class Foo:\n    pass\n")
        (tmp_path / "top.py").write_text("x = 1\n")

        scanner = RepositoryScanner(tmp_path)
        result = scanner.scan()
        assert result.success_count == 2
        assert Path("top.py") in result.modules
        assert Path("pkg/sub/mod.py") in result.modules

    def test_scan_skips_hidden_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "visible.py").write_text("a = 1\n")
        hidden = tmp_path / ".git"
        hidden.mkdir()
        (hidden / "secret.py").write_text("b = 2\n")

        scanner = RepositoryScanner(tmp_path)
        result = scanner.scan()
        assert result.success_count == 1
        assert Path("visible.py") in result.modules
