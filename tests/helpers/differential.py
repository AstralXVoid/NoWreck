"""Differential checker — the v0.17.0 completeness oracle.

Phase 0 infrastructure: an **independent, deliberately dumb** symbol and
call extractor per language, built on regex + line/brace tracking (no
tree-sitter, no ``ast``), compared against the production scanners by
``tests/test_differential_audit.py``.

The checker is a *completeness audit*, not a second parser:

- It compares per-file ``(kind, name)`` sets and called-name sets.
- ``parent_class`` / caller attribution are deliberately out of scope
  (regex caller-tracking would make the oracle itself untrustworthy).
- Where the production parsers have *documented* boundaries (Rust
  qualified ``ns::func()`` calls, JS object-literal methods, Python
  nested functions, TS interface members), the checker mirrors the
  boundary so the audit measures real gaps, not known design limits.

Every divergence between checker and parser is either fixed (parser bug)
or mapped in ``EXPECTED_DIVERGENCES`` with a written justification.

String/comment stripping is deliberately conservative and line-preserving:
- comments are removed (a comment containing ``def foo():`` must not
  create a phantom symbol),
- string literals are blanked with newlines preserved (code text inside
  strings must not create phantom calls),
- JS/TS, Rust and Go strip comments and literals in a **single
  left-to-right pass** (one alternation regex; the leftmost match wins),
  so there is no ordering hazard between a ``//`` inside a string and a
  quote/backtick inside a comment,
- Python strips f-strings (single- and triple-quoted, both quote styles)
  with ``{expr}`` regions preserved, then plain strings, then comments,
- regex literals in JS/TS are *not* stripped (documented limitation:
  the corpus avoids regex literals containing ``(`` or unbalanced
  braces),
- an f-string containing escaped literal braces (``f"{{x}}"``) or a
  dict literal nested inside an interpolation falls back to
  whole-literal blanking (documented limitation).
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Language registry
# ---------------------------------------------------------------------------

LANGS = ("python", "javascript", "typescript", "rust", "go", "java", "kotlin")

KIND_FUNCTION = "function"
KIND_METHOD = "method"
KIND_CLASS = "class"
KIND_INTERFACE = "interface"
KIND_ENUM = "enum"
KIND_TYPE_ALIAS = "type_alias"

# (kind, name) — the unit the audit compares.
SymbolTuple = tuple[str, str]

_IDENT = r"[A-Za-z_][A-Za-z0-9_$]*"


def is_dunder_name(name: str) -> bool:
    """Mirror of ``_tree_sitter_helpers.is_dunder_name`` (``^__.*__$``)."""
    return len(name) >= 4 and name.startswith("__") and name.endswith("__")


# ---------------------------------------------------------------------------
# Comment / string stripping (line-based, newline-preserving)
# ---------------------------------------------------------------------------


def _blank(match: re.Match[str]) -> str:
    """Replace a match with spaces, preserving newlines."""
    return re.sub(r"[^\n]", " ", match.group(0))


# Python: triple-quoted f-strings, plain triple-quoted strings,
# f-strings (expressions preserved), single-line strings, then
# comments.  Strings are stripped *before* comments so a ``#`` inside
# a string literal is never mistaken for a comment start.
_PY_TRIPLE = re.compile(
    r'"""(?:[^"\\]|\\.|"(?!""))*(?:"""|$)'
    r"|\'\'\'(?:[^\'\\]|\\.|\'(?!\'\'))*(?:\'\'\'|$)"
)
_PY_STRING = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")
_PY_COMMENT = re.compile(r"#[^\n]*")
# f-strings (``f"..."``, ``f'...'``, ``rf"..."``, ``fr'...'``): literal
# parts are blanked but ``{expression}`` regions are preserved — calls
# inside them are real calls (``f"{self.prefix()}"``).  Both quote
# styles and both the single-line and triple-quoted forms are handled.
# An f-string containing escaped literal braces (``f"{{x}}"``) falls
# back to whole-literal blanking, and braces nested deeper than one
# level (a dict literal inside an interpolation) are a documented
# limitation — the corpus stays shallow.
_PY_FSTRING = re.compile(
    r"(?:[rR][fF]|[fF][rR]|[fF])"
    r"(?:\"(?:[^\"\\{]|\\.)*(?:\{[^\"{}]*\}[^\"\\{]*)*\""
    r"|'(?:[^'\\{]|\\.)*(?:\{[^'{}]*\}[^'\\{]*)*')"
)
_PY_FTRIPLE = re.compile(
    r"(?:[rR][fF]|[fF][rR]|[fF])"
    r"(?:\"\"\"(?:[^\"\\{]|\\.|\"(?!\"\"))*"
    r"(?:\{[^\"{}]*\}(?:[^\"\\{]|\\.|\"(?!\"\"))*)*\"\"\""
    r"|'''(?:[^'\\{]|\\.|'(?!''))*"
    r"(?:\{[^'{}]*\}(?:[^'\\{]|\\.|'(?!''))*)*''')",
    re.DOTALL,
)


def _blank_fstring(match: re.Match[str]) -> str:
    """Blank an f-string's literal parts, keeping ``{expr}`` verbatim."""
    text = match.group(0)
    out: list[str] = []
    depth = 0
    for ch in text:
        if ch == "{":
            depth += 1
            out.append(ch)
        elif ch == "}":
            depth = max(0, depth - 1)
            out.append(ch)
        elif depth > 0:
            out.append(ch)
        else:
            out.append(" " if ch != "\n" else "\n")
    return "".join(out)


def _strip_python(source: str) -> str:
    src = _PY_FTRIPLE.sub(_blank_fstring, source)
    src = _PY_TRIPLE.sub(_blank, src)
    src = _PY_FSTRING.sub(_blank_fstring, src)
    src = _PY_STRING.sub(_blank, src)
    return _PY_COMMENT.sub(_blank, src)


# JS/TS: a single left-to-right pass matches block comments, line
# comments, template literals, and quoted strings as alternatives.
# ``re.sub`` scans left to right and the leftmost match wins, so a
# ``//`` inside a string (``"https://x"``) is consumed by the *string*
# match that starts earlier, and a backtick inside a comment is consumed
# by the *comment* match that starts earlier — no ordering hazard.
# Template literal bodies are blanked but ``${...}`` interpolation
# regions are preserved — calls inside them are real calls
# (```${this.prefix()}``).  Nested braces deeper than one level inside
# ``${...}`` (object literals in interpolations) fall back to
# whole-literal blanking — documented limitation; the corpus stays
# level-1.
_JS_TOKEN = re.compile(
    r"(?P<block>/\*.*?\*/)"
    r"|(?P<line>//[^\n]*)"
    r"|(?P<template>`(?:[^`\\]|\\.)*`)"
    r"|(?P<string>'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")",
    re.DOTALL,
)


def _blank_js_template(match: re.Match[str]) -> str:
    """Blank a template literal's text, keeping ``${expr}`` verbatim."""
    text = match.group(0)
    out: list[str] = []
    depth = 0
    i = 0
    while i < len(text):
        if text[i : i + 2] == "${":
            depth += 1
            out.append("${")
            i += 2
            continue
        ch = text[i]
        if ch == "}" and depth > 0:
            depth -= 1
            out.append(ch)
        elif depth > 0:
            out.append(ch)
        else:
            out.append(" " if ch != "\n" else "\n")
        i += 1
    return "".join(out)


def _strip_javascript(source: str) -> str:
    """Blank comments and string/template literals in one ordered pass."""
    return _JS_TOKEN.sub(
        lambda m: _blank_js_template(m) if m.lastgroup == "template" else _blank(m),
        source,
    )


def _strip_typescript(source: str) -> str:
    return _strip_javascript(source)


# Rust: a single left-to-right pass matches line comments, block
# comments, raw strings, byte/plain strings, and char literals as
# alternatives — the leftmost match wins, so a ``//`` inside a string
# or a ``"`` inside a comment can never be misattributed (no ordering
# hazard).  Char literals are exactly one char (or one escape): a
# greedy ``*`` would swallow lifetimes (``&'a str``,
# ``struct User<'a> {``) across lines and blank real code.  ``'a``
# never closes on the same line, so ``'\u{...}'``-style escapes still
# match via ``\\.`` + ``[^'\\\n]``.
_RS_TOKEN = re.compile(
    r"(?P<line>//[^\n]*)"
    r"|(?P<block>/\*.*?\*/)"
    r"|(?P<raw>(?:b|br)?r(?P<hashes>#+)"
    r'"(?:[^"]|"(?!(?P=hashes)))*"(?P=hashes))'
    r"|(?P<string>b?\"(?:\\.|[^\"\\])*\")"
    r"|(?P<char>'(?:\\.|[^'\\\n])')",
    re.DOTALL,
)
# Macro invocations: ``name!(...)`` / ``name![...]`` / ``name!{...}``.
# The tree-sitter grammar parses macro arguments as a flat ``token_tree``
# (verified against tree-sitter-rust) — calls inside a macro are
# structurally invisible to the parser, so the checker blanks the whole
# invocation.  ``!`` must be immediately followed by the delimiter so
# ``a != (b)`` is never mistaken for a macro.
_RS_MACRO = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\s*!([\[({])")


def _blank_rust_macros(src: str) -> str:
    """Blank every macro invocation with balanced-delimiter tracking.

    Strings/raw strings are stripped first, so text inside them can
    never unbalance the scan.  Nested macros (``format!("{} ",
    foo!(x))``) balance naturally.  ``macro_rules! name { ... }``
    definitions are blanked too (their bodies are ``token_tree`` as
    well — the parser emits nothing from them).
    """
    out: list[str] = []
    last = 0
    for match in _RS_MACRO.finditer(src):
        out.append(src[last : match.start()])
        opener = match.group(1)
        closer = {"[": "]", "(": ")", "{": "}"}[opener]
        depth = 0
        i = match.end() - 1  # the delimiter char itself
        while i < len(src):
            ch = src[i]
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out.append(re.sub(r"[^\n]", " ", src[match.start() : i + 1]))
        last = i + 1
    out.append(src[last:])
    return "".join(out)


def _strip_rust(source: str) -> str:
    """Blank comments, strings and char literals, then macro bodies."""
    src = _RS_TOKEN.sub(_blank, source)
    return _blank_rust_macros(src)


# Go: a single left-to-right pass matches block comments, line comments,
# raw backtick strings, interpreted strings, and rune literals as
# alternatives — the leftmost match wins, so a ``//`` inside a string
# or a backtick inside a comment can never be misattributed (no
# ordering hazard).
_GO_TOKEN = re.compile(
    r"(?P<block>/\*.*?\*/)"
    r"|(?P<line>//[^\n]*)"
    r"|(?P<raw>`[^`]*`)"
    r"|(?P<string>\"(?:\\.|[^\"\\])*\")"
    r"|(?P<rune>'(?:\\.|[^'\\])*')",
    re.DOTALL,
)


def _strip_go(source: str) -> str:
    """Blank comments and string/rune literals in one ordered pass."""
    return _GO_TOKEN.sub(_blank, source)


# Java: a single left-to-right pass matches block comments, line
# comments, text blocks (``"""``), double-quoted strings and character
# literals as alternatives — the leftmost match wins, so a ``//`` inside
# a string or a quote inside a comment can never be misattributed (no
# ordering hazard).  The text-block alternative **must** precede the
# plain-string one: both start at a ``"`` and the earlier alternative
# wins, so ``"""…"""`` is consumed whole instead of leaving a dangling
# quote behind (J7 — the grammar models text blocks as
# ``string_literal`` and so does the stripper).  Text blocks may span
# lines and a trailing ``\`` continues them, hence ``re.DOTALL``.
_JAVA_TOKEN = re.compile(
    r"(?P<block>/\*.*?\*/)"
    r"|(?P<line>//[^\n]*)"
    r'|(?P<textblock>"""(?:\\.|[^\\])*?""")'
    r'|(?P<string>"(?:\\.|[^"\\])*"'
    r"|'(?:\\.|[^'\\])*')",
    re.DOTALL,
)


def _strip_java(source: str) -> str:
    """Blank comments, text blocks, strings and char literals in one pass."""
    return _JAVA_TOKEN.sub(_blank, source)


# Kotlin: a single left-to-right pass matches block comments, line
# comments, raw (triple-quoted) strings, plain strings and char literals
# as alternatives — the leftmost match wins, so a ``//`` inside a string
# or a quote inside a comment can never be misattributed (no ordering
# hazard).  The raw alternative **must** precede the plain-string one:
# both start at a ``"`` and the earlier alternative wins, so ``"""…"""``
# is consumed whole instead of leaving a dangling quote behind (K7 — the
# grammar models a raw string as ``multiline_string_literal``).  Raw
# strings may span lines, hence ``[\s\S]``; a plain string may not.
_KOTLIN_TOKEN = re.compile(
    r"(?P<block>/\*.*?\*/)"
    r"|(?P<line>//[^\n]*)"
    r'|(?P<raw>"""(?:\\.|[\s\S])*?""")'
    r'|(?P<string>"(?:\\.|[^"\\\n])*")'
    r"|(?P<char>'(?:\\.|[^'\\\n])*')",
    re.DOTALL,
)


def _strip_kotlin(source: str) -> str:
    """Blank comments and string/char literals in one ordered pass.

    Strings are blanked whole \u2014 interpolation included \u2014 and the calls
    inside a ``${\u2026}`` region are recovered separately by
    :func:`_kotlin_interpolation_names`.  Keeping the region here instead
    would leak an interpolation's ``)`` into the *receiver* test of the
    following line — a raw string whose last line interpolates, with
    ``.trimIndent()`` chained on after it, which is how that shape reads in
    real code.
    """
    return _KOTLIN_TOKEN.sub(_blank, source)


# ``${\u2026}`` interpolation: the parser sees real calls in here (probe K7),
# so they are collected from the raw line and only inside a caller body.
_KOTLIN_INTERPOLATION = re.compile(r"\$\{(?P<body>[^{}]*)\}", re.DOTALL)


def _kotlin_interpolation_names(raw_lines: list[str], mask: list[int]) -> set[str]:
    """Called names inside ``${\u2026}`` interpolation (probe K7).

    ``"total: ${format(count)}"`` holds a real ``call_expression``, so the
    name is collected from the *raw* line \u2014 on rows that already sit
    inside a caller body, which is exactly where the parser attributes it.
    A multi-line interpolation is a documented limitation (the corpus
    stays single-line, as the JS/TS template rule does).
    """
    names: set[str] = set()
    keywords = _KEYWORDS["kotlin"]
    pattern = re.compile(rf"(?<![A-Za-z0-9_$])({_IDENT})\s*\(")
    for i, line in enumerate(raw_lines):
        if mask[i] < 0:
            continue
        for interpolation in _KOTLIN_INTERPOLATION.finditer(line):
            for match in pattern.finditer(interpolation.group("body")):
                name = match.group(1)
                if name not in keywords:
                    names.add(name)
    return names


_STRIPPERS = {
    "python": _strip_python,
    "javascript": _strip_javascript,
    "typescript": _strip_typescript,
    "rust": _strip_rust,
    "go": _strip_go,
    "java": _strip_java,
    "kotlin": _strip_kotlin,
}


# ---------------------------------------------------------------------------
# Keywords that may precede ``(`` but are not calls
# ---------------------------------------------------------------------------

_KEYWORDS: dict[str, frozenset[str]] = {
    "python": frozenset(
        {
            "if",
            "for",
            "while",
            "with",
            "elif",
            "else",
            "return",
            "lambda",
            "and",
            "or",
            "not",
            "in",
            "is",
            "assert",
            "del",
            "global",
            "nonlocal",
            "pass",
            "raise",
            "yield",
            "import",
            "from",
            "as",
            "match",
            "case",
            "except",
            "def",
            "class",
            "async",
            "await",
            "type",
        }
    ),
    "javascript": frozenset(
        {
            "if",
            "for",
            "while",
            "switch",
            "catch",
            "with",
            "function",
            "return",
            "throw",
            "new",
            "delete",
            "typeof",
            "instanceof",
            "void",
            "in",
            "of",
            "do",
            "else",
            "case",
            "default",
            "break",
            "continue",
            "debugger",
            "import",
            "export",
            "yield",
            "await",
            "async",
            "static",
            "class",
            "const",
            "let",
            "var",
            "this",
            "super",
            "extends",
            "implements",
            # NOTE: ``get``/``set``/``from`` are NOT keywords — they are
            # ordinary method names (``obj.get(x)``, ``static
            # from(seed)`` are real calls/methods the parser captures).
            # Getter/setter *declarations* (``get size() {``) are
            # excluded by the method-header modifier groups instead.
        }
    ),
    "typescript": frozenset(
        {
            "if",
            "for",
            "while",
            "switch",
            "catch",
            "with",
            "function",
            "return",
            "throw",
            "new",
            "delete",
            "typeof",
            "instanceof",
            "void",
            "in",
            "of",
            "do",
            "else",
            "case",
            "default",
            "break",
            "continue",
            "debugger",
            "import",
            "export",
            "yield",
            "await",
            "async",
            "static",
            "class",
            "const",
            "let",
            "var",
            "this",
            "super",
            "extends",
            "implements",
            # ``as`` STAYS a keyword in TS: ``x as (T)`` type-assertion
            # parens are not calls.  (``as`` as a method name is a
            # documented checker limitation — the corpus avoids it.)
            "as",
            "interface",
            "type",
            "enum",
            "namespace",
            "declare",
            "abstract",
            "readonly",
            "keyof",
            "infer",
            "satisfies",
            "is",
            "asserts",
            "using",
            "module",
            "global",
            "unknown",
            "never",
            "any",
            "string",
            "number",
            "boolean",
            "symbol",
            "object",
            "undefined",
            "null",
            "true",
            "false",
            "public",
            "private",
            "protected",
            "override",
            "out",
            "require",
            # NOTE: ``get``/``set`` are NOT keywords — see the JavaScript
            # list comment.  Getter/setter declarations are excluded by
            # the method-header modifier groups instead.
        }
    ),
    "rust": frozenset(
        {
            "if",
            "for",
            "while",
            "loop",
            "match",
            "return",
            "fn",
            "impl",
            "trait",
            "struct",
            "enum",
            "let",
            "mut",
            "const",
            "static",
            "where",
            "move",
            "async",
            "await",
            "unsafe",
            "pub",
            "use",
            "mod",
            "type",
            "in",
            "as",
            "break",
            "continue",
            "else",
        }
    ),
    "go": frozenset(
        {
            "if",
            "for",
            "switch",
            "case",
            "return",
            "func",
            "go",
            "defer",
            "select",
            "range",
            "var",
            "const",
            "type",
            "map",
            "chan",
            "interface",
            "struct",
            "break",
            "continue",
            "else",
            "fallthrough",
            "goto",
            "import",
            "package",
        }
    ),
    "java": frozenset(
        {
            "if",
            "else",
            "for",
            "while",
            "do",
            "switch",
            "case",
            "default",
            "break",
            "continue",
            "return",
            "throw",
            "try",
            "catch",
            "finally",
            "assert",
            "synchronized",
            "new",
            "instanceof",
            "this",
            "super",
            "class",
            "interface",
            "enum",
            "extends",
            "implements",
            "throws",
            "import",
            "package",
            "yield",
            "void",
            "public",
            "protected",
            "private",
            "static",
            "final",
            "abstract",
            "native",
            "strictfp",
            "transient",
            "volatile",
            "boolean",
            "byte",
            "char",
            "short",
            "int",
            "long",
            "float",
            "double",
            # NOTE: ``record`` / ``var`` / ``sealed`` / ``permits`` are
            # *contextual* keywords in Java — they are legal method
            # names (``obj.record()``), so they are deliberately NOT
            # listed here.
        }
    ),
    "kotlin": frozenset(
        {
            "if",
            "else",
            "for",
            "while",
            "do",
            "when",
            "return",
            "break",
            "continue",
            "throw",
            "try",
            "catch",
            "finally",
            "class",
            "interface",
            "object",
            "enum",
            "super",
            "this",
            "null",
            "true",
            "false",
            "is",
            "as",
            "in",
            "val",
            "var",
            "fun",
            "typealias",
            "package",
            "import",
            "out",
            "where",
            "typeof",
            "constructor",
            "companion",
            "init",
            # NOTE: ``get``/``set``/``by``/``field``/``value``/``dynamic``/
            # ``suspend`` are *soft* keywords in Kotlin — ``list.get(0)``
            # and ``obj.field()`` are ordinary calls — so they are
            # deliberately NOT listed (probe K12e).  Accessor heads are
            # blanked instead, and the D5/D6 soft-keyword defects live in
            # the grammar, not in the call-name extraction.
        }
    ),
}

# ---------------------------------------------------------------------------
# Caller-scope masks — per-line "inside a function-like body" tracking
# ---------------------------------------------------------------------------
#
# The production extractors only record calls that occur *inside* a
# function/method/arrow body — a call needs a caller to be attributed
# to, so module-level statements like ``compute_total([1, 2, 3])`` are
# never emitted.  The checker mirrors that boundary with a per-line
# mask; a called name only counts when its line is inside a caller
# body.  Lambdas (Python), closures (Rust/Go) and expression-bodied
# arrows nested in call arguments at module level are documented
# checker limitations: the corpus avoids call-bearing instances, and
# the parser's own boundaries are the ground truth.

_JS_FN_FUNCTION = re.compile(
    r"\bfunction\s*\*?\s*(?:[A-Za-z_$][A-Za-z0-9_$]*)?(?:\s*<[^>]*>)?\s*\("
)
# Class methods, object-literal methods (``m() {``), and TS methods
# with a return type (``m(): T {``), incl. async/static/generic forms
# (``async get() {``, ``static from() {``, ``on<T>(...): R {``).  The
# keyword lookahead keeps ``if (x) {`` / ``for (..) {`` control flow
# from opening a body.  Requires the body ``{`` on the same line.
# Single source for the method-header shape: both the caller-scope
# mask and the symbol extractor use this (with ``_JS_METHOD_OPEN`` as
# the multi-line start) so the two can never drift apart.
_JS_METHOD = re.compile(
    r"(?:^\s*|[{,]\s*)(?:static\s+|async\s+|get\s+|set\s+|\*\s*)*"
    r"(?!(?:if|for|while|switch|catch|with|do|else|return|throw|new|"
    r"typeof|delete|void|in|of|case|default|break|continue|debugger|"
    r"import|export|yield|await|class|extends|implements|interface|"
    r"type|enum|namespace|declare|abstract|this|super|function)\b)"
    r"(" + _IDENT + r")(?:\s*<[^>]*>)?\s*\([^)]*\)\s*(?::[^{;]*)?\{"
)
# Multi-line method-header *start* (``method(`` with the body ``{`` on
# a later line): same shape without the closing ``)``/``{`` — only
# honoured when the line's parens are unbalanced, so ``foo(bar);`` and
# ``foo(bar)`` (balanced calls) never qualify.
_JS_METHOD_OPEN = re.compile(
    r"(?:^\s*|[{,]\s*)(?:static\s+|async\s+|get\s+|set\s+|\*\s*)*"
    r"(?!(?:if|for|while|switch|catch|with|do|else|return|throw|new|"
    r"typeof|delete|void|in|of|case|default|break|continue|debugger|"
    r"import|export|yield|await|class|extends|implements|interface|"
    r"type|enum|namespace|declare|abstract|this|super|function)\b)"
    r"(" + _IDENT + r")(?:\s*<[^>]*>)?\s*\("
)
# Detection-only opener: the mask only needs ``search()`` to hit, so no
# capture group; the symbol extractor uses ``_RS_FN_DECL`` (modifiers +
# name capture).  Distinct names keep the two from shadowing.
_RS_FN = re.compile(r"\bfn\s+" + _IDENT)
_GO_FN = re.compile(r"\bfunc\b")


def _body_colon(line: str, def_match: re.Match[str]) -> int | None:
    """Index of the body colon on a ``def`` line, or None.

    The colon must sit outside brackets/parens — annotation colons
    (``x: int``) and ``-> T`` are inside or after the signature and
    must not count as the body colon.
    """
    depth = 0
    for idx in range(def_match.end(), len(line)):
        ch = line[idx]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ":" and depth == 0:
            return idx
    return None


def _py_call_mask(source: str) -> list[int]:
    """Per-line body-start column: 0 inside a ``def`` body, -1 outside.

    Nested defs are callers too; a def line with an inline body
    (``def f(): return g()``) starts its body right after the colon,
    so ``g`` counts but the ``def``/signature itself never does.
    """
    src = _strip_python(source)
    lines = src.splitlines()
    mask = [-1] * len(lines)
    fn_indents: list[int] = []  # indent of each open def
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        while fn_indents and fn_indents[-1] >= indent:
            fn_indents.pop()
        # Decorator lines (``@deco(...)``) are attributed to the
        # decorated function by the parser — the call counts even at
        # module level.
        if stripped.startswith("@"):
            mask[i] = 0
            continue
        def_match = _DEF_RE.match(stripped)
        if def_match:
            # Single-line body: ``def f(): return g()`` — the call
            # after the body colon is inside the function.
            body_colon = _body_colon(line, def_match)
            if body_colon is not None and line[body_colon + 1 :].strip():
                mask[i] = body_colon + 1
            fn_indents.append(indent)
        elif fn_indents:
            mask[i] = 0
    return mask


def _brace_fn_mask(
    source: str,
    strip: object,
    opener: re.Pattern[str],
) -> list[int]:
    """Per-line body-start column for brace languages (Rust, Go).

    Tracks open function-like bodies with a stack of the brace depth at
    which each body opened.  A line gets the column of its body
    opening ``{`` (``fn foo() { bar(); }`` → ``bar`` counts, the
    signature never does); body lines get 0; everything else -1.
    Opener lines whose body brace lands on a later line (multi-line
    signatures) keep ``pending_fn`` set until the ``{`` or a ``;``
    (prototype — no body) appears.
    """
    src = strip(source)  # type: ignore[operator]
    lines = src.splitlines()
    mask = [-1] * len(lines)
    depth = 0
    fn_stack: list[int] = []
    pending_fn = False
    for i, line in enumerate(lines):
        stripped_line = line.strip()
        if not stripped_line:
            continue
        opens = stripped_line.count("{")
        closes = stripped_line.count("}")
        depth_before = depth
        opens_fn = pending_fn or opener.search(stripped_line) is not None
        if opens_fn:
            # Opener lines take precedence over enclosing bodies: a
            # nested ``fn``/method definition line is a *definition*,
            # not a call site, until its own body brace opens.
            body_brace = line.find("{")
            mask[i] = body_brace if body_brace != -1 else -1
        elif fn_stack:
            mask[i] = 0
        if pending_fn:
            if opens > 0:
                fn_stack.append(depth_before)
                pending_fn = False
            elif line.rstrip().endswith(";"):
                pending_fn = False
        if opens_fn and not pending_fn and not line.rstrip().endswith(";"):
            if opens > 0:
                fn_stack.append(depth_before)
            else:
                pending_fn = True
        depth += opens - closes
        while fn_stack and depth <= fn_stack[-1]:
            fn_stack.pop()
    return mask


def _js_call_mask(source: str) -> list[int]:
    """Per-line body-start column for JS/TS.

    Like :func:`_brace_fn_mask`, plus expression-bodied arrows (no
    ``{``): the body starts right after ``=>``.
    """
    src = _strip_javascript(source)
    lines = src.splitlines()
    mask = [-1] * len(lines)
    depth = 0
    fn_stack: list[int] = []
    pending_fn = False
    for i, line in enumerate(lines):
        stripped_line = line.strip()
        if not stripped_line:
            continue
        opens = stripped_line.count("{")
        closes = stripped_line.count("}")
        depth_before = depth
        arrow = "=>" in stripped_line
        method_same_line = _JS_METHOD.search(stripped_line) is not None
        method_open = _JS_METHOD_OPEN.search(
            stripped_line
        ) is not None and stripped_line.count("(") > stripped_line.count(")")
        opens_fn = (
            pending_fn
            or _JS_FN_FUNCTION.search(stripped_line) is not None
            or method_same_line
            or method_open
            # An expression-bodied arrow on a line *inside* an enclosing
            # body is not an opener: calls before the ``=>`` belong to
            # the enclosing function and still count, so the line keeps
            # the enclosing body-start column (0).  Only a top-level
            # arrow (``const f = () => ...``) opens a body here.
            or (arrow and not fn_stack)
        )
        if opens_fn:
            body_brace = line.find("{")
            if body_brace != -1:
                mask[i] = body_brace
            elif arrow:
                mask[i] = line.find("=>") + 2
            else:
                mask[i] = -1
        elif fn_stack:
            mask[i] = 0
        if pending_fn:
            if opens > 0:
                fn_stack.append(depth_before)
                pending_fn = False
            elif line.rstrip().endswith(";"):
                pending_fn = False
        if opens_fn and not pending_fn and not line.rstrip().endswith(";"):
            if opens > 0:
                fn_stack.append(depth_before)
            elif not arrow:
                pending_fn = True
            # else: expression-bodied arrow — body on this line only.
        depth += opens - closes
        while fn_stack and depth <= fn_stack[-1]:
            fn_stack.pop()
    return mask


def _rust_call_mask(source: str) -> list[int]:
    """Per-line body-start column for Rust (fns, impl/trait methods)."""
    return _brace_fn_mask(source, _strip_rust, _RS_FN)


def _go_call_mask(source: str) -> list[int]:
    """Per-line body-start column for Go (funcs and methods)."""
    return _brace_fn_mask(source, _strip_go, _GO_FN)


# ---------------------------------------------------------------------------
# Java: declaration heads (methods, constructors, types)
# ---------------------------------------------------------------------------
#
# Java has no declaration keyword to anchor on — a method header is
# ``name(params)`` like a call — so the checker classifies each
# *statement* by shape.  A declaration is a ``name(...)`` group whose name
# is preceded by a modifier/return-type prefix (``public int m(``,
# ``void m(``, ``default int m(``) and whose prefix is neither a
# control-flow head nor an assignment/member chain.
#
# Rejections that keep ordinary statements and control flow out:
# ``foo(x);`` (bare name, ``;`` form), ``obj.foo(x);`` and
# ``System.out.println(x);`` (prefix ends with ``.``), ``x = foo();``
# (prefix ends with ``=``), ``Util.<T>parse(x);`` (prefix ends with
# ``>``), ``return foo();`` / ``assert foo();`` / ``yield foo();``
# (prefix head is a keyword), ``throw new Foo();`` / ``new Foo().bar();``
# / anonymous-class bodies (prefix ends with ``new``), ``if (x) {`` /
# ``for (…) {`` / ``catch (E e) {`` / ``switch (x) {`` /
# ``synchronized (l) {`` (name is a control keyword), ``(x) -> {`` (no
# paren group closes the head) and ``static {`` / ``{`` (no paren group
# at all).  A **bare** ``Name(...)`` head is a declaration only in front
# of a ``{`` — ``Foo(int x) {`` is a package-private constructor while
# ``foo(x);`` is a call statement.
_JAVA_NON_DECL_NAMES = frozenset(
    {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "synchronized",
        "new",
        "return",
        "throw",
        "assert",
        "do",
        "else",
        "case",
        "yield",
        "this",
        "super",
        "instanceof",
        "try",
        "finally",
        "default",
    }
)
# First word of the prefix: a control-flow / expression statement head.
# ``default`` is deliberately absent — it is a legal method modifier
# (``default int doubleIt() {``).
_JAVA_NON_DECL_PREFIX = frozenset(
    {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "synchronized",
        "try",
        "do",
        "else",
        "return",
        "throw",
        "assert",
        "new",
        "case",
        "yield",
        "break",
        "continue",
        "instanceof",
        "this",
        "super",
        "package",
        "import",
    }
)
# A prefix ending in one of these is never a declaration head.
_JAVA_PREFIX_BAD_TAIL = ".)]=+-*/&|!?:,"


def _java_head_names(head: str, *, allow_bare: bool) -> tuple[str, bool] | None:
    """Classify a brace-free Java statement head as a method/constructor.

    Returns ``(name, has_prefix)`` — ``has_prefix`` is False for a bare
    ``Name(...)`` head, the shape a package-private constructor shares with
    an enum constant that has a body — or ``None`` when *head* is not a
    declaration.  ``allow_bare`` must be True when classifying a head that
    precedes a ``{`` (``Foo(int x) {`` is a constructor) and False for a
    head that precedes a ``;`` (``foo(x);`` is a call statement).
    """
    s = re.sub(r"\s+", " ", head).strip()
    if not s:
        return None
    # The head must end in ``)``, optionally followed by ``throws E``.
    tail = re.search(r"\)(?:\s+throws\s+[\w$.,<>\[\]\s]+)?$", s)
    if tail is None:
        return None
    depth = 0
    open_paren = -1
    j = tail.start()
    while j >= 0:
        ch = s[j]
        if ch == ")":
            depth += 1
        elif ch == "(":
            depth -= 1
            if depth == 0:
                open_paren = j
                break
        j -= 1
    if open_paren < 0:
        return None
    # The name must be the identifier immediately before ``(``.
    k = open_paren - 1
    while k >= 0 and s[k].isspace():
        k -= 1
    if k < 0 or not (s[k].isalnum() or s[k] in "_$"):
        return None
    end = k + 1
    while k >= 0 and (s[k].isalnum() or s[k] in "_$"):
        k -= 1
    name = s[k + 1 : end]
    prefix = s[: k + 1].strip()
    if name in _JAVA_NON_DECL_NAMES:
        return None
    if prefix:
        # ``obj.m(x)`` / ``x = m(x)`` / ``Util.<T>parse(x)`` are calls.
        if prefix[-1] in _JAVA_PREFIX_BAD_TAIL or _java_explicit_type_args(prefix):
            return None
        first_word = re.split(r"[\s(\[<]", prefix, maxsplit=1)[0]
        if first_word in _JAVA_NON_DECL_PREFIX:
            return None
        # ``throw new Foo(...);`` / ``new Foo(...) {`` (anonymous body).
        if re.search(r"\bnew\s*$", re.sub(r"<[^<>]*>\s*$", "", prefix)):
            return None
    elif not allow_bare:
        # A body-less ``;`` declaration always has a modifier or return
        # type; a bare ``foo(x);`` is a call statement.
        return None
    return name, bool(prefix)


def _java_explicit_type_args(prefix: str) -> bool:
    """Whether *prefix* ends in *call* type arguments (``Util.<T>``).

    ``Util.<String>parse(x)`` is a call — its ``<`` follows a ``.`` —
    while ``Map<String, Long> m(x)`` is a return type whose ``<`` follows
    the type name.  Both end in ``>``, so the opener is what decides.
    """
    if not prefix.endswith(">"):
        return False
    depth = 0
    i = len(prefix) - 1
    while i >= 0:
        if prefix[i] == ">":
            depth += 1
        elif prefix[i] == "<":
            depth -= 1
            if depth == 0:
                return i >= 1 and prefix[i - 1] == "."
        i -= 1
    return False


# Type declarations: ``class`` / ``interface`` / ``@interface`` /
# ``enum`` / ``record``.  The preceding anchor keeps ``SomeType.class``
# (a class literal) from matching.
_JAVA_TYPE_RE = re.compile(
    r"(?:^|[\s;{}])"
    r"(?:(?:@[\w$.]+(?:\s*\([^)]*\))?)\s*)*"
    r"(?:(?:public|protected|private|static|final|abstract|sealed|strictfp)\s+)*"
    r"(?P<kind>@interface|interface|class|enum|record)\s+(?P<name>\w+)"
)


# Annotation and modifier prefixes that may precede a declaration name.
_JAVA_ANNOTATION_PREFIX = re.compile(r"(?:@[\w$.]+(?:\s*\([^)]*\))?\s*)*")
_JAVA_MODIFIER_PREFIX = re.compile(
    r"(?:(?:public|protected|private|static|final|abstract|default|native|"
    r"strictfp|synchronized|sealed|transient|volatile)\s+)*"
)


def _java_strip_modifiers(head: str) -> str:
    """Drop leading annotations and modifiers from a declaration *head*.

    ``public Point`` and ``@Deprecated private Point`` both reduce to
    ``Point`` — the shape a record's compact constructor reduces to, which
    is how it is recognised (it has no parameter list to anchor on).
    """
    flat = re.sub(r"\s+", " ", head).strip()
    flat = _JAVA_ANNOTATION_PREFIX.sub("", flat)
    flat = _JAVA_MODIFIER_PREFIX.sub("", flat)
    return flat.strip()


def _java_type_head(head: str) -> tuple[str, str] | None:
    """``(kind, name)`` for a type declaration *head*, else ``None``.

    ``record`` is a contextual keyword, so it only counts as a
    declaration when a parameter list follows (``record Foo(int x)``);
    ``record Foo;`` (a variable declaration) does not.
    """
    match = _JAVA_TYPE_RE.search(head)
    if match is None:
        return None
    kind = match.group("kind")
    if kind == "record":
        rest = head[match.end() :]
        if not re.match(r"\s*(?:<[^>]*>)?\s*\(", rest):
            return None
    return kind, match.group("name")


class _JavaEvent(NamedTuple):
    """One structural event from :func:`_java_structure`.

    ``event`` is ``"open"`` (a ``{``), ``"close"`` (a ``}``) or
    ``"semi"`` (a statement-level ``;`` — a semicolon inside parentheses
    belongs to a ``for`` header and is not a boundary).
    ``symbol_kind``/``name`` describe a symbol the parser would emit (one
    of ``KIND_CLASS``/``KIND_INTERFACE``/``KIND_ENUM``/``KIND_METHOD``) or
    are ``None``.  ``is_fn`` is True when an ``open`` brace begins a body
    that owns calls (a method, a constructor, or a record's compact
    constructor).  ``index`` is the event's offset in the source and
    ``head_start`` the offset where a *declaration* head starts, which is
    whitespace-blanked before call extraction; it is ``None`` when the
    head may legitimately contain calls (control flow, anonymous classes).
    """

    event: str
    symbol_kind: str | None
    name: str | None
    is_fn: bool
    index: int
    head_start: int | None


def _java_structure(src: str) -> Iterator[_JavaEvent]:
    """Walk stripped Java source, yielding structural events.

    Classification works on the *statement* text between boundaries, not
    on a single line, so a header split across lines (a wrapped return
    type or a multi-line parameter list) is still classified correctly.
    The parser is the ground truth and this walk mirrors it: members are
    symbols only while the innermost open body is a *type* body, and an
    enum constant with a body is never a method.
    """
    stack: list[tuple[str, str, str, bool]] = []
    stmt_start = 0
    paren = 0
    for idx, ch in enumerate(src):
        if ch == "(":
            paren += 1
            continue
        if ch == ")":
            paren = max(0, paren - 1)
            continue
        if ch == "{":
            head = src[stmt_start:idx]
            innermost = stack[-1] if stack else None
            at_type_level = innermost is None or innermost[0] == "type"
            methods_are_symbols = at_type_level and (
                innermost is None or innermost[2] != "annotation"
            )
            enum_constants = (
                innermost is not None
                and innermost[0] == "type"
                and innermost[2] == "enum"
                and innermost[3]
            )
            type_head = _java_type_head(head)
            decl = (
                None
                if type_head is not None
                else _java_head_names(head, allow_bare=True)
            )
            # Enum constants are separated by commas, so the head of a
            # constant with a body starts with ```` ,```` — classify it
            # without the separator.
            enum_decl = (
                _java_head_names(head.lstrip(" \t\n,"), allow_bare=True)
                if enum_constants
                else None
            )
            symbol_kind: str | None = None
            name: str | None = None
            is_fn = False
            blank_from: int | None = None
            if type_head is not None:
                tk, tname = type_head
                if tk in ("@interface", "interface"):
                    symbol_kind = KIND_INTERFACE
                elif tk == "enum":
                    symbol_kind = KIND_ENUM
                else:
                    symbol_kind = KIND_CLASS
                name = tname
                blank_from = stmt_start
                # ``@interface`` is a distinct member-grammar: its
                # elements are ``annotation_type_element_declaration``
                # nodes, so they are NOT method symbols (nested types
                # inside it still are).
                type_kind = "annotation" if tk == "@interface" else tk
                stack.append(
                    ("type", tname, type_kind, tk == "enum")
                    if at_type_level
                    else ("block", "", "", False)
                )
            elif enum_decl is not None and not enum_decl[1]:
                # ``PLUS(1) { … }`` — an enum constant with a body; it is
                # not a method and owns no symbols.
                blank_from = stmt_start
                stack.append(("block", "", "", False))
            elif decl is not None:
                if methods_are_symbols:
                    symbol_kind = KIND_METHOD
                    name = decl[0]
                is_fn = True
                blank_from = stmt_start
                stack.append(("block", "", "", False))
            else:
                bare = _java_strip_modifiers(head)
                if (
                    innermost is not None
                    and innermost[0] == "type"
                    and innermost[2] == "record"
                    and bare == innermost[1]
                ):
                    # A record's compact constructor: ``Point { … }``,
                    # possibly with modifiers and annotations.
                    symbol_kind = KIND_METHOD
                    name = bare
                    is_fn = True
                    blank_from = stmt_start
                stack.append(("block", "", "", False))
            if not at_type_level:
                symbol_kind = None
                name = None
            yield _JavaEvent("open", symbol_kind, name, is_fn, idx, blank_from)
            stmt_start = idx + 1
        elif ch == "}":
            if stack:
                stack.pop()
            stmt_start = idx + 1
            yield _JavaEvent("close", None, None, False, idx, None)
        elif ch == ";" and paren == 0:
            head = src[stmt_start:idx]
            head_start = stmt_start
            stmt_start = idx + 1
            innermost = stack[-1] if stack else None
            at_type_level = innermost is None or innermost[0] == "type"
            methods_are_symbols = at_type_level and (
                innermost is None or innermost[2] != "annotation"
            )
            enum_constants = (
                innermost is not None
                and innermost[0] == "type"
                and innermost[2] == "enum"
                and innermost[3]
            )
            decl = _java_head_names(head, allow_bare=False)
            if decl is not None and methods_are_symbols:
                yield _JavaEvent("semi", KIND_METHOD, decl[0], False, idx, head_start)
            else:
                if decl is None and enum_constants:
                    # The ``;`` that ends an enum's constant region.
                    stack[-1] = ("type", innermost[1], "enum", False)
                yield _JavaEvent("semi", None, None, False, idx, None)


def _blank_java_decl_heads(src: str) -> str:
    """Blank the *declaration* heads of stripped Java source.

    Call extraction must not read a method/constructor/type header as if
    it were a call — ``void render() {`` and ``enum Mode { FAST(1) {``
    both contain ``name(`` shapes.  Head spans come from the same
    :func:`_java_structure` walk that drives symbols and the caller mask,
    so a head can never be blanked in one place and honoured in another.
    Control-flow heads are deliberately left intact: ``if (check()) {``
    contains a real call, and so does an anonymous-class head.

    Whole-head blanking is sound for declarations: a valid Java header
    holds only modifiers, annotations with constant arguments and
    parameter types — none of which is a ``method_invocation``.
    """
    spans: list[tuple[int, int]] = []
    for ev in _java_structure(src):
        if ev.head_start is not None:
            spans.append((ev.head_start, ev.index))
    if not spans:
        return src
    chars = list(src)
    for start, end in spans:
        for i in range(start, end):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def _java_call_mask(source: str) -> list[int]:
    """Per-line body-start column for Java (methods and constructors).

    Only method/constructor bodies are callers: a call needs a caller to
    be attributed to, so class-level fields, initializer blocks and
    annotation arguments are excluded.  Anonymous-class and lambda bodies
    are *not* openers — their calls attribute to the nearest enclosing
    method (the same anonymous-function rule the JS/TS walker applies) —
    while a local or nested class's own methods are callers.
    """
    src = _strip_java(source)
    lines = src.splitlines()
    mask = [-1] * len(lines)
    line_starts: list[int] = []
    offset = 0
    for line in lines:
        line_starts.append(offset)
        offset += len(line) + 1
    brace_stack: list[tuple[int, bool]] = []
    fn_ranges: list[tuple[int, int]] = []
    opened_col: dict[int, int] = {}
    for ev in _java_structure(src):
        row = bisect_right(line_starts, ev.index) - 1
        if ev.event == "open":
            brace_stack.append((row, ev.is_fn))
            if ev.is_fn and row not in opened_col:
                opened_col[row] = ev.index - line_starts[row]
        elif ev.event == "close" and brace_stack:
            open_row, open_is_fn = brace_stack.pop()
            if open_is_fn:
                fn_ranges.append((open_row, row))
    # ``running`` counts how many call-owning bodies cover each row: 0 →
    # not a caller, 1 → inside one (mask from its opening column), 2+ →
    # nested, so the enclosing body's start (0) governs.
    deltas = [0] * (len(lines) + 1)
    for start, end in fn_ranges:
        deltas[start] += 1
        if end + 1 <= len(lines):
            deltas[end + 1] -= 1
    running = 0
    for i in range(len(lines)):
        running += deltas[i]
        if running > 1:
            mask[i] = 0
        elif running == 1:
            mask[i] = opened_col.get(i, 0)
    return mask


# ---------------------------------------------------------------------------
# Kotlin
# ---------------------------------------------------------------------------
#
# Kotlin is the least keyword-shaped of the nine grammars and the checker
# therefore mirrors the scanner's *documented* boundaries rather than a
# keyword list (probes K1–K11):
#
# * a member is a symbol only while the innermost open body is a **type**
#   body — a local ``fun`` inside a method body and an enum-entry body's
#   methods are not symbols (K1/K11), while a nested class's members are;
# * ``interface`` is a type kind, ``enum``/``annotation`` are modifiers
#   that change it (``annotation class`` → ``interface``, matching Java's
#   ``@interface``), and ``companion object`` is a type body with **no**
#   symbol of its own (K3) — named or not;
# * caller bodies are ``fun`` bodies and expression bodies, secondary
#   constructors, property accessors and function-valued properties.
#   Class-level property initialisers, ``init`` blocks and *primary*
#   constructor defaults own no calls (K11) — which is why a *type* head
#   is blanked before call extraction, exactly as a Java declaration head
#   is (``Base()`` in ``class A : Base()`` is a ``delegation_specifier``,
#   not a call, and so is a primary-constructor default);
# * a ``fun`` head is **not** blanked — only its name token is — because a
#   Kotlin parameter default (``fun f(x: Int = compute())``) *is* a call
#   (K11), unlike Java's annotation arguments;
# * ``${…}`` interpolation survives the stripper, so ``"x ${format(v)}"``
#   still reports ``format`` (K7).

_KOTLIN_MODIFIERS = (
    "public|private|protected|internal|open|abstract|final|override|sealed|"
    "data|value|enum|annotation|inner|expect|actual|external|inline|infix|"
    "operator|suspend|tailrec|const|lateinit|vararg|reified|crossinline|"
    "noinline|companion|fun|out"
)
_KOTLIN_ANNOTATION_PREFIX = r"(?:@[\w.]+(?:\s*\([^)]*\))?\s+)*"
_KOTLIN_MODIFIER_PREFIX = rf"(?:(?:{_KOTLIN_MODIFIERS})\s+)*"
_KOTLIN_DECL_PREFIX = _KOTLIN_ANNOTATION_PREFIX + _KOTLIN_MODIFIER_PREFIX

_KOTLIN_TYPE_DECL = re.compile(
    r"(?P<prefix>"
    + _KOTLIN_DECL_PREFIX
    + r")"
    + r"(?P<kind>class|interface|object|typealias)\s+(?P<name>"
    + _IDENT
    + r")"
)
_KOTLIN_UNNAMED_COMPANION = re.compile(
    _KOTLIN_ANNOTATION_PREFIX + r"companion\s+object\b"
)
_KOTLIN_FUN_KEYWORD = re.compile(r"(?:^|[\s;{}])fun\s+")
_KOTLIN_CTOR_HEAD = re.compile(_KOTLIN_DECL_PREFIX + r"constructor\s*\(")
_KOTLIN_ACCESSOR_HEAD = re.compile(_KOTLIN_DECL_PREFIX + r"(?P<accessor>get|set)\s*\(")
_KOTLIN_FUNCTION_PROPERTY = re.compile(
    _KOTLIN_DECL_PREFIX + r"(?:val|var)\s+" + _IDENT + r"[^=\n]*=\s*(?:\{|fun\s*\()"
)
# Continuation characters: a statement that ends with one of these keeps
# accumulating across a newline (``fun f(): Int =`` then the expression on
# the next line).  The test reads the *raw* line, so a blanked string or a
# trailing comment can never masquerade as a continuation.
_KOTLIN_CONTINUATION_TAIL = ",.+-*/:=?"


def _kotlin_statement_continues(stripped: str, raw: str, paren_depth: int) -> bool:
    """Whether the statement opened so far continues past the newline.

    Kotlin has no statement terminator, so the boundary is the first
    newline at paren depth 0 — unless the line ends in an operator, in
    which case the expression continues (``fun f(): Int =`` / ``class A :``).
    The *raw* text decides: the stripped copy has had string and comment
    text replaced by spaces, which would make ``val x = "s"`` look like a
    dangling ``=``.

    ``paren_depth`` is the walker's live paren count.  It settles the case
    the tail character cannot: a multi-line parameter list whose last line
    ends in a *type* — ``fun f(\n    items: List<Int>\n)`` — must keep
    accumulating, and no tail heuristic can see that
    (``…List<Int>`` ends in ``>``).
    """
    if paren_depth > 0:
        return True
    tail = raw.rstrip()
    if not tail:
        return True
    if tail[-1] in "([{":
        return True
    if tail.endswith(("&&", "||", "->")):
        return True
    if tail[-1] in _KOTLIN_CONTINUATION_TAIL:
        return True
    return not stripped.strip()


def _kotlin_fun_name(head: str) -> tuple[str, int, int] | None:
    """``(name, start, end)`` of a ``fun`` declaration head, else ``None``.

    The name is the last identifier before the parameter list in every
    spelling: ``fun f(``, ``fun <T> f(`` and ``fun List<String>.f(`` —
    the extension receiver is simply an earlier identifier.
    """
    match = _KOTLIN_FUN_KEYWORD.search(head)
    if match is None:
        return None
    open_paren = head.find("(", match.end())
    if open_paren < 0:
        return None
    prefix = head[:open_paren].rstrip()
    if prefix.endswith(">"):
        # Drop a trailing type-parameter list: ``fun map<R>(`` names ``map``,
        # not ``R``.  (A receiver's type arguments close earlier, so the
        # last ``<``\u2026``>`` pair is the only one that can sit here.)
        depth = 0
        for i in range(len(prefix) - 1, -1, -1):
            if prefix[i] == ">":
                depth += 1
            elif prefix[i] == "<":
                depth -= 1
                if depth == 0:
                    prefix = prefix[:i].rstrip()
                    break
    found = list(re.finditer(_IDENT, prefix))
    if not found:
        return None
    last = found[-1]
    return last.group(0), last.start(), last.end()


def _kotlin_param_open(
    head: str,
    fun_name: tuple[str, int, int] | None,
    accessor: bool,
    ctor: bool,
) -> int:
    """Offset of the parameter list's ``(`` in a declaration head, or ``-1``.

    Anchoring on the name (for ``fun``) or on the ``get``/``set``/
    ``constructor`` keyword matters when an annotation carries its own
    parens: in ``@Ann(1) fun f(x: Int = compute())`` the *first* ``(`` in
    the head belongs to the annotation, and reading it as the parameter
    list would put the return-type span over the parameters — blanking
    the default value's call (probe K11).
    """
    if fun_name is not None:
        return head.find("(", fun_name[2])
    pattern = _KOTLIN_CTOR_HEAD if ctor else _KOTLIN_ACCESSOR_HEAD
    stripped = head.lstrip()
    match = pattern.match(stripped)
    if match is None:
        return -1
    return len(head) - len(stripped) + match.end() - 1


def _kotlin_return_type_span(
    head: str, open_paren: int, end: int | None
) -> tuple[int, int] | None:
    """Span between a parameter list's ``)`` and the declaration body.

    A return type holds no call evidence, but it does hold ``IDENT {``
    shapes that the trailing-lambda pass would read as a call
    (``fun f(): (Int) -> Int {``).  *end* is the ``=`` that opens an
    expression body, or ``None`` for a brace-opened head (the whole rest
    of the head).  The parameter list itself is never included: a default
    value there *is* a call (K11).
    """
    if open_paren < 0:
        return None
    depth = 0
    for i in range(open_paren, len(head)):
        ch = head[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                start = i + 1
                stop = len(head) if end is None else end - 1
                return (start, stop) if stop > start else None
    return None


def _kotlin_type_head(head: str) -> tuple[str, SymbolTuple | None] | None:
    """``(container kind, symbol)`` for a type-declaration head, else ``None``.

    ``typealias`` is reported as a statement-level symbol (it has no
    body), while a companion object -- named or not -- is a **type**
    container that contributes no symbol of its own (K3).
    """
    stripped = head.lstrip()
    match = _KOTLIN_TYPE_DECL.match(stripped)
    if match is None:
        if _KOTLIN_UNNAMED_COMPANION.match(stripped) is not None:
            return "type", None
        return None
    prefix = match.group("prefix")
    words = prefix.split()
    kind = match.group("kind")
    name = match.group("name")
    if "companion" in words:
        return "type", None
    if kind == "typealias":
        return "stmt", (KIND_TYPE_ALIAS, name)
    if "enum" in words:
        return "type", (KIND_ENUM, name)
    if "annotation" in words or kind == "interface":
        return "type", (KIND_INTERFACE, name)
    return "type", (KIND_CLASS, name)


class _KotlinEvent(NamedTuple):
    """One structural event from :func:`_kotlin_structure`.

    ``event`` is ``"open"`` (a ``{``), ``"close"`` (a ``}``) or
    ``"stmt"`` (a newline/semicolon statement boundary).
    ``symbol_kind``/``name`` describe a symbol the parser would emit, or
    are ``None``.  ``is_fn`` marks a body that owns calls; ``body_start``
    is where that body begins (the ``{``, or the offset just after ``=``
    for an expression body).  ``blanks`` are the spans removed before call
    extraction — a whole *type* head, a ``fun``'s name token, and its
    return-type tail (see :func:`_kotlin_return_type_span`).
    """

    event: str
    symbol_kind: str | None
    name: str | None
    is_fn: bool
    index: int
    body_start: int | None
    blanks: tuple[tuple[int, int], ...]


def _kotlin_structure(src: str, raw: str) -> Iterator[_KotlinEvent]:
    """Walk stripped Kotlin source, yielding structural events.

    ``src`` is the stripped copy (offsets align with ``raw``), used for
    the character walk so a brace inside a string never counts; ``raw``
    decides statement continuation, so a blanked literal cannot look like
    a dangling operator (see :func:`_kotlin_statement_continues`).
    """
    stack: list[tuple[str, str]] = []  # (container kind, type name)
    stmt_start = 0
    paren = 0
    i = 0
    while i < len(src):
        ch = src[i]
        if ch == "(":
            paren += 1
            i += 1
            continue
        if ch == ")":
            paren = max(0, paren - 1)
            i += 1
            continue
        if ch != "{" and ch != "}" and ch != "\n" and ch != ";":
            i += 1
            continue
        # Braces are counted at *any* paren depth: Kotlin lambdas are
        # arguments (``process(x, { … })``) and a secondary constructor's
        # delegation holds one too (``: this({ … })``) — skipping those
        # openers while still counting their closers would unbalance the
        # stack and misplace every following member.
        if ch == "{":
            head = src[stmt_start:i]
            innermost = stack[-1] if stack else None
            at_type_level = innermost is None or innermost[0] == "type"
            enclosing_name = (
                innermost[1] if innermost and innermost[0] == "type" else ""
            )
            kind: str | None = None
            name: str | None = None
            is_fn = False
            blanks: list[tuple[int, int]] = []
            body_start: int | None = None
            container = "block"
            expression = _kotlin_expression_start(head)
            type_head = _kotlin_type_head(head)
            fun_name = None if type_head is not None else _kotlin_fun_name(head)
            accessor = (
                type_head is None
                and fun_name is None
                and _KOTLIN_ACCESSOR_HEAD.match(head.lstrip()) is not None
            )
            ctor = (
                type_head is None
                and fun_name is None
                and not accessor
                and _KOTLIN_CTOR_HEAD.match(head.lstrip()) is not None
            )
            if type_head is not None:
                container, symbol = type_head
                if symbol is not None and at_type_level:
                    kind, name = symbol
                blanks.append((stmt_start, i))
            elif fun_name is not None or accessor or ctor:
                is_fn = True
                if ctor:
                    if at_type_level and enclosing_name:
                        kind, name = KIND_METHOD, enclosing_name
                elif fun_name is not None and at_type_level:
                    kind = KIND_FUNCTION if innermost is None else KIND_METHOD
                    name = fun_name[0]
                open_paren = _kotlin_param_open(head, fun_name, accessor, ctor)
                if fun_name is not None:
                    blanks.append((stmt_start + fun_name[1], stmt_start + fun_name[2]))
                tail = _kotlin_return_type_span(
                    head,
                    open_paren,
                    expression if expression is not None else len(head),
                )
                if tail is not None:
                    blanks.append((stmt_start + tail[0], stmt_start + tail[1]))
                if expression is not None:
                    # ``fun f() = run { \u2026 }``: this brace opens the
                    # *expression's* lambda, so the caller body starts at
                    # the ``=`` \u2014 keeping the whole expression, lambda
                    # included, inside the caller.
                    body_start = stmt_start + expression
                else:
                    # The body starts at the parameter list: a parameter
                    # default is a call that belongs to *this* function
                    # (``fun f(x: Int = compute())``, probe K11), while the
                    # name token before the ``(`` is already blanked.
                    body_start = stmt_start + open_paren if open_paren >= 0 else i
            elif _KOTLIN_FUNCTION_PROPERTY.match(head.lstrip() + "{") is not None:
                # A function-valued property owns the calls in its lambda
                # (probe K6); the brace is the value, so it is appended
                # before matching.
                is_fn = True
                body_start = i
            if at_type_level and container == "type":
                stack.append(("type", name or enclosing_name))
            else:
                stack.append(("block", ""))
            yield _KotlinEvent("open", kind, name, is_fn, i, body_start, tuple(blanks))
            stmt_start = i + 1
        elif ch == "}":
            if stack:
                stack.pop()
            stmt_start = i + 1
            yield _KotlinEvent("close", None, None, False, i, None, ())
        else:  # a newline or semicolon at paren depth 0
            head = src[stmt_start:i]
            raw_head = raw[stmt_start:i]
            if ch == "\n" and _kotlin_statement_continues(head, raw_head, paren):
                i += 1
                continue
            kind = None
            name = None
            is_fn = False
            body_start: int | None = None
            blanks = []
            innermost = stack[-1] if stack else None
            at_type_level = innermost is None or innermost[0] == "type"
            if head.strip():
                type_head = _kotlin_type_head(head)
                fun_name = None if type_head is not None else _kotlin_fun_name(head)
                accessor = (
                    type_head is None
                    and fun_name is None
                    and (_KOTLIN_ACCESSOR_HEAD.match(head.lstrip()) is not None)
                )
                ctor = (
                    type_head is None
                    and fun_name is None
                    and not accessor
                    and _KOTLIN_CTOR_HEAD.match(head.lstrip()) is not None
                )
                if type_head is not None:
                    symbol = type_head[1]
                    if symbol is not None and at_type_level:
                        kind, name = symbol
                    blanks.append((stmt_start, i))
                elif fun_name is not None:
                    if at_type_level:
                        kind = KIND_FUNCTION if innermost is None else KIND_METHOD
                        name = fun_name[0]
                    blanks.append((stmt_start + fun_name[1], stmt_start + fun_name[2]))
                # An expression body (``fun f() = expr`` / ``get() = expr``)
                # owns calls from the ``=`` to the statement boundary.
                equals = _kotlin_expression_start(head)
                if equals is not None:
                    is_fn = fun_name is not None or accessor
                    body_start = stmt_start + equals
                if fun_name is not None or accessor or ctor:
                    open_paren = _kotlin_param_open(head, fun_name, accessor, ctor)
                    tail = _kotlin_return_type_span(head, open_paren, equals)
                    if tail is not None:
                        blanks.append((stmt_start + tail[0], stmt_start + tail[1]))
            yield _KotlinEvent("stmt", kind, name, is_fn, i, body_start, tuple(blanks))
            stmt_start = i + 1
        i += 1


def _kotlin_expression_start(head: str) -> int | None:
    """Offset just after the top-level ``=`` that opens an expression body.

    ``None`` when the head has no such ``=`` — a brace-opened declaration,
    or an ordinary statement.  ``==``/``!=``/``<=``/``>=`` and a ``->``
    arrow never open a body, and neither does an ``=`` inside the
    parameter list (``fun f(x: Int = 1) = 2`` picks the second one).
    """
    depth = 0
    i = 0
    while i < len(head):
        ch = head[i]
        if ch in "([<":
            depth += 1
        elif ch in ")]>":
            depth = max(0, depth - 1)
        elif ch == "=" and depth == 0:
            prev = head[i - 1] if i else ""
            nxt = head[i + 1] if i + 1 < len(head) else ""
            if nxt == "=" or prev in "!=<>+-*/%&":
                i += 1
                continue
            return i + 1
        i += 1
    return None


def _blank_kotlin_decl_heads(source: str) -> str:
    """Blank Kotlin spans that must never read as calls.

    Two spans, for two different reasons: a **type** head (``class A :
    Base()`` — a ``delegation_specifier`` is not a call, and a
    primary-constructor default is class-level code that owns nothing,
    K11) and a ``fun``'s **name token** only (so ``fun render() {`` does
    not read as a call to ``render``).  A ``fun``'s parameter list is
    deliberately left intact, because ``fun f(x: Int = compute())`` *is* a
    call (K11) — the reason this cannot blank whole heads the way the Java
    checker does.

    Both the walk and the blanking run on the stripped copy, but statement
    boundaries are decided on the *original* source (:func:`_kotlin_structure`
    takes both) so a blanked literal can never shift a boundary.
    """
    src = _strip_kotlin(source)
    spans = [span for ev in _kotlin_structure(src, source) for span in ev.blanks]
    if not spans:
        return src
    chars = list(src)
    for start, end in spans:
        for i in range(start, end):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def _kotlin_call_mask(source: str) -> list[int]:
    """Per-line caller-body mask for Kotlin (``fun``/ctor/accessor bodies).

    Class-level property initialisers, ``init`` blocks and primary
    constructor defaults own no calls (K11, the Java-family rule), so their
    rows stay at ``-1``; a *nested* caller body's rows get column ``0``,
    exactly as the Java mask does.
    """
    src = _strip_kotlin(source)
    lines = src.splitlines()
    mask = [-1] * len(lines)
    line_starts: list[int] = []
    offset = 0
    for line in lines:
        line_starts.append(offset)
        offset += len(line) + 1
    brace_stack: list[tuple[int, bool, int]] = []
    regions: list[tuple[int, int, int]] = []
    for ev in _kotlin_structure(src, source):
        row = bisect_right(line_starts, ev.index) - 1
        if ev.event == "open":
            # An expression-bodied caller anchors at its ``=``, so the whole
            # expression (lambda included) sits inside the caller body.
            anchor = ev.body_start if ev.body_start is not None else ev.index
            row = bisect_right(line_starts, anchor) - 1
            brace_stack.append((row, ev.is_fn, anchor - line_starts[row]))
        elif ev.event == "close":
            if not brace_stack:
                continue
            open_row, open_is_fn, col = brace_stack.pop()
            if open_is_fn:
                regions.append((open_row, row, col))
        elif ev.event == "stmt" and ev.is_fn and ev.body_start is not None:
            start_row = bisect_right(line_starts, ev.body_start) - 1
            regions.append((start_row, row, ev.body_start - line_starts[start_row]))
    deltas = [0] * (len(lines) + 1)
    opened_col: dict[int, int] = {}
    for start, end, col in regions:
        deltas[start] += 1
        if end + 1 <= len(lines):
            deltas[end + 1] -= 1
        opened_col.setdefault(start, col)
    running = 0
    for row in range(len(lines)):
        running += deltas[row]
        if running > 1:
            mask[row] = 0
        elif running == 1:
            mask[row] = opened_col.get(row, 0)
    # A chained continuation (a row that opens with ``.``, ``?:`` or a
    # boolean operator) belongs to the caller that owns the row above it:
    # Kotlin writes
    #     fun total() = items
    #         .map { it.value }
    #         .sum()
    # and the parser attributes every one of those calls to ``total``.
    for row in range(1, len(lines)):
        if mask[row] >= 0 or mask[row - 1] < 0:
            continue
        opening = lines[row].lstrip()
        if opening[:1] == "." or opening.startswith(("?:", "?.", "&&", "||")):
            mask[row] = mask[row - 1] if mask[row - 1] > 0 else 0
    return mask


_MASKS: dict[str, object] = {
    "python": _py_call_mask,
    "javascript": _js_call_mask,
    "typescript": _js_call_mask,
    "rust": _rust_call_mask,
    "go": _go_call_mask,
    "java": _java_call_mask,
    "kotlin": _kotlin_call_mask,
}


# ---------------------------------------------------------------------------
# Called-name extraction (language-agnostic core)
# ---------------------------------------------------------------------------


def _paren_is_call(text: str, close_idx: int) -> bool:
    """Whether the ``)`` at *close_idx* closes a *call* paren group.

    Scans back to the matching ``(``; a call when the ``(`` is preceded
    by an identifier character, ``>`` (generics), a closer, or a quote
    (``f().bar()``, ``Foo<T>().bar()``).  A ``(`` preceded by anything
    else (operator, ``(``, line start) is a grouped expression — the
    parser captures ``(x).foo()`` / ``(a*b).sqrt()`` because the
    receiver is ``parenthesized_expression``, not ``call_expression``.
    """
    depth = 1
    idx = close_idx - 1
    while idx >= 0 and depth:
        ch = text[idx]
        if ch == ")":
            depth += 1
        elif ch == "(":
            depth -= 1
        idx -= 1
    if depth:
        # Unbalanced — conservative: treat as a call (old behaviour).
        return True
    open_idx = idx + 1
    if open_idx == 0:
        return False
    before = text[open_idx - 1]
    return before.isalnum() or before in "_$>)]}'\"`"


def _receiver_is_call(lines: list[str], i: int, name_start: int) -> bool:
    """Whether ``.name`` at *name_start* has a *call* receiver.

    Only a receiver that is itself a ``call_expression`` is excluded by
    the parsers (``f().bar()``).  Subscript (``a[0].bar()``), string
    (``"s".upper()``), object-literal (``{...}.m()``), and
    parenthesized-expression (``(x).foo()``) receivers are all
    captured — verified against the production extractors.  A ``.`` at
    line start continues the previous line's expression, so the
    previous line's tail is consulted for the closer check.
    """
    if name_start < 1 or lines[i][name_start - 1] != ".":
        return False
    dot = name_start - 1
    prev = lines[i][dot - 1] if dot >= 1 else ""
    if prev == ")":
        return _paren_is_call(lines[i], dot - 1)
    if (prev == "" or prev.isspace()) and not lines[i][:dot].strip():
        # Leading dot (possibly indented) — continuation of the
        # previous line's expression.
        if i == 0:
            return False
        tail = lines[i - 1].rstrip()
        if tail and tail[-1] == ")":
            return _paren_is_call(lines[i - 1], len(tail) - 1)
    return False


# Rust match/let patterns that look like calls: ``Some(x)``, ``Ok(x)``,
# ``Err(x)``, ``None`` are *patterns* after ``let``, ``match``, or
# ``=>`` — never calls there (the parser only sees ``call_expression``
# nodes).  ``return Err(...)`` and ``Err(x)?`` stay real calls.
_RUST_PATTERN_PREFIX = re.compile(r"(?:let|match|=>)\s+$")


def _java_receiver_is_call(lines: list[str], i: int, name_start: int) -> bool:
    """Java receiver rule: only a ``method_invocation`` receiver is excluded.

    ``f().bar()`` is excluded (the receiver is itself a call), but
    ``new Foo().bar()`` is **not** — the receiver there is an
    ``object_creation_expression`` (J2), so the parser captures ``bar``.
    """
    if not _receiver_is_call(lines, i, name_start):
        return False
    text = lines[i]
    dot = name_start - 1
    if dot >= 1 and text[dot - 1] == ")":
        close = dot - 1
    else:
        if i == 0:
            return True
        prev = lines[i - 1].rstrip()
        if not prev.endswith(")"):
            return True
        text = prev
        close = len(prev) - 1
    depth = 1
    idx = close - 1
    while idx >= 0 and depth:
        ch = text[idx]
        if ch == ")":
            depth += 1
        elif ch == "(":
            depth -= 1
        idx -= 1
    open_idx = idx + 1
    k = open_idx - 1
    while k >= 0 and text[k].isspace():
        k -= 1
    # Skip the callee's own type arguments (``new Box<String>(...)``).
    if k >= 0 and text[k] == ">":
        depth = 0
        while k >= 0:
            if text[k] == ">":
                depth += 1
            elif text[k] == "<":
                depth -= 1
                if depth == 0:
                    k -= 1
                    break
            k -= 1
        while k >= 0 and text[k].isspace():
            k -= 1
    end = k + 1
    while k >= 0 and (text[k].isalnum() or text[k] in "_$"):
        k -= 1
    callee = text[k + 1 : end]
    if not callee:
        return True
    # ``new Foo(...).bar()`` / ``new Foo<T>(...).bar()`` — the receiver is
    # a constructor, not a call.
    before = re.sub(r"<[^<>]*>\s*$", "", text[: k + 1].rstrip()).rstrip()
    return not re.search(r"\bnew\s*$", before)


def _java_is_annotation(line: str, name_start: int) -> bool:
    """Whether the identifier at *name_start* is part of an ``@Annotation``.

    Annotations are never ``method_invocation`` nodes, so their argument
    parens must not be read as calls — including the qualified form
    ``@Foo.Bar(1)``, where the identifier is preceded by a dot chain.
    """
    k = name_start - 1
    while k >= 0 and (line[k] in "_$" or line[k].isalnum() or line[k] == "."):
        k -= 1
    return k >= 0 and line[k] == "@"


def _kotlin_receiver_is_call(lines: list[str], i: int, name_start: int) -> bool:
    """Kotlin receiver rule: a *call* receiver is excluded (probe K5).

    The generic ``)``/``]`` rule plus one Kotlin-only shape: a trailing
    lambda closes with ``}``, so ``items.map { \u2026 }.first()`` has a call
    receiver the generic check cannot see.  An object-literal receiver is
    always parenthesised (``(object : T {}).m()``), so this cannot swallow
    a non-call receiver.
    """
    if _receiver_is_call(lines, i, name_start):
        return True
    if name_start < 1 or lines[i][name_start - 1] != ".":
        return False
    dot = name_start - 1
    text = lines[i]
    prev = text[dot - 1] if dot >= 1 else ""
    if prev == "}":
        return True
    if (prev == "" or prev.isspace()) and not text[:dot].strip():
        if i == 0:
            return False
        tail = lines[i - 1].rstrip()
        return bool(tail) and tail[-1] == "}"
    return False


def _kotlin_trailing_lambda_names(lines: list[str], mask: list[int]) -> set[str]:
    """Called names of Kotlin *trailing-lambda* calls (``foo { \u2026 }``).

    ``list.forEach { \u2026 }`` is a ``call_expression`` whose argument is the
    lambda, so the parser reports ``forEach`` even though no ``(`` follows
    the name.  The trap is a supertype or delegation head — ``class A :
    Runnable {``, ``class A(b: B) : B by b {`` — so a name preceded by
    ``:``/``,``/``by`` is refused.
    """
    found: set[str] = set()
    keywords = _KEYWORDS["kotlin"]
    pattern = re.compile(rf"(?<![A-Za-z0-9_$])({_IDENT})\s*\{{")
    for i, line in enumerate(lines):
        body_start = mask[i]
        if body_start < 0:
            continue
        for match in pattern.finditer(line):
            if match.start() < body_start:
                continue
            name = match.group(1)
            if name in keywords:
                continue
            if _java_is_annotation(line, match.start()):
                continue
            before = line[: match.start()].rstrip()
            if before.endswith((":", ",")) or re.search(r"\bby\s*$", before):
                continue
            if _kotlin_receiver_is_call(lines, i, match.start()):
                continue
            if (
                is_dunder_name(name)
                and match.start() >= 1
                and line[match.start() - 1] == "."
            ):
                continue
            found.add(name)
    return found


def extract_called_names(lang: str, source: str) -> set[str]:
    """Return every distinct called name in *source*.

    Only calls inside function-like bodies count (a call must have a
    caller to be attributed) — module-level statements are excluded.
    Mirrors the production call extractors' documented boundary:
    - plain identifier calls ``foo()`` (keywords excluded),
    - final segment of member chains ``a.b()`` / ``a.b.c()`` incl.
      optional chains ``a?.b()`` and continuation lines ``.b()``,
    - receiver-is-a-call excluded (``f().bar()``) but subscript /
      string / paren / object-literal receivers captured,
    - ``new X(...)`` constructor calls excluded (JS/TS: ``new_expression``
      is not a ``call_expression``),
    - dunder attributes excluded (``obj.__x__()``),
    - Rust ``::``-qualified targets excluded (parser boundary) and
      ``Some``/``Ok``/``Err``/``None`` in pattern position,
    - Rust macro invocations blanked (args are a flat ``token_tree``),
    - Java declaration heads blanked (``void render() {``), annotation
      argument parens excluded (``@Foo(1)`` is not a call), and
      ``new Foo().bar()`` captured while ``f().bar()`` is excluded.
    """
    src = _STRIPPERS[lang](source)
    if lang == "java":
        # A declaration head must never read as a call (``void render() {``,
        # ``enum Mode { FAST(1) {``).
        src = _blank_java_decl_heads(src)
    elif lang == "kotlin":
        # A *type* head must never read as a call (``class A : Base()`` is a
        # delegation, a primary-constructor default is class-level code) and
        # a ``fun``'s name token is not a call either — while its parameter
        # defaults *are* (K11), which is why only the name token goes.
        src = _blank_kotlin_decl_heads(source)
    keywords = _KEYWORDS[lang]
    names: set[str] = set()
    mask = _MASKS[lang](source)  # type: ignore[operator]
    lines = src.splitlines()

    rust_guard = r"(?<!:)" if lang == "rust" else r""
    plain_re = re.compile(rf"{rust_guard}(?<![A-Za-z0-9_$])({_IDENT})\s*\(")
    for i, line in enumerate(lines):
        body_start = mask[i]
        if body_start < 0:
            continue
        for match in plain_re.finditer(line):
            if match.start() < body_start:
                continue
            name = match.group(1)
            if name in keywords:
                continue
            if lang == "java":
                if _java_is_annotation(line, match.start()):
                    continue
                if _java_receiver_is_call(lines, i, match.start()):
                    continue
            elif lang == "kotlin":
                # ``@Suppress("x")`` owns no call (an annotation argument is
                # not a ``call_expression``), and unlike Java a constructor
                # receiver *is* a call — ``Foo().bar()`` is excluded just as
                # ``f().bar()`` is.
                if _java_is_annotation(line, match.start()):
                    continue
                if _kotlin_receiver_is_call(lines, i, match.start()):
                    continue
            elif _receiver_is_call(lines, i, match.start()):
                continue
            # Dunder *attributes* (``obj.__x__()``) are excluded by the
            # parsers; a bare ``__str__()`` call is not.
            if (
                is_dunder_name(name)
                and match.start() >= 1
                and line[match.start() - 1] == "."
            ):
                continue
            # ``new X(...)`` — JS/TS/Java only: ``new_expression`` /
            # ``object_creation_expression`` is not a call expression, so
            # the parsers never emit the target.
            if lang in ("javascript", "typescript", "java") and re.search(
                r"\bnew\s+$",
                line[: match.start()],
            ):
                continue
            # Rust pattern position: ``let Some(x) = ...``,
            # ``if let Some(x) = ...``, and match-arm patterns
            # ``Some(x) => ...`` (the arm line carries no keyword).
            if lang == "rust" and name in ("Some", "Ok", "Err", "None"):
                if _RUST_PATTERN_PREFIX.search(line[: match.start()]):
                    continue
                # ``Some(x) =>`` — scan to the closing paren and check
                # the arm arrow.  Starts *after* the opening paren.
                depth = 1
                idx = match.end()
                while idx < len(line) and depth:
                    if line[idx] == "(":
                        depth += 1
                    elif line[idx] == ")":
                        depth -= 1
                    idx += 1
                if depth == 0 and line[idx:].lstrip().startswith("=>"):
                    continue
            names.add(name)

    if lang == "kotlin":
        names |= _kotlin_trailing_lambda_names(lines, mask)
        names |= _kotlin_interpolation_names(source.splitlines(), mask)

    return names


# ---------------------------------------------------------------------------
# Symbol extraction — Python (indentation-stack based)
# ---------------------------------------------------------------------------

_DEF_RE = re.compile(r"(?:async\s+)?def\s+(" + _IDENT + r")")
_CLASS_RE = re.compile(r"class\s+(" + _IDENT + r")")


def extract_symbols_python(source: str) -> set[SymbolTuple]:
    """Top-level functions/classes and one-level-deep methods.

    Mirrors ``SymbolIndexBuilder``: nested functions and nested classes
    are not symbols (their bodies are shell content of the enclosing
    class).  ``async def`` is indexed on equal footing (v0.16.0).
    """
    src = _strip_python(source)
    symbols: set[SymbolTuple] = set()
    stack: list[tuple[int, str]] = []  # (indent, kind) kind in {class, func, skip}

    for line in src.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())

        while stack and stack[-1][0] >= indent:
            stack.pop()

        class_match = _CLASS_RE.match(stripped)
        def_match = _DEF_RE.match(stripped)
        if class_match:
            if indent == 0:
                symbols.add((KIND_CLASS, class_match.group(1)))
                stack.append((indent, "class"))
            else:
                # Nested class: not a symbol; its direct methods aren't
                # symbols either (they are outer-class shell content).
                stack.append((indent, "skip"))
        elif def_match:
            if indent == 0:
                symbols.add((KIND_FUNCTION, def_match.group(1)))
            elif stack and stack[-1][1] == "class":
                symbols.add((KIND_METHOD, def_match.group(1)))
            stack.append((indent, "func"))

    return symbols


# ---------------------------------------------------------------------------
# Symbol extraction — JS / TS (brace-depth + class tracking)
# ---------------------------------------------------------------------------

_JS_EXPORT = re.compile(r"export\s+(?:default\s+)?")
_JS_CLASS = re.compile(r"class\s+(" + _IDENT + r")")
_JS_FUNCTION = re.compile(r"(?:async\s+)?function\s*\*?\s*(" + _IDENT + r")")
# Arrow consts: plain ``const f = (x) => ...``, typed params with return
# type (``const f = (x: T): R => ...``), and typed-const form
# (``const f: (x: T) => R = (x) => ...``).
_JS_ARROW = re.compile(
    r"(?:const|let|var)\s+(" + _IDENT + r")\s*=\s*(?:async\s+)?"
    r"(?:\([^)]*\)\s*(?::[^{=]*?)?|" + _IDENT + r")\s*=>"
)
_JS_ARROW_TYPED = re.compile(
    r"(?:const|let|var)\s+(" + _IDENT + r")\s*:\s*\([^)]*\)\s*=>\s*[^=;]+?\s*=\s*"
    r"(?:\([^)]*\)|" + _IDENT + r")\s*=>"
)
_JS_GENERATOR_ASSIGN = re.compile(
    r"(?:const|let|var)\s+(" + _IDENT + r")\s*=\s*function\s*\*"
)
# ``from``/``as`` are deliberately NOT in the keyword lookahead above:
# they are ordinary method names (``static from(seed)`` is a real
# method — verified against the parser); ``import/export`` statements
# never put them before ``(``.
_TS_INTERFACE = re.compile(r"interface\s+(" + _IDENT + r")")
_TS_ENUM = re.compile(r"enum\s+(" + _IDENT + r")")
_TS_TYPE_ALIAS = re.compile(r"type\s+(" + _IDENT + r")(?:<[^>]*>)?\s*=")


def _extract_ts_js(source: str, typescript: bool) -> set[SymbolTuple]:
    src = _strip_javascript(source)
    symbols: set[SymbolTuple] = set()
    depth = 0
    in_class = False
    pending_method: str | None = None

    for line in src.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        opens = stripped.count("{")
        closes = stripped.count("}")
        depth_before = depth

        if depth_before == 0:
            decl = _JS_EXPORT.sub("", stripped)
            class_match = _JS_CLASS.match(decl)
            fn_match = _JS_FUNCTION.match(decl)
            arrow_match = _JS_ARROW.match(decl)
            typed_match = _JS_ARROW_TYPED.match(decl)
            gen_match = _JS_GENERATOR_ASSIGN.match(decl)
            if class_match:
                symbols.add((KIND_CLASS, class_match.group(1)))
            elif fn_match:
                symbols.add((KIND_FUNCTION, fn_match.group(1)))
            elif arrow_match:
                symbols.add((KIND_FUNCTION, arrow_match.group(1)))
            elif typed_match:
                symbols.add((KIND_FUNCTION, typed_match.group(1)))
            elif gen_match:
                symbols.add((KIND_FUNCTION, gen_match.group(1)))
            elif typescript:
                iface_match = _TS_INTERFACE.match(decl)
                enum_match = _TS_ENUM.match(decl)
                alias_match = _TS_TYPE_ALIAS.match(decl)
                if iface_match:
                    symbols.add((KIND_INTERFACE, iface_match.group(1)))
                elif enum_match:
                    symbols.add((KIND_ENUM, enum_match.group(1)))
                elif alias_match:
                    symbols.add((KIND_TYPE_ALIAS, alias_match.group(1)))
        elif in_class and depth_before == 1:
            method_match = _JS_METHOD.match(stripped)
            open_match = _JS_METHOD_OPEN.match(stripped)
            if method_match:
                name = method_match.group(1)
                if name not in _KEYWORDS["typescript"]:
                    symbols.add((KIND_METHOD, name))
            elif open_match and stripped.count("(") > stripped.count(")"):
                # Multi-line signature start: ``method(`` with the body
                # brace on a later line — only when the parens are
                # unbalanced (``foo(bar)`` — balanced — is a call).
                name = open_match.group(1)
                if name not in _KEYWORDS["typescript"]:
                    symbols.add((KIND_METHOD, name))
                    pending_method = name
            elif pending_method:
                # A ``;`` before any ``{`` means the pending "method"
                # was a multi-line call — undo it.
                if stripped.endswith(";"):
                    symbols.discard((KIND_METHOD, pending_method))
                    pending_method = None
                elif "{" in stripped:
                    pending_method = None

        depth += opens - closes
        if depth == 0:
            in_class = False
            pending_method = None
        elif class_match_in_line(stripped, opens, closes):
            in_class = True

    return symbols


def class_match_in_line(stripped: str, opens: int, closes: int) -> bool:
    """True when this line opens a top-level ``class ... {`` body."""
    return opens > closes and _JS_CLASS.match(_JS_EXPORT.sub("", stripped)) is not None


def extract_symbols_javascript(source: str) -> set[SymbolTuple]:
    return _extract_ts_js(source, typescript=False)


def extract_symbols_typescript(source: str) -> set[SymbolTuple]:
    return _extract_ts_js(source, typescript=True)


# ---------------------------------------------------------------------------
# Symbol extraction — Rust (brace-depth + impl tracking)
# ---------------------------------------------------------------------------

_RS_MODIFIERS = (
    r"(?:pub(?:\([^)]*\))?\s+)?(?:async\s+|unsafe\s+|extern\s+\"[^\"]*\"\s+"
    r"|const\s+|default\s+)*"
)
_RS_FN_DECL = re.compile(_RS_MODIFIERS + r"fn\s+(" + _IDENT + r")")
_RS_STRUCT = re.compile(_RS_MODIFIERS + r"struct\s+(" + _IDENT + r")")
_RS_TRAIT = re.compile(_RS_MODIFIERS + r"trait\s+(" + _IDENT + r")")
_RS_ENUM = re.compile(_RS_MODIFIERS + r"enum\s+(" + _IDENT + r")")
_RS_TYPE = re.compile(_RS_MODIFIERS + r"type\s+(" + _IDENT + r")\s*=")


def extract_symbols_rust(source: str) -> set[SymbolTuple]:
    """Top-level fns/structs/traits/enums/type aliases + impl methods.

    Mirrors ``rust_scanner``: trait methods and nested fns are not
    symbols; ``impl``-block ``fn`` items are methods; ``impl Trait for
    X`` bodies attribute to the first type name (parser boundary —
    checker only records ``(method, name)``, so attribution is
    irrelevant here).
    """
    src = _strip_rust(source)
    symbols: set[SymbolTuple] = set()
    depth = 0
    in_impl = False
    pending_impl = False

    for line in src.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        opens = stripped.count("{")
        closes = stripped.count("}")
        depth_before = depth

        if depth_before == 0:
            if pending_impl and "{" in stripped:
                in_impl = True
                pending_impl = False
            elif not pending_impl and re.match(r"impl\b", stripped):
                pending_impl = "{" not in stripped
                if "{" in stripped:
                    in_impl = True

        if not in_impl and depth_before == 0:
            fn_match = _RS_FN_DECL.match(stripped)
            struct_match = _RS_STRUCT.match(stripped)
            trait_match = _RS_TRAIT.match(stripped)
            enum_match = _RS_ENUM.match(stripped)
            type_match = _RS_TYPE.match(stripped)
            if fn_match:
                symbols.add((KIND_FUNCTION, fn_match.group(1)))
            elif struct_match:
                symbols.add((KIND_CLASS, struct_match.group(1)))
            elif trait_match:
                symbols.add((KIND_INTERFACE, trait_match.group(1)))
            elif enum_match:
                symbols.add((KIND_ENUM, enum_match.group(1)))
            elif type_match:
                symbols.add((KIND_TYPE_ALIAS, type_match.group(1)))
        elif in_impl and depth_before == 1:
            fn_match = _RS_FN_DECL.match(stripped)
            if fn_match:
                symbols.add((KIND_METHOD, fn_match.group(1)))

        depth += opens - closes
        if depth == 0:
            in_impl = False
            # ``pending_impl`` survives depth-0 lines: a multi-line
            # ``impl<K, V> Registry<K, V> where ... {`` keeps depth 0
            # while its where-clause lines pass by — resetting here
            # would orphan the impl (verified audit finding).  It is
            # cleared when the ``{`` opens the body.

    return symbols


# ---------------------------------------------------------------------------
# Symbol extraction — Go (line-based)
# ---------------------------------------------------------------------------

_GO_FUNC = re.compile(r"func\s+(" + _IDENT + r")(?:\[[^\]]*\])?\s*\(")
_GO_METHOD = re.compile(r"func\s*\([^)]*\)\s+(" + _IDENT + r")\s*\(")
# Generics: ``type Box[T any] struct`` / ``type Pair[K, V any] struct`` —
# the type-parameter list sits between the name and the keyword.
_GO_TYPE_STRUCT = re.compile(r"type\s+(" + _IDENT + r")(?:\[[^\]]*\])?\s+struct\b")
_GO_TYPE_INTERFACE = re.compile(
    r"type\s+(" + _IDENT + r")(?:\[[^\]]*\])?\s+interface\b"
)
_GO_TYPE_ALIAS_EQ = re.compile(r"type\s+(" + _IDENT + r")(?:\[[^\]]*\])?\s*=")
_GO_TYPE_ALIAS_OTHER = re.compile(r"type\s+(" + _IDENT + r")(?:\[[^\]]*\])?\s+")


# Grouped ``type ( ... )`` declarations: the group header opens a block
# whose lines are type specs without the ``type`` keyword.
_GO_TYPE_GROUP = re.compile(r"^type\s*\(")
_GO_GROUP_STRUCT = re.compile(r"(" + _IDENT + r")(?:\[[^\]]*\])?\s+struct\b")
_GO_GROUP_INTERFACE = re.compile(r"(" + _IDENT + r")(?:\[[^\]]*\])?\s+interface\b")
_GO_GROUP_ALIAS_EQ = re.compile(r"(" + _IDENT + r")(?:\[[^\]]*\])?\s*=")
_GO_GROUP_ALIAS_OTHER = re.compile(r"(" + _IDENT + r")(?:\[[^\]]*\])?\s+")


def extract_symbols_go(source: str) -> set[SymbolTuple]:
    """Top-level funcs, methods (by receiver), structs/interfaces/aliases.

    Mirrors ``go_scanner``: ``type X struct`` → class, ``type X
    interface`` → interface, ``type X = Y`` and every other ``type X
    ...`` form → type_alias (parser boundary: non-struct/interface
    type_specs map to TYPE_ALIAS).  Pointer receivers ``*Store`` and
    generic receivers ``Store[T]`` both yield the bare type name —
    attribution is not compared.  Grouped declarations (``type ( ... )``)
    are handled with the same per-line mapping, mirroring the parser's
    ``type_spec`` handling inside group blocks.
    """
    src = _strip_go(source)
    symbols: set[SymbolTuple] = set()
    in_group = False

    for line in src.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _GO_TYPE_GROUP.match(stripped):
            in_group = True
            continue
        if in_group:
            if stripped == ")":
                in_group = False
                continue
            struct_match = _GO_GROUP_STRUCT.match(stripped)
            if struct_match:
                symbols.add((KIND_CLASS, struct_match.group(1)))
                continue
            interface_match = _GO_GROUP_INTERFACE.match(stripped)
            if interface_match:
                symbols.add((KIND_INTERFACE, interface_match.group(1)))
                continue
            alias_eq = _GO_GROUP_ALIAS_EQ.match(stripped)
            if alias_eq:
                symbols.add((KIND_TYPE_ALIAS, alias_eq.group(1)))
                continue
            alias_other = _GO_GROUP_ALIAS_OTHER.match(stripped)
            if alias_other:
                symbols.add((KIND_TYPE_ALIAS, alias_other.group(1)))
            continue
        method_match = _GO_METHOD.match(stripped)
        if method_match:
            symbols.add((KIND_METHOD, method_match.group(1)))
            continue
        func_match = _GO_FUNC.match(stripped)
        if func_match:
            symbols.add((KIND_FUNCTION, func_match.group(1)))
            continue
        struct_match = _GO_TYPE_STRUCT.match(stripped)
        if struct_match:
            symbols.add((KIND_CLASS, struct_match.group(1)))
            continue
        interface_match = _GO_TYPE_INTERFACE.match(stripped)
        if interface_match:
            symbols.add((KIND_INTERFACE, interface_match.group(1)))
            continue
        alias_eq = _GO_TYPE_ALIAS_EQ.match(stripped)
        if alias_eq:
            symbols.add((KIND_TYPE_ALIAS, alias_eq.group(1)))
            continue
        alias_other = _GO_TYPE_ALIAS_OTHER.match(stripped)
        if alias_other:
            symbols.add((KIND_TYPE_ALIAS, alias_other.group(1)))

    return symbols


# ---------------------------------------------------------------------------
# Symbol extraction — Java (statement walk)
# ---------------------------------------------------------------------------
#
# The parser emits the type declarations directly contained in a type
# body plus their direct methods/constructors, and never enters a method
# body while collecting members.  Consequences the checker mirrors:
# nested types are symbols, but local classes (inside a method) and
# anonymous-class bodies produce none — and neither do their members.
# :func:`_java_structure` classifies each opened ``{`` as a *type* body
# (``class``/``interface``/``enum``/``record``) or a plain ``block``
# (method, initializer, lambda, anonymous/local class, array
# initializer); symbols are only collected while the innermost open body
# is a type body.
#
# Two Java-specific traps the classifier closes:
# ---------------------------------------------------------------------------
# Symbol extraction — Kotlin (structure walk, see ``_kotlin_structure``)
# ---------------------------------------------------------------------------
#
# The parser collects a member only while the innermost open body is a
# *type* body, so a local ``fun`` (inside a method) and an enum-entry body's
# methods produce no symbols, while a nested class's members do (K1/K11).
# A companion object is a type body with no symbol of its own — named or
# not (K3) — and a secondary ``constructor`` is a method named after the
# enclosing type, the Kotlin spelling of Java's constructor rule.
def extract_symbols_kotlin(source: str) -> set[SymbolTuple]:
    """Type declarations and their direct functions/methods/constructors.

    Mirrors ``kotlin_scanner``: ``class``/``data class``/``sealed class``/
    ``value class``/``object`` → class, ``interface``/``fun interface``/
    ``annotation class`` → interface, ``enum class`` → enum, ``typealias``
    → type_alias, a top-level ``fun`` → function and a type-body
    ``fun``/``constructor`` → method.
    """
    src = _strip_kotlin(source)
    symbols: set[SymbolTuple] = set()
    for ev in _kotlin_structure(src, source):
        if ev.symbol_kind is not None and ev.name:
            symbols.add((ev.symbol_kind, ev.name))
    return symbols


def extract_symbols_java(source: str) -> set[SymbolTuple]:
    """Type declarations and their direct methods/constructors.

    Mirrors ``java_scanner``: ``class_declaration``/``record_declaration``
    → class, ``interface_declaration``/``annotation_type_declaration``
    (``@interface``) → interface, ``enum_declaration`` → enum, and
    ``method_declaration``/``constructor_declaration``/
    ``compact_constructor_declaration`` → method.  All of that — nesting,
    the compact constructor and the enum-constant-with-body trap — is
    resolved by :func:`_java_structure`, so this is a pure consumer.
    """
    symbols: set[SymbolTuple] = set()
    for ev in _java_structure(_strip_java(source)):
        if ev.symbol_kind is not None and ev.name is not None:
            symbols.add((ev.symbol_kind, ev.name))
    return symbols


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_SYMBOL_EXTRACTORS: dict[str, object] = {
    "python": extract_symbols_python,
    "javascript": extract_symbols_javascript,
    "typescript": extract_symbols_typescript,
    "rust": extract_symbols_rust,
    "go": extract_symbols_go,
    "java": extract_symbols_java,
    "kotlin": extract_symbols_kotlin,
}


def extract_symbols(lang: str, source: str) -> set[SymbolTuple]:
    """Return the checker's ``(kind, name)`` set for *source*."""
    if lang not in _SYMBOL_EXTRACTORS:
        raise ValueError(f"unknown language: {lang!r}")
    return _SYMBOL_EXTRACTORS[lang](source)  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Parser side — run the REAL production pipeline on a corpus directory
# ---------------------------------------------------------------------------

# SymbolType name → checker kind.
_SYMBOL_KIND: dict[str, str] = {
    "FUNCTION": KIND_FUNCTION,
    "METHOD": KIND_METHOD,
    "CLASS": KIND_CLASS,
    "INTERFACE": KIND_INTERFACE,
    "ENUM": KIND_ENUM,
    "TYPE_ALIAS": KIND_TYPE_ALIAS,
}


def parse_corpus(
    lang: str,
    corpus_dir: Path,
) -> tuple[dict[Path, set[SymbolTuple]], dict[Path, set[str]]]:
    """Run the production scanners over *corpus_dir*.

    Exercises the real path end-to-end (``RepositoryScanner.scan`` →
    ``build_symbol_index`` → ``ChangeDetector._extract_calls``) and
    returns per-file symbol and called-name sets keyed by path relative
    to the corpus dir.

    Raises ``AssertionError`` when any corpus file fails to parse — a
    corpus file that does not parse defeats the audit.
    """
    from nowreck.detector.change_detector import ChangeDetector
    from nowreck.scanner.repository_scanner import RepositoryScanner
    from nowreck.scanner.symbol_index import build_symbol_index

    scan = RepositoryScanner(corpus_dir, use_cache=False).scan()
    assert scan.failure_count == 0, f"corpus parse failures: {scan.failed_files}"

    index = build_symbol_index(scan)
    symbols_by_file: dict[Path, set[SymbolTuple]] = {}
    for sym in index.all_symbols:
        kind = _SYMBOL_KIND[sym.symbol_type.name]
        symbols_by_file.setdefault(sym.file_path, set()).add((kind, sym.name))

    calls_by_file: dict[Path, set[str]] = {}
    for evidence in ChangeDetector._extract_calls(scan):
        calls_by_file.setdefault(evidence.file_path, set()).add(
            evidence.called_name,
        )

    return symbols_by_file, calls_by_file
