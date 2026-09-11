"""Differential audit — the v0.17.0 completeness oracle (permanent).

Runs the regex-based checker (``tests/helpers/differential.py``) against
the **real production pipeline** (``RepositoryScanner`` →
``build_symbol_index`` → ``ChangeDetector._extract_calls``) over the
authored corpora in ``tests/differential_corpus/``.

Every divergence between checker and parser must be fixed (parser bug)
or listed in :data:`EXPECTED_DIVERGENCES` with a written justification.
The map is checked for hygiene: no stale entries, no empty
justifications, every key a real corpus file.

The checker mirrors the parsers' *documented* boundaries (qualified Rust
calls, object-literal methods, nested functions, TS interface members),
so the divergences that remain are real findings — see
``docs/v17-audit-report.md`` for the Phase 0 classifications.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.differential import (
    LANGS,
    extract_called_names,
    extract_symbols,
    parse_corpus,
)

CORPUS_DIR = Path(__file__).parent / "differential_corpus"

# (lang, corpus_file) → {diverging key: written justification}
#
# Keys are either symbol tuples rendered as ``repr((kind, name))`` or
# bare called names.  Every entry documents an accepted edge (or a
# finding awaiting a decision) — no entry may be added without a
# justification, and the corpus must not regress into new unmapped
# divergences.
#
# REAL GAP entries (Phase 1 remediation candidates): the JS/TS call
# walker only collects *named* arrow functions as callers
# (``variable_declarator`` values).  Anonymous arrows in argument or
# return position (``fn(() => x())``, ``return () => x()``) are skipped
# by ``find_tree_sitter_calls_in_body`` — every call inside them is
# invisible to the parser.  The checker captures them (they are real
# calls), so the divergence is a genuine parser gap, not a checker
# over-capture.
EXPECTED_DIVERGENCES: dict[tuple[str, str], dict[str, str]] = {
    ("javascript", "classes.js"): {
        "increment": (
            "REAL GAP: call inside a class-field arrow value "
            "(``public_field_definition``) — the parser collects only "
            "``variable_declarator`` arrows as callers, so class-field "
            "arrow bodies are invisible. Phase 1 remediation candidate."
        ),
    },
    ("javascript", "realworld.js"): {
        "handler": (
            "REAL GAP: call inside an anonymous arrow passed as a call "
            "argument — the parser skips anonymous-arrow bodies (no "
            "caller to attribute to). Phase 1 remediation candidate."
        ),
        "unsubscribe": (
            "REAL GAP: call inside an anonymous arrow in return position "
            "— the parser skips anonymous-arrow bodies (no caller to "
            "attribute to). Phase 1 remediation candidate."
        ),
    },
    ("typescript", "realworld.ts"): {
        "off": (
            "REAL GAP: call inside an anonymous arrow in return position "
            "— the parser skips anonymous-arrow bodies (no caller to "
            "attribute to). Phase 1 remediation candidate."
        ),
    },
}

# Minimum corpus size per language (scope: 12–18 files).
MIN_CORPUS_FILES = 12


def _cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for lang in LANGS:
        lang_dir = CORPUS_DIR / lang
        for f in sorted(lang_dir.iterdir()):
            if f.is_file():
                cases.append((lang, f.name))
    return cases


_CASES = _cases()


@pytest.fixture(scope="module")
def parser_results() -> dict[str, tuple[dict[Path, set[object]], dict[Path, set[str]]]]:
    """Run the production pipeline once per language."""
    results: dict[str, tuple[dict[Path, set[object]], dict[Path, set[str]]]] = {}
    for lang in LANGS:
        symbols, calls = parse_corpus(lang, CORPUS_DIR / lang)
        results[lang] = (symbols, calls)  # type: ignore[assignment]
    return results


@pytest.mark.parametrize(
    ("lang", "corpus_file"),
    _CASES,
    ids=[f"{lang}/{name}" for lang, name in _CASES],
)
def test_differential_file(
    lang: str,
    corpus_file: str,
    parser_results: dict[str, tuple[dict[Path, set[object]], dict[Path, set[str]]]],
) -> None:
    """Checker and parser must agree on symbols and called names per file."""
    source = (CORPUS_DIR / lang / corpus_file).read_text(encoding="utf-8")

    checker_symbols = {repr(t) for t in extract_symbols(lang, source)}
    checker_calls = extract_called_names(lang, source)

    symbols_by_file, calls_by_file = parser_results[lang]
    file_key = Path(corpus_file)
    parser_symbols = {repr(t) for t in symbols_by_file.get(file_key, set())}
    parser_calls = calls_by_file.get(file_key, set())

    mapped = EXPECTED_DIVERGENCES.get((lang, corpus_file), {})

    symbol_divergences = (checker_symbols ^ parser_symbols) - set(mapped)
    call_divergences = (checker_calls ^ parser_calls) - set(mapped)

    assert not symbol_divergences, (
        f"{lang}/{corpus_file}: unmapped symbol divergences: "
        f"{sorted(symbol_divergences)}"
    )
    assert not call_divergences, (
        f"{lang}/{corpus_file}: unmapped call divergences: {sorted(call_divergences)}"
    )


# ---------------------------------------------------------------------------
# Map hygiene — the mapping may never rot
# ---------------------------------------------------------------------------


def test_every_language_has_minimum_corpus() -> None:
    """Each language corpus must meet the 12–18 file budget."""
    for lang in LANGS:
        count = len([f for f in (CORPUS_DIR / lang).iterdir() if f.is_file()])
        assert count >= MIN_CORPUS_FILES, f"{lang}: only {count} corpus files"


def test_map_keys_reference_real_corpus_files() -> None:
    """Every mapped key must be a real (lang, corpus_file) pair."""
    valid = set(_CASES)
    for key in EXPECTED_DIVERGENCES:
        assert key in valid, f"stale EXPECTED_DIVERGENCES entry: {key}"


def test_map_justifications_are_nonempty() -> None:
    """Every mapped divergence needs a written justification."""
    for (lang, corpus_file), divergences in EXPECTED_DIVERGENCES.items():
        for key, justification in divergences.items():
            assert justification.strip(), (
                f"{lang}/{corpus_file}: empty justification for {key}"
            )


def test_corpus_files_parse_cleanly() -> None:
    """Corpus files must all parse — a file that fails defeats the audit."""
    for lang in LANGS:
        symbols, calls = parse_corpus(lang, CORPUS_DIR / lang)
        assert symbols or calls, f"{lang}: corpus produced no output at all"
