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
from pathlib import Path

# ---------------------------------------------------------------------------
# Language registry
# ---------------------------------------------------------------------------

LANGS = ("python", "javascript", "typescript", "rust", "go")

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


_STRIPPERS = {
    "python": _strip_python,
    "javascript": _strip_javascript,
    "typescript": _strip_typescript,
    "rust": _strip_rust,
    "go": _strip_go,
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


_MASKS: dict[str, object] = {
    "python": _py_call_mask,
    "javascript": _js_call_mask,
    "typescript": _js_call_mask,
    "rust": _rust_call_mask,
    "go": _go_call_mask,
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
    - Rust macro invocations blanked (args are a flat ``token_tree``).
    """
    src = _STRIPPERS[lang](source)
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
            if _receiver_is_call(lines, i, match.start()):
                continue
            # Dunder *attributes* (``obj.__x__()``) are excluded by the
            # parsers; a bare ``__str__()`` call is not.
            if (
                is_dunder_name(name)
                and match.start() >= 1
                and line[match.start() - 1] == "."
            ):
                continue
            # ``new X(...)`` — JS/TS only: ``new_expression`` is not a
            # ``call_expression``, so the parsers never emit the target.
            if lang in ("javascript", "typescript") and re.search(
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
# Dispatch
# ---------------------------------------------------------------------------

_SYMBOL_EXTRACTORS: dict[str, object] = {
    "python": extract_symbols_python,
    "javascript": extract_symbols_javascript,
    "typescript": extract_symbols_typescript,
    "rust": extract_symbols_rust,
    "go": extract_symbols_go,
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
