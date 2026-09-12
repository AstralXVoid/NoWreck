"""Pinned accepted edges — the v0.17.0 differential audit's Section 4.

The differential corpus (``tests/test_differential_audit.py``) proves that
the checker and the production parsers *agree*; these tests prove that the
agreed behaviour is the one written down in ``docs/v17-audit-report.md``
(Section 4), so a documented boundary cannot drift silently.  Each test
names the boundary it pins.

Nothing here is new behaviour — every assertion was verified against the
parsers during Phase 0 and is mirrored by the corpus.  A failure here
means a documented limit changed and the report (and the README
Limitations table) must be updated with it.
"""

from __future__ import annotations

from pathlib import Path

from nowreck.detector.change_detector import ChangeDetector
from nowreck.scanner.go_scanner import scan_go_calls, scan_go_file
from nowreck.scanner.javascript_scanner import scan_js_calls
from nowreck.scanner.rust_scanner import scan_rust_calls
from nowreck.scanner.typescript_scanner import scan_ts_calls


def _write(tmp_path: Path, name: str, source: str) -> Path:
    """Write *source* to ``tmp_path/name`` and return the path."""
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def _called_names(tmp_path: Path, name: str, source: str, scanner: object) -> set[str]:
    """Called-name set for a single file scanned by *scanner*."""
    path = _write(tmp_path, name, source)
    return {call.called_name for call in scanner(path)}  # type: ignore[operator]


def _called_pairs(
    tmp_path: Path, name: str, source: str, scanner: object
) -> set[tuple[str, str]]:
    """``(caller_name, called_name)`` pairs for a single scanned file.

    Attribution matters as much as capture: a call with the right name
    recorded against the wrong caller is still a bug.
    """
    path = _write(tmp_path, name, source)
    return {(call.caller_name, call.called_name) for call in scanner(path)}  # type: ignore[operator]


def _python_calls(tmp_path: Path, files: dict[str, str]) -> set[str]:
    """Called-name set for a Python-only repo (goes through the detector)."""
    from nowreck.scanner.repository_scanner import RepositoryScanner

    for rel_path, source in files.items():
        _write(tmp_path, rel_path, source)
    scan = RepositoryScanner(tmp_path, use_cache=False).scan()
    return {evidence.called_name for evidence in ChangeDetector._extract_calls(scan)}


# ---------------------------------------------------------------------------
# JavaScript / TypeScript
# ---------------------------------------------------------------------------


class TestCallEdgesJsTs:
    """Boundaries shared by the JavaScript and TypeScript grammars."""

    def test_new_expression_target_is_not_a_call(self, tmp_path: Path) -> None:
        """``new X(...)`` is a ``new_expression``, not a call."""
        names = _called_names(
            tmp_path,
            "a.js",
            "function make() { const e = new Error('x'); return e; }\n",
            scan_js_calls,
        )
        assert "Error" not in names

    def test_receiver_is_a_call_excluded_inner_call_kept(self, tmp_path: Path) -> None:
        """``f().bar()`` is excluded (dynamic receiver); the inner ``f()`` is not."""
        names = _called_names(
            tmp_path,
            "a.js",
            "function run() { f().bar(); return 1; }\n",
            scan_js_calls,
        )
        assert "bar" not in names
        assert "f" in names

    def test_subscript_string_and_paren_receivers_are_captured(
        self, tmp_path: Path
    ) -> None:
        """Only a *call* receiver is excluded — these three are not calls."""
        names = _called_names(
            tmp_path,
            "a.js",
            (
                "function run() {\n"
                "  a[0].bar();\n"
                "  's'.toUpperCase();\n"
                "  (x).foo();\n"
                "  return 1;\n"
                "}\n"
            ),
            scan_js_calls,
        )
        assert {"bar", "toUpperCase", "foo"} <= names

    def test_super_method_captured_constructor_excluded(self, tmp_path: Path) -> None:
        """``super.speak()`` is captured (``super`` is an identifier);
        ``super(n)`` is a ``super`` call and is excluded."""
        names = _called_names(
            tmp_path,
            "a.js",
            (
                "class B extends A {\n"
                "  constructor(n) { super(n); }\n"
                "  speak() { super.speak(); }\n"
                "}\n"
            ),
            scan_js_calls,
        )
        assert "speak" in names
        assert "super" not in names

    def test_optional_chain_first_link_captured_second_excluded(
        self, tmp_path: Path
    ) -> None:
        """``store.fetch()?.save()`` — ``fetch`` is captured, ``save`` is not
        (its receiver is a call)."""
        names = _called_names(
            tmp_path,
            "a.js",
            "function run(store) { store.fetch()?.save(); }\n",
            scan_js_calls,
        )
        assert names == {"fetch"}

    def test_ts_new_expression_and_receiver_rules_match_js(
        self, tmp_path: Path
    ) -> None:
        """The TypeScript grammar shares every boundary above."""
        names = _called_names(
            tmp_path,
            "a.ts",
            (
                "function run(): void {\n"
                "  const e = new Error('x');\n"
                "  f().bar();\n"
                "  store.fetch()?.save();\n"
                "  return;\n"
                "}\n"
            ),
            scan_ts_calls,
        )
        assert "Error" not in names
        assert "bar" not in names
        assert names == {"f", "fetch"}


# ---------------------------------------------------------------------------
# The three audit REAL GAPs (G1/G2/G3) — fixed in Phase 1
# ---------------------------------------------------------------------------


class TestCallEdgesFixedGaps:
    """Regression pins for the Phase 0 audit's REAL GAPs.

    All three had one root cause in the shared JS/TS call walker
    (``nowreck/scanner/_tree_sitter_helpers.py``): every function-valued
    node was treated as caller-owning, so an *anonymous* arrow was skipped
    entirely — leaving its calls with no caller — and a class-field arrow
    was never collected at all.  The corpus files (`realworld.js`,
    `realworld.ts`, `classes.js`) are the catching tests; these pins assert
    the *attribution* directly, so a regression names itself.
    """

    def test_g1_anonymous_arrow_argument_belongs_to_enclosing_fn(
        self, tmp_path: Path
    ) -> None:
        """G1: ``fn(() => x())`` — the arrow has no name, so ``x`` is the
        enclosing function's call."""
        pairs = _called_pairs(
            tmp_path,
            "a.js",
            "function run(wrap) { wrap.forEach(() => tag()); }\n",
            scan_js_calls,
        )
        assert ("run", "tag") in pairs
        assert ("run", "forEach") in pairs

    def test_g2_anonymous_arrow_in_return_position(self, tmp_path: Path) -> None:
        """G2: ``return () => x()`` — same rule, return position."""
        pairs = _called_pairs(
            tmp_path,
            "a.js",
            "function make() { return () => { cleanup(); }; }\n",
            scan_js_calls,
        )
        assert ("make", "cleanup") in pairs

    def test_g2_anonymous_function_expression_argument(self, tmp_path: Path) -> None:
        """G2: an anonymous ``function`` expression is not a caller either."""
        pairs = _called_pairs(
            tmp_path,
            "a.js",
            "function run() { setTimeout(function () { late(); }); }\n",
            scan_js_calls,
        )
        assert ("run", "late") in pairs

    def test_g2_nested_anonymous_arrow_delegates_to_named_owner(
        self, tmp_path: Path
    ) -> None:
        """A nested anonymous arrow inside a named arrow stays with the
        named owner rather than becoming its own caller."""
        pairs = _called_pairs(
            tmp_path,
            "a.js",
            "const f = () => { return () => { deep(); }; };\n",
            scan_js_calls,
        )
        assert pairs == {("f", "deep")}

    def test_g3_js_class_field_arrow_is_a_caller(self, tmp_path: Path) -> None:
        """G3: JS ``field_definition`` arrows are callers named after the field."""
        pairs = _called_pairs(
            tmp_path,
            "a.js",
            "class A {\n  inc = (step) => { apply(step); };\n}\n",
            scan_js_calls,
        )
        assert pairs == {("inc", "apply")}

    def test_g3_ts_class_field_arrow_is_a_caller(self, tmp_path: Path) -> None:
        """G3: TS ``public_field_definition`` arrows — plain, typed, static."""
        pairs = _called_pairs(
            tmp_path,
            "a.ts",
            (
                "class A {\n"
                "  inc = (s: number) => { step(s); };\n"
                "  private typed: number = () => { typedCall(); };\n"
                "  static stat = () => { staticCall(); };\n"
                "}\n"
            ),
            scan_ts_calls,
        )
        assert pairs == {
            ("inc", "step"),
            ("typed", "typedCall"),
            ("stat", "staticCall"),
        }

    def test_non_function_declarator_is_not_a_caller(self, tmp_path: Path) -> None:
        """A declarator is a caller only when its value is a function —
        otherwise its calls stay with the enclosing function."""
        pairs = _called_pairs(
            tmp_path,
            "a.js",
            "function run() { const v = load(); }\n",
            scan_js_calls,
        )
        assert pairs == {("run", "load")}

    def test_class_field_non_function_value_has_no_caller(self, tmp_path: Path) -> None:
        """A class-field initialiser is class-shell content, not a caller.

        This is the class-body form of the caller-scope boundary the corpus
        already pins for module-level statements ("a call must have a
        caller"): ``n = compute()`` at class level has no caller to be
        attributed to, so it is not emitted — while the *arrow* form of the
        same field (G3, above) is.  Pinned so the asymmetry is deliberate
        and visible rather than mistaken for a missed capture.
        """
        pairs = _called_pairs(
            tmp_path,
            "a.ts",
            "class A {\n  n: number = compute();\n}\n",
            scan_ts_calls,
        )
        assert pairs == set()


# ---------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------


class TestCallEdgesRust:
    """Rust-specific structural limits."""

    def test_macro_arguments_are_opaque(self, tmp_path: Path) -> None:
        """Macro args are a flat ``token_tree`` — calls inside are invisible."""
        names = _called_names(
            tmp_path,
            "a.rs",
            'fn run() {\n    format!("{}:{}", self.prefix(), self.label());\n}\n',
            scan_rust_calls,
        )
        assert names == set()

    def test_turbofish_and_qualified_targets_not_emitted(self, tmp_path: Path) -> None:
        """``Vec::<i64>::new()`` and ``std::f64::consts::PI`` are not simple
        identifier/member targets."""
        names = _called_names(
            tmp_path,
            "a.rs",
            "fn run() { let v = Vec::<i64>::new(); let p = std::f64::consts::PI; }\n",
            scan_rust_calls,
        )
        assert names == set()

    def test_pattern_position_is_not_a_call(self, tmp_path: Path) -> None:
        """``Some``/``None`` in ``let``/``match`` patterns are not calls;
        ``Ok(..)`` / ``Err(..)`` in arm bodies are."""
        names = _called_names(
            tmp_path,
            "a.rs",
            (
                "fn run(o: Option<i32>) -> Result<i32, i32> {\n"
                "    if let Some(x) = o { return Ok(x); }\n"
                "    match o { Some(y) => Ok(y), None => Err(1) }\n"
                "}\n"
            ),
            scan_rust_calls,
        )
        assert "Some" not in names
        assert "None" not in names
        assert {"Ok", "Err"} <= names

    def test_closure_calls_attributed_to_enclosing_fn(self, tmp_path: Path) -> None:
        """Closures are not separate callers — their calls belong to the fn."""
        names = _called_names(
            tmp_path,
            "a.rs",
            (
                "fn run(items: Vec<(i32, i32)>) {\n"
                "    items.sort_by(|a, b| a.1.cmp(&b.1));\n"
                "}\n"
            ),
            scan_rust_calls,
        )
        assert {"cmp", "sort_by"} <= names

    def test_trait_default_method_body_is_a_caller(self, tmp_path: Path) -> None:
        """A trait default-method body is walked like any other caller."""
        path = _write(
            tmp_path,
            "a.rs",
            (
                "trait Drawable {\n"
                "    fn describe(&self) -> String {\n"
                "        self.draw()\n"
                "    }\n"
                "}\n"
            ),
        )
        pairs = {(call.caller_name, call.called_name) for call in scan_rust_calls(path)}
        assert ("describe", "draw") in pairs


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------


class TestCallEdgesGo:
    """Go-specific structural limits."""

    def test_paren_receiver_is_captured(self, tmp_path: Path) -> None:
        """A parenthesised expression receiver is not a call receiver."""
        names = _called_names(
            tmp_path,
            "a.go",
            (
                "package x\n\n"
                "type P struct { x, y float64 }\n\n"
                "func (p P) Len() float64 {\n"
                "\treturn (p.x*p.x + p.y*p.y).sqrt()\n"
                "}\n"
            ),
            scan_go_calls,
        )
        assert names == {"sqrt"}

    def test_type_group_maps_struct_to_class_and_alias(self, tmp_path: Path) -> None:
        """``type ( ... )`` groups use the same per-spec mapping as top level."""
        path = _write(
            tmp_path,
            "a.go",
            "package x\n\ntype (\n\tAlpha struct{ n int }\n\tBeta = string\n)\n",
        )
        kinds = {
            (symbol.symbol_type.name, symbol.name) for symbol in scan_go_file(path)
        }
        assert ("CLASS", "Alpha") in kinds
        assert ("TYPE_ALIAS", "Beta") in kinds


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


class TestCallEdgesPython:
    """Python boundaries that the detector (not a tree-sitter scanner) owns."""

    def test_decorator_call_is_captured(self, tmp_path: Path) -> None:
        """``@retry(times=5)`` emits ``retry``, attributed to the decorated fn."""
        names = _python_calls(
            tmp_path,
            {"app.py": "@retry(times=5)\ndef fetch():\n    return 1\n"},
        )
        assert names == {"retry"}

    def test_bare_decorator_emits_nothing(self, tmp_path: Path) -> None:
        """``@timed`` is a bare name, not a call."""
        names = _python_calls(
            tmp_path,
            {"app.py": "@timed\ndef fetch():\n    return 1\n"},
        )
        assert names == set()
