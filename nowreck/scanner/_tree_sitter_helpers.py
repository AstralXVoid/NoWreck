from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from tree_sitter import Node

from nowreck.scanner.symbol_index import Symbol, SymbolType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Generic tree-sitter helpers (language-agnostic)
# ---------------------------------------------------------------------------

# Leaf node types whose text is part of the structural hash only after
# quote-style normalisation: ``"x"`` and ``'x'`` must hash identically.
# Union across grammars; a type absent from a grammar never matches.
STRING_NODE_TYPES: frozenset[str] = frozenset(
    {
        "string",
        "string_literal",
        "raw_string_literal",
        "char_literal",
        "interpreted_string_literal",
        "rune_literal",
        "template_string",
    }
)

# Comment nodes never affect the structural hash (grammar-specific names).
COMMENT_NODE_TYPES: frozenset[str] = frozenset(
    {
        "comment",
        "line_comment",
        "block_comment",
    }
)

# Semicolon leaves are optional under automatic-semicolon-insertion in
# JS/TS/Go: ``return 1;`` and ``return 1`` are the same program, so the
# leaf must not affect the hash.  Rust's ``;`` is semantic (``{ 1 }``
# returns the value, ``{ 1; }`` returns ``()``) and is deliberately
# never excluded.
ASI_LEAF_EXCLUSIONS: frozenset[str] = frozenset({";"})

# Tokens that may follow a trailing comma in a comma-separated list
# (``[1, 2,]``, ``f(a,)``, ``{x: 1,}``, Rust ``Vec<i32,>``).  A comma is
# hash-invisible only when everything after it is a closer or another
# comma — mid-list commas stay, so elisions (``[1,,2]``) still hash
# differently from ``[1,2]``.
CLOSING_TOKEN_TYPES: frozenset[str] = frozenset({"]", "}", ")", ">"})


def text_of(node: Node, source_bytes: bytes) -> str:
    """Decode the source text spanned by *node*."""
    return source_bytes[node.start_byte : node.end_byte].decode(
        "utf-8",
        errors="replace",
    )


def structural_hash(
    node: Node,
    source_bytes: bytes,
    *,
    excluded_leaf_types: frozenset[str] = frozenset(),
) -> str:
    """Compute a formatting-insensitive structural hash for *node*.

    Serialises the CST: each node's type plus, for leaf tokens, the
    node's trimmed text (quote-style-normalised for string literals).
    Whitespace, comments, semicolons, trailing commas, and brace style
    never affect the result; operators and other tokens do.  This
    mirrors the structure-only semantics of the Python ``ast.dump`` hash
    so that all five languages share one rule: reformatting is never a
    "change", edited logic always is.

    Args:
        node: The CST node to hash.
        source_bytes: Source bytes the tree was parsed from.
        excluded_leaf_types: Leaf token types to omit entirely (e.g.
            ``ASI_LEAF_EXCLUSIONS`` for JS/TS/Go, whose semicolons are
            optional).  Rust passes nothing — its ``;`` is semantic.
    """
    if node.type in COMMENT_NODE_TYPES:
        return ""
    return _serialize_node(
        node,
        source_bytes,
        skip_methods=False,
        excluded_leaf_types=excluded_leaf_types,
    )


def _string_text(node: Node, source_bytes: bytes) -> str:
    """Trimmed, quote-stripped text of a string-literal node.

    JS/TS ``string`` nodes (single or double quotes) are fully unescaped
    so ``"it's"`` and ``'it\'s'`` collide; Rust/Go literals keep their
    escape text (their quote styles are separate node types and raw vs
    interpreted is semantically significant).  Whitespace inside a
    literal is content and is preserved exactly.
    """
    text = _strip_outer_quotes(text_of(node, source_bytes))
    if node.type == "string":
        return _js_unescape(text)
    return text


def _js_unescape(text: str) -> str:
    r"""Decode JavaScript escape sequences inside a quoted string token.

    Handles ``\n``-style escapes, hex/unicode escapes (``\xHH``,
    ``\uHHHH``, ``\u{...}``), legacy octal escapes, escaped quotes and
    backslashes, and line continuations.  Unknown or invalid escapes are
    kept verbatim; surrogate-range ``\u`` escapes are kept as text so
    the hash never carries lone surrogates.
    """
    simple: dict[str, str] = {
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "b": "\b",
        "f": "\f",
        "v": "\v",
    }
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c != "\\" or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        nxt = text[i + 1]
        if nxt in ("'", '"', "\\"):
            out.append(nxt)
            i += 2
            continue
        if nxt in simple:
            out.append(simple[nxt])
            i += 2
            continue
        if nxt == "x":
            hex_str = text[i + 2 : i + 4]
            if len(hex_str) == 2 and all(
                ch in "0123456789abcdefABCDEF" for ch in hex_str
            ):
                out.append(chr(int(hex_str, 16)))
                i += 4
                continue
            out.append(c)  # invalid \x escape: keep verbatim
            i += 1
            continue
        if nxt == "u":
            if i + 2 < n and text[i + 2] == "{":
                close = text.find("}", i + 3)
                if close != -1:
                    hex_str = text[i + 3 : close]
                    if hex_str and all(
                        ch in "0123456789abcdefABCDEF" for ch in hex_str
                    ):
                        cp = int(hex_str, 16)
                        if cp <= 0x10FFFF and not 0xD800 <= cp <= 0xDFFF:
                            out.append(chr(cp))
                            i = close + 1
                            continue
            else:
                hex_str = text[i + 2 : i + 6]
                if len(hex_str) == 4 and all(
                    ch in "0123456789abcdefABCDEF" for ch in hex_str
                ):
                    cp = int(hex_str, 16)
                    if not 0xD800 <= cp <= 0xDFFF:
                        out.append(chr(cp))
                        i += 6
                        continue
            # Invalid or surrogate \u escape: keep the whole escape text.
            out.append(c)
            i += 1
            continue
        if nxt in "01234567":  # legacy octal: up to 3 digits
            j = i + 1
            digits = ""
            while j < n and len(digits) < 3 and text[j] in "01234567":
                digits += text[j]
                j += 1
            out.append(chr(int(digits, 8)))
            i = j
            continue
        if nxt in "89":  # identity escape (\8, \9)
            out.append(nxt)
            i += 2
            continue
        if nxt in "\n\r":  # line continuation
            i += 2
            if nxt == "\r" and i < n and text[i] == "\n":
                i += 1
            continue
        # Unknown escape: keep the backslash; the next char is re-read
        # as a normal character.
        out.append(c)
        i += 1
    return "".join(out)


def _strip_outer_quotes(text: str) -> str:
    """Strip the outermost quote pair of a string-literal token text.

    ``"x"`` and ``'x'`` both become ``x``; a Rust raw string
    ``r"x"`` keeps its ``r`` prefix (the delimiters differ from the
    value, so quote-style normalisation does not apply).
    """
    if len(text) >= 2 and text[0] == text[-1]:
        return text[1:-1]
    return text


def _class_shell_hash(
    class_node: Node,
    source_bytes: bytes,
    *,
    excluded_leaf_types: frozenset[str] = frozenset(),
) -> str:
    """Structural hash of a class *shell only*.

    Serialises the ``class_declaration`` subtree (decorators, name,
    heritage, class body) while excluding every ``method_definition``
    subtree — getter/setter/static/async modifiers live *inside* the
    method subtree and go with it — and, for TypeScript, decorator
    siblings attached to a method.  A method edit therefore never fires
    ``CHANGED_CLASS`` (disjoint-facts rule), at any nesting depth (e.g.
    methods of a class expression stored in a static field).  Class-level
    decorators and class fields remain in the shell.
    """
    parts: list[str] = [class_node.type]
    for child in class_node.children:
        child_hash = _serialize_node(
            child,
            source_bytes,
            skip_methods=True,
            excluded_leaf_types=excluded_leaf_types,
        )
        if child_hash:
            parts.append(child_hash)
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _serialize_node(
    node: Node,
    source_bytes: bytes,
    *,
    skip_methods: bool,
    excluded_leaf_types: frozenset[str] = frozenset(),
) -> str:
    """Core CST serialisation shared by ``structural_hash`` and the class
    shell walk.

    With *skip_methods* set, ``method_definition`` subtrees and the
    decorator siblings attached to them are omitted (class shell mode);
    otherwise the full structure is hashed.  Leaves in
    *excluded_leaf_types* are omitted entirely, and trailing commas are
    hash-invisible (see ``_is_trailing_comma``).
    """
    if node.type in COMMENT_NODE_TYPES:
        return ""
    if node.type in excluded_leaf_types:
        return ""
    if skip_methods and node.type == "method_definition":
        return ""
    parts: list[str] = [node.type]
    if node.type in STRING_NODE_TYPES and node.type != "template_string":
        # JS/TS ``string`` nodes carry quote/escape-sequence children;
        # Rust/Go string literals are single leaf tokens.  Either way,
        # hash the quote-stripped text so ``"x"`` and ``'x'`` are equal
        # (JS/TS also unescape, so embedded-quote styles collide too).
        # Template strings are excluded: interpolated ones must recurse
        # so ``${expr}`` edits affect the hash.
        parts.append(_string_text(node, source_bytes))
    elif node.child_count == 0:
        parts.append(" ".join(text_of(node, source_bytes).split()))
    else:
        children = node.children
        for i, child in enumerate(children):
            if (
                skip_methods
                and child.type == "decorator"
                and _is_method_decorator(
                    children,
                    i,
                )
            ):
                continue
            if child.type == "," and _is_trailing_comma(children, i):
                continue
            child_hash = _serialize_node(
                child,
                source_bytes,
                skip_methods=skip_methods,
                excluded_leaf_types=excluded_leaf_types,
            )
            if child_hash:
                parts.append(child_hash)
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _is_trailing_comma(children: list[Node], index: int) -> bool:
    """Whether the comma at *index* is a trailing separator.

    A comma is trailing when every following sibling (ignoring comments
    and other commas) is a closing token — ``[1, 2,]``, ``f(a,)``,
    ``{x: 1,}``, Rust ``Vec<i32,>``.  Mid-list commas are kept, so
    elisions (``[1,,2]``) and separators still affect the hash.
    """
    for sibling in children[index + 1 :]:
        if sibling.type in COMMENT_NODE_TYPES or sibling.type == ",":
            continue
        return sibling.type in CLOSING_TOKEN_TYPES
    return False


def _is_method_decorator(children: list[Node], index: int) -> bool:
    """Whether the decorator at *index* decorates a sibling method.

    The TypeScript grammar attaches method decorators as siblings
    *before* the ``method_definition`` in the class body.  A run of
    decorators directly followed by a ``method_definition`` is excluded
    from the class shell so method-decorator edits never fire
    ``CHANGED_CLASS`` (Accepted Edges #1).
    """
    j = index + 1
    while j < len(children) and children[j].type == "decorator":
        j += 1
    return j < len(children) and children[j].type == "method_definition"


def unwrap_parens(node: Node) -> Node | None:
    """Unwrap a chain of parenthesized expressions to reach the inner node.

    ``((() => {}))`` → after unwrapping → ``() => {}`` (arrow_function)
    Returns ``None`` when the chain is empty (named_child_count == 0).

    Uses ``named_child(0)`` (not ``child(0)``) to skip syntactic tokens
    like ``(`` and ``)`` and reach the actual expression inside the parens.
    """
    inner: Node | None = node
    while (
        inner is not None
        and inner.type == "parenthesized_expression"
        and inner.named_child_count > 0
    ):
        inner = inner.named_child(0)
    return inner


def is_iife(node: Node) -> bool:
    """Check whether *node* is a ``call_expression`` whose callee is a
    ``function_expression``, ``arrow_function``, or ``generator_function``
    (possibly wrapped in ``parenthesized_expression``).

    Returns ``False`` for ordinary function calls like ``foo()`` where
    the callee is an ``identifier`` or ``member_expression``.
    """
    if node.type == "call_expression":
        func_node = node.child_by_field_name("function")
        if func_node is not None:
            inner = unwrap_parens(func_node)
            if inner is not None and inner.type in (
                "function_expression",
                "arrow_function",
                "generator_function",
            ):
                return True
    # ``void function() { ... }()`` — void wraps a call_expression.
    if node.type == "unary_expression" and node.named_child_count > 0:
        operand = node.named_child(0)
        if operand is not None and operand.type == "call_expression":
            return is_iife(operand)
    return False


# ---------------------------------------------------------------------------
# Symbol collection (language-agnostic — node types are identical between
# JavaScript and TypeScript tree-sitter grammars for all in-scope patterns)
# ---------------------------------------------------------------------------


def collect_top_level_symbols(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> list[Symbol]:
    """Walk top-level statements and collect symbols.

    Handles:
        - ``function foo() {}``  →  SymbolType.FUNCTION
        - ``const foo = () => {}``  →  SymbolType.FUNCTION
        - ``class Foo { ... }``  →  SymbolType.CLASS  (+ methods)
        - ``interface Foo { ... }``  →  SymbolType.INTERFACE
        - ``enum Color { ... }``  →  SymbolType.ENUM
        - ``type T = ...``  →  SymbolType.TYPE_ALIAS
        - ``export function foo() {}``  →  (unwrapped, same as above)
        - ``export class Foo {}``  →  (unwrapped, same as above)
        - ``export const foo = () => {}``  →  (unwrapped, same as above)

    The interface/enum/type-alias node types only ever occur in the
    TypeScript and TSX grammars, so JavaScript scanning behaviour is
    untouched by construction.  Members (interface method signatures,
    enum members, generic parameters) are structural detail and are
    intentionally NOT captured — same one-level-deep philosophy as class
    methods.
    """
    symbols: list[Symbol] = []

    for child in root_node.children:
        # Unwrap export_statement: drill into the ``declaration`` field so
        # that ``export function foo() {}`` produces a FUNCTION symbol.
        node = child
        if node.type == "export_statement":
            declaration_child = node.child_by_field_name("declaration")
            if declaration_child is not None:
                node = declaration_child

        if node.type in ("function_declaration", "generator_function_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(
                    Symbol(
                        name=text_of(name_node, source_bytes),
                        symbol_type=SymbolType.FUNCTION,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        body_hash=structural_hash(
                            node,
                            source_bytes,
                            excluded_leaf_types=ASI_LEAF_EXCLUSIONS,
                        ),
                    )
                )

        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                class_name = text_of(name_node, source_bytes)
                class_line = node.start_point[0] + 1
                symbols.append(
                    Symbol(
                        name=class_name,
                        symbol_type=SymbolType.CLASS,
                        file_path=file_path,
                        line_number=class_line,
                        body_hash=_class_shell_hash(
                            node,
                            source_bytes,
                            excluded_leaf_types=ASI_LEAF_EXCLUSIONS,
                        ),
                    )
                )
                collect_class_methods(
                    node,
                    source_bytes,
                    file_path,
                    class_name,
                    symbols,
                )

        elif node.type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(
                    Symbol(
                        name=text_of(name_node, source_bytes),
                        symbol_type=SymbolType.INTERFACE,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                    )
                )

        elif node.type == "enum_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(
                    Symbol(
                        name=text_of(name_node, source_bytes),
                        symbol_type=SymbolType.ENUM,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                    )
                )

        elif node.type == "type_alias_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(
                    Symbol(
                        name=text_of(name_node, source_bytes),
                        symbol_type=SymbolType.TYPE_ALIAS,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                    )
                )

        elif node.type == "expression_statement":
            # Standalone IIFE: ``(function() { ... })()``
            if node.named_child_count > 0:
                expr = node.named_child(0)
                if expr is not None and is_iife(expr):
                    logger.debug(
                        "Skipping top-level IIFE at line %d", node.start_point[0] + 1
                    )
                    continue

        elif node.type in ("lexical_declaration", "variable_declaration"):
            # const foo = () => {}  or  var foo = () => {}
            for declarator in node.children:
                if declarator.type == "variable_declarator":
                    maybe_arrow_function_declarator(
                        declarator,
                        source_bytes,
                        file_path,
                        symbols,
                    )

    return symbols


def collect_class_methods(
    class_node: Node,
    source_bytes: bytes,
    file_path: Path,
    class_name: str,
    symbols: list[Symbol],
) -> None:
    """Index ``method_definition`` nodes inside a class body."""
    body_node = class_node.child_by_field_name("body")
    if body_node is None:
        return

    for member in body_node.children:
        if member.type == "method_definition":
            name_node = member.child_by_field_name("name")
            if name_node is not None:
                symbols.append(
                    Symbol(
                        name=text_of(name_node, source_bytes),
                        symbol_type=SymbolType.METHOD,
                        file_path=file_path,
                        line_number=member.start_point[0] + 1,
                        parent_class=class_name,
                        body_hash=structural_hash(
                            member,
                            source_bytes,
                            excluded_leaf_types=ASI_LEAF_EXCLUSIONS,
                        ),
                    )
                )


def maybe_arrow_function_declarator(
    declarator_node: Node,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
) -> None:
    """If a variable declarator's value is an arrow function or generator
    expression, emit a Symbol.

    IIFEs (e.g. ``const x = (function() { ... })()``) are explicitly
    skipped rather than falling through silently.
    """
    name_node = declarator_node.child_by_field_name("name")
    value_node = declarator_node.child_by_field_name("value")
    if name_node is None or value_node is None:
        return

    if is_iife(value_node):
        logger.debug(
            "Skipping IIFE assignment to %s at line %d",
            text_of(name_node, source_bytes),
            value_node.start_point[0] + 1,
        )
        return

    inner = unwrap_parens(value_node)

    if inner is not None and inner.type in (
        "arrow_function",
        "generator_function",
    ):
        symbols.append(
            Symbol(
                name=text_of(name_node, source_bytes),
                symbol_type=SymbolType.FUNCTION,
                file_path=file_path,
                line_number=inner.start_point[0] + 1,
                body_hash=structural_hash(
                    inner,
                    source_bytes,
                    excluded_leaf_types=ASI_LEAF_EXCLUSIONS,
                ),
            )
        )


# ---------------------------------------------------------------------------
# Call detection helpers (language-agnostic)
# ---------------------------------------------------------------------------


def collect_tree_sitter_callers(
    node: Node,
    source_bytes: bytes,
    result: list[tuple[str, Node]],
) -> None:
    """Recursively collect every ``function_declaration``,
    ``method_definition``, and named ``arrow_function`` / ``function_expression``
    assignee in the tree.

    Each entry is ``(caller_name, function_node)`` where *function_node* is
    the CST node whose body should be searched for ``call_expression``
    children.
    """
    if node.type in ("function_declaration", "generator_function_declaration"):
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            result.append((text_of(name_node, source_bytes), node))

    elif node.type == "method_definition":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            result.append((text_of(name_node, source_bytes), node))

    elif node.type == "variable_declarator":
        value_node = node.child_by_field_name("value")
        if value_node is not None:
            inner = unwrap_parens(value_node)
            if inner is not None and inner.type in (
                "arrow_function",
                "function_expression",
                "generator_function",
            ):
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    result.append(
                        (
                            text_of(name_node, source_bytes),
                            inner,
                        )
                    )

    # Recurse into children to find nested functions
    for child in node.named_children:
        collect_tree_sitter_callers(child, source_bytes, result)


def find_tree_sitter_calls_in_body(
    node: Node,
    caller_name: str,
    root_func_node: Node,
    source_bytes: bytes,
    file_path: Path,
    calls: set[tuple[Path, str, str]],
) -> None:
    """Walk *node* finding ``call_expression`` children whose function
    target is a simple ``identifier`` (e.g. ``foo()`` — not
    ``obj.method()``).

    Skips nested function-like nodes that are not *root_func_node* so
    their calls are not misattributed to the outer function.
    """
    for child in node.named_children:
        # Skip nested function-like nodes — they have their own entry
        if child is not root_func_node:
            if child.type in (
                "function_declaration",
                "generator_function_declaration",
                "method_definition",
                "arrow_function",
                "function_expression",
                "generator_function",
            ):
                continue
            # Skip const foo = () => {} inside a function body
            if child.type == "variable_declarator":
                value_node = child.child_by_field_name("value")
                if value_node is not None:
                    inner = unwrap_parens(value_node)
                    if inner is not None and inner.type in (
                        "arrow_function",
                        "function_expression",
                        "generator_function",
                    ):
                        continue

        if child.type == "call_expression":
            func_node = child.child_by_field_name("function")
            if func_node is not None and func_node.type == "identifier":
                called_name = text_of(func_node, source_bytes)
                calls.add((file_path, caller_name, called_name))

        find_tree_sitter_calls_in_body(
            child,
            caller_name,
            root_func_node,
            source_bytes,
            file_path,
            calls,
        )


def extract_tree_sitter_calls_from_tree(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> set[tuple[Path, str, str]]:
    """Extract all ``(file_path, caller_name, called_name)`` tuples from
    a parsed tree-sitter CST.

    1. Finds every function-like node (the *callers*).
    2. For each caller, walks its body looking for ``call_expression``
       nodes whose target is a simple ``identifier``.
    """
    calls: set[tuple[Path, str, str]] = set()
    function_nodes: list[tuple[str, Node]] = []

    collect_tree_sitter_callers(root_node, source_bytes, function_nodes)

    for caller_name, func_node in function_nodes:
        find_tree_sitter_calls_in_body(
            func_node,
            caller_name,
            root_func_node=func_node,
            source_bytes=source_bytes,
            file_path=file_path,
            calls=calls,
        )

    return calls
