"""C++ scanner — symbol and call extraction via ``tree-sitter-cpp``.

Phase 5 of v0.17.0.  The grammar (``tree-sitter-cpp 0.23.4``, ABI 14, on
``tree-sitter 0.26.0``) exposes a single ``language()`` covering the whole
C++ grammar.  That grammar **also** parses C, and the ``.h`` extension is
in the discovery list, so a C header in a mixed repository is parsed as
C++ — an accepted edge (documented for Phase 7); ``.c`` files are never
discovered.

Every grammar shape this file depends on was resolved empirically
**before** any collector code was written and is pinned in
``tests/test_cpp_probes.py`` (probes E1–E14, the E17 type/wrapper probes
and the E18 review set).  The facts that shape the code:

- ``a.b()`` and ``a->b()`` share one ``field_expression`` shape: the
  member name is the ``field`` field and the receiver the ``argument``
  field (E1).  A receiver that is itself a ``call_expression``
  (``f().bar()``) has no static name and is excluded, exactly like
  JS/TS/PHP.
- ``ns::func()`` / ``Class::static()`` / ``::global_fn()`` carry a
  ``qualified_identifier`` in the call's ``function`` field, with a
  recursive ``name`` field (``a::b::c()``) and a ``template_function``
  head for templated targets (E2).
- Operator functions are ``operator_name`` nodes; a reference return type
  wraps the ``function_declarator`` in a ``reference_declarator``, so a
  declarator walk is required (E3).
- Only grammar-exposed call shapes are captured: ``new Foo()`` is a
  ``new_expression`` and ``Foo obj(3)`` an ``init_declarator``, neither
  call-shaped, while ``std::vector<int>(10)`` *is* a ``call_expression``
  (E4).  Forms the grammar does not expose as calls are excluded, never
  guessed.
- ``template <...>`` is a **sibling wrapper** (``template_declaration``)
  around the declaration, so the whole wrapper is hashed — a
  template-parameter edit is visible (E5).
- ``#ifdef`` regions are embedded in the enclosing body, so a conditional
  edit is part of that function's span (E6).
- A type specifier can hide *inside* a declaration node: a tagged
  declaration (``struct Foo { ... } obj;``), a nested type member
  (``struct B { ... };``) and ``typedef struct Foo { ... } FooT;`` wrap
  their ``struct_specifier`` under a ``declaration``/``field_declaration``/
  ``type_definition``, so every such declaration first emits its
  **body-carrying** type children (a bare ``struct Foo x;`` is an
  elaborated-type use, not a definition) (E18).
- ``extern "C"`` has two forms: the ``declaration_list`` body descends like
  a namespace, while the single-declaration form (``extern "C" int f() {}
  ``) puts the declaration itself in ``body`` and is emitted directly —
  walking its children would drop the symbol (E18).
- Declarator wrappers hide names: a ``reference_declarator`` exposes no
  ``declarator`` field (``A& get();`` needs the first named child), and a
  declaration-only conversion operator (``operator bool() const;``) has no
  ``function_declarator`` at all — the ``operator_cast`` *is* the
  declarator (E18).

Symbol model: ``class_specifier``/``struct_specifier``/``union_specifier`` →
CLASS (a union is a class-like type declaration),
``enum_specifier`` → ENUM (both ``enum X`` and ``enum class X``),
``alias_declaration`` (``using X = Y``) and ``type_definition``
(``typedef``) → TYPE_ALIAS, a ``function_definition`` → FUNCTION at
module/namespace scope or METHOD when it sits in a class body or its
declarator is qualified, a declaration-only member → FUNCTION/METHOD with
``body_hash=None`` (E9), a conversion operator (``operator bool()``) →
METHOD named by its type text (``operatorbool``), and a named lambda
assignment (``auto f = [](){};``) → FUNCTION (E12, the JS ``const f = ()
=> {}`` rule).  A *class-field* lambda (``auto on_ready = []() { ... };``)
is the one lambda that is a **caller, never a symbol**: its name is the
preceding ``field_identifier`` and the field itself is class-shell
content — the JS class-field arrow rule (G3) (E18).  ``INTERFACE``
never fires — C++ has no interface keyword (the accepted edge Phase 7
documents, like Go enums).  ``namespace_definition`` and
``linkage_specification`` (both ``extern "C"`` forms) descend — they are
not symbols, like Python modules.  ``friend`` declarations declare a
non-member and yield no symbol; a data field is class-shell content.  A
type declared *inside a function body* is a local: neither it nor its
members are symbols (its calls still get that member as caller), and a
nested type at class scope is a file-level CLASS fact with no
``parent_class`` — the Java nested-class rule.

**Header/impl split (E9).**  A method declared in ``foo.h`` and defined in
``foo.cpp`` is two independent per-file symbols; there is no ``#include``
resolution.  A declaration-only member (no ``compound_statement``) carries
``body_hash=None``, so a ``.cpp`` body edit can never falsify the header
symbol.  The three pinned rows: a header *declaration* edit surfaces as
``CHANGED_CLASS`` on the header's own type (the declaration is shell
content — the method symbol itself is hash-less by design), a ``.cpp``
body edit fires ``CHANGED_FUNCTION`` on the ``.cpp`` symbol, and the
declaration-only header symbol never fires from the ``.cpp`` edit.
``= default`` / ``= delete`` are *definitions* (a ``function_definition``
with no body but a ``default_method_clause``/``delete_method_clause``) and
are hashed normally (E13).

**Out-of-line attribution.**  ``void Widget::draw() {}`` puts a
``qualified_identifier`` in the declarator; its ``scope`` becomes
``parent_class`` and its ``name`` the symbol name.  The grammar cannot
distinguish a class qualifier from a namespace qualifier (both parse as
``namespace_identifier``), so a namespace-qualified definition
(``void app::run() {}``) is attributed to ``app`` — accepted coarseness,
documented.  A ``template_type`` scope (``Box<T>::put``) keeps the head
identifier (``Box``), mirroring the Rust generic-``impl`` rule.

**Overloads (E11).**  Every overload is emitted.  ``Symbol`` identity is
``(name, kind, file, parent_class)``, so same-identity overloads dedupe in
the detector's ADD/REMOVE set-diff and the body-hash pass is last-wins
(deterministic scan order) — an edit fires ``CHANGED_FUNCTION`` only when
the last-iterated overload changed.  That coarseness lives in the
detector, not here, and is pinned in ``tests/test_change_detector.py``.

Hash model: CLASS/ENUM symbols carry a class-*shell* hash with
``function_definition`` subtrees excluded, so a method edit fires
``CHANGED_FUNCTION`` only (the disjoint-facts rule) while a data field,
base-class list, access specifier, nested type or template-parameter list
stays shell content.  TYPE_ALIAS symbols carry no hash (no
``CHANGED_TYPE_ALIAS`` claim type).  C++ semicolons are required syntax
and are hashed as content (E8) — the shared ASI exclusion set is never
forwarded.  Raw strings are their own node type, so a raw↔interpreted swap
stays a change (E7).

Accepted edges (loud, or correct-by-design): the ``.h`` extension also
matches C headers (the C++ grammar parses C); a file the grammar cannot
parse sets ``has_error`` and the family's parse warning fires while
partial symbols are still extracted; function-pointer declarations
(``int (*fp)(int);``) are not functions and yield no symbol; and a
reserved cast/query keyword the grammar models as *call-shaped*
(``static_cast<int>(x)``, ``typeid(x)``, ``noexcept(x)``) is never
captured — a keyword can never name a user function, and an explicit
operator-call syntax (``b.operator bool()``) is a *grammar error*, so a
call subtree carrying a parse error is skipped rather than guessed from
its leftovers (E18).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from tree_sitter import Language, Parser, Tree

from nowreck.scanner._tree_sitter_helpers import (
    class_shell_hash,
    is_dunder_name,
    structural_hash,
    text_of,
)
from nowreck.scanner.call_evidence import CallEvidence
from nowreck.scanner.symbol_index import Symbol, SymbolType

if TYPE_CHECKING:
    from tree_sitter import Node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-process singleton: load the grammar once and reuse it.
# ---------------------------------------------------------------------------

_cpp_language_cache: Language | None = None


def _get_cpp_language() -> Language:
    """Return the C++ tree-sitter language, loading it on first call."""
    global _cpp_language_cache  # noqa: PLW0603
    if _cpp_language_cache is None:
        import tree_sitter_cpp as ts_cpp  # noqa: PLC0415

        _cpp_language_cache = Language(ts_cpp.language())
    return _cpp_language_cache


def _new_parser(language: Language) -> Parser:
    """Create a fresh parser wired to the given grammar."""
    return Parser(language)


# ---------------------------------------------------------------------------
# Grammar vocabulary (resolved by probes E1-E14)
# ---------------------------------------------------------------------------

# Type declarations that become symbols (E17: the ``using`` alias node is
# ``alias_declaration``, *not* ``type_alias_declaration``).  A ``union``
# is a class-like type declaration and is indexed as CLASS too.
_CLASS_KINDS: frozenset[str] = frozenset(
    {"class_specifier", "struct_specifier", "union_specifier"}
)
_ENUM_KINDS: frozenset[str] = frozenset({"enum_specifier"})
_TYPE_ALIAS_KINDS: frozenset[str] = frozenset({"alias_declaration", "type_definition"})
_TYPE_KINDS: frozenset[str] = _CLASS_KINDS | _ENUM_KINDS | _TYPE_ALIAS_KINDS

# The single node type whose subtrees are excluded from a class shell so a
# method edit can never fire ``CHANGED_CLASS`` (E9/E13).  Declaration-only
# members live in ``field_declaration``/``declaration`` nodes that also
# carry data fields, so they stay shell content; their own symbol is
# defensive-``None`` and never fires ``CHANGED_FUNCTION``.
_METHOD_NODE_TYPES: frozenset[str] = frozenset({"function_definition"})

# Module-scope wrappers that are not symbols (like Python modules).  A
# ``namespace`` body and an ``extern "C"`` block both hold top-level
# declarations in a ``declaration_list``.
_MODULE_WRAPPERS: frozenset[str] = frozenset(
    {"namespace_definition", "linkage_specification"}
)

# Preprocessor region nodes: their inner declarations share the enclosing
# scope (E6), so the walk descends without changing the class context.
_PREPROC_KINDS: frozenset[str] = frozenset(
    {"preproc_ifdef", "preproc_if", "preproc_else", "preproc_elif"}
)

# Reserved keywords the grammar nevertheless exposes as *call-shaped*:
# ``static_cast<int>(x)`` is a ``call_expression`` whose target is a
# ``template_function``, and ``typeid(x)`` / ``noexcept(x)`` one whose
# target is an ``identifier``.  None of them can ever name a user function
# (they are keywords), so they are never captured — the same rule the
# shared call models apply to a cast.
_RESERVED_CALL_KEYWORDS: frozenset[str] = frozenset(
    {
        "static_cast",
        "dynamic_cast",
        "const_cast",
        "reinterpret_cast",
        "typeid",
        "noexcept",
    }
)

# Node types that can carry a declaration's name, either directly or under
# a declarator chain (E3/E14).  ``operator_cast`` is a conversion operator
# (``operator bool``) — the grammar models it apart from ``operator_name``
# (E18) because the declarator is a *type*, not an operator token.
_NAME_NODE_TYPES: frozenset[str] = frozenset(
    {
        "identifier",
        "field_identifier",
        "qualified_identifier",
        "destructor_name",
        "operator_name",
        "operator_cast",
    }
)

# Wrappers outside a ``function_declarator`` whose ``declarator`` field
# leads back to it (``int* add(int)`` → pointer_declarator →
# function_declarator) — E3.
_OUTER_DECLARATOR_WRAPPERS: frozenset[str] = frozenset(
    {"pointer_declarator", "reference_declarator", "parenthesized_declarator"}
)

# Every declarator wrapper walked when resolving a name (E3/E14).
# ``array_declarator`` carries the name of a ``typedef``'d array
# (``typedef int Table[4];`` → ``Table``).
_DECLARATOR_WRAPPERS: frozenset[str] = _OUTER_DECLARATOR_WRAPPERS | frozenset(
    {"function_declarator", "init_declarator", "array_declarator"}
)


# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------


def _collapse_operator_name(text: str) -> str:
    """Normalise an operator/destructor name by removing whitespace.

    The grammar spells an operator declaration with the ``operator``
    keyword and the operator token as separate children, so the source
    text may carry internal spaces (``operator <<``).  Stripping every
    whitespace run makes ``operator<<`` and ``operator <<`` one symbol
    name; ``~Widget`` is unaffected.  The differential checker mirrors
    this rule (see ``tests/helpers/differential.py``).
    """
    return "".join(text.split())


def _resolve_declarator(
    node: Node | None, source_bytes: bytes
) -> tuple[str | None, str | None]:
    """Return ``(name, qualifier)`` for a declarator subtree.

    Walks the declarator chain (pointer/reference/function wrappers) to
    the node that carries the name, handling identifiers,
    ``field_identifier`` members, ``type_identifier`` names (a
    ``typedef``'s declarator, E17), operators and destructors (E3/E14),
    and a ``qualified_identifier`` whose ``scope`` becomes the qualifier
    (the header/impl split).  ``qualifier`` is ``None`` for an unqualified
    declarator.
    """
    if node is None:
        return None, None
    node_type = node.type
    if node_type in ("identifier", "field_identifier", "type_identifier"):
        return text_of(node, source_bytes) or None, None
    if node_type in ("destructor_name", "operator_name"):
        return _collapse_operator_name(text_of(node, source_bytes)) or None, None
    if node_type == "operator_cast":
        # A conversion operator (``operator bool``) is named by its type
        # text alone — the node also carries the parameter list and trailing
        # qualifiers (``operator bool() const``), which are sliced off at the
        # declarator child (E18) and the rest collapsed like any operator.
        end_byte = node.end_byte
        for child in node.children:
            if child.type in ("abstract_function_declarator", "function_declarator"):
                end_byte = child.start_byte
                break
        text = source_bytes[node.start_byte : end_byte].decode("utf-8", "replace")
        return _collapse_operator_name(text) or None, None
    if node_type == "qualified_identifier":
        scope = node.child_by_field_name("scope")
        name_node = node.child_by_field_name("name")
        qualifier = _scope_name(scope, source_bytes)
        name, _ = _resolve_declarator(name_node, source_bytes)
        return name, qualifier
    if node_type == "template_function":
        return _resolve_declarator(node.child_by_field_name("name"), source_bytes)
    if node_type in _DECLARATOR_WRAPPERS:
        inner = node.child_by_field_name("declarator")
        if inner is None:
            inner = _first_declarator_child(node)
        if inner is not None:
            return _resolve_declarator(inner, source_bytes)
        return None, None
    return None, None


def _first_declarator_child(node: Node) -> Node | None:
    """The inner declarator of a wrapper with no ``declarator`` field.

    ``parenthesized_declarator`` (``(*Cb)`` in ``typedef void (*Cb)(int);``)
    holds its inner declarator as an *unnamed* child, so the field lookup
    the other wrappers use returns ``None`` and the walk has to take the
    child itself.
    """
    for child in node.named_children:
        if child.type == "parameter_list":
            continue
        return child
    return None


def _scope_name(node: Node | None, source_bytes: bytes) -> str | None:
    """The qualifier text of a qualified declarator or call target.

    A ``template_type`` scope keeps its head identifier (``Box<T>`` →
    ``Box``, the Rust generic rule); a ``nested_namespace_specifier``
    keeps its last segment; anything else (``namespace_identifier``,
    ``type_identifier``) uses its own text.
    """
    if node is None:
        return None
    if node.type == "template_type":
        head = node.child_by_field_name("name")
        return text_of(head, source_bytes) if head is not None else None
    if node.type == "nested_namespace_specifier":
        segments = [
            child
            for child in node.named_children
            if child.type == "namespace_identifier"
        ]
        if segments:
            return text_of(segments[-1], source_bytes) or None
        return None
    if node.type == "qualified_identifier":
        name_node = node.child_by_field_name("name")
        return text_of(name_node, source_bytes) if name_node is not None else None
    return text_of(node, source_bytes) or None


def _function_declarator_name(
    declarator: Node | None,
    source_bytes: bytes,
) -> tuple[str, str | None] | None:
    """Resolve a *declaration* declarator to a function name, or ``None``.

    Unlike :func:`_resolve_declarator`, this walks **only** the outer
    wrappers (a pointer/reference return type) to reach a
    ``function_declarator``, and requires its ``declarator`` field to be a
    plain name node.  That excludes a function-pointer declaration
    (``int (*fp)(int);``), whose ``function_declarator`` wraps a
    ``parenthesized_declarator`` — it is not a function definition and
    yields no symbol.

    A ``reference_declarator`` does **not** expose its inner declarator
    through a field (E18), so the walk falls back to its first named child;
    without that, every declaration-only member with a reference return
    type (``A& get();``, ``A& operator+=(int);``) is dropped.  A
    declaration-only *conversion operator* (``operator bool() const;``) has
    no ``function_declarator`` at all — the ``operator_cast`` is itself the
    declarator (E18).
    """
    node = declarator
    while node is not None and node.type in _OUTER_DECLARATOR_WRAPPERS:
        inner = node.child_by_field_name("declarator")
        if inner is None:
            inner = _first_declarator_child(node)
        node = inner
    if node is None:
        return None
    if node.type == "operator_cast":
        name, qualifier = _resolve_declarator(node, source_bytes)
        return (name, qualifier) if name is not None else None
    if node.type != "function_declarator":
        return None
    inner = node.child_by_field_name("declarator")
    if inner is None or inner.type not in _NAME_NODE_TYPES:
        return None
    name, qualifier = _resolve_declarator(inner, source_bytes)
    if name is None:
        return None
    return name, qualifier


def _type_name(node: Node, source_bytes: bytes) -> str | None:
    """The declared name of a type node, or ``None`` when anonymous."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    return text_of(name_node, source_bytes) or None


def _named_lambda_name(node: Node, source_bytes: bytes) -> str | None:
    """The *caller* name of a named lambda, or ``None`` (E12).

    A lambda is a symbol only when it is the ``value`` of an
    ``init_declarator`` whose ``declarator`` is a plain identifier
    (``auto f = [](){};``) — the C++ spelling of the JS
    ``const f = () => {}`` rule.  Any other lambda is an unnamed body
    whose calls belong to the nearest enclosing named caller.

    A class-field lambda (``auto f = []() { ... };`` inside a class body)
    is the one shape that is a *caller* but never a symbol: the grammar
    gives the field no ``init_declarator``, so its name is the
    ``field_identifier`` preceding the lambda (E18).  That mirrors the JS
    class-field arrow rule (G3) — calls belong to the field, while the
    field itself is class-shell content.
    """
    parent = node.parent
    if parent is None:
        return None
    if parent.type == "init_declarator":
        declarator = parent.child_by_field_name("declarator")
        if declarator is None or declarator.type not in (
            "identifier",
            "field_identifier",
        ):
            return None
        return text_of(declarator, source_bytes) or None
    if parent.type == "field_declaration":
        previous = node.prev_named_sibling
        if previous is None or previous.type not in ("field_identifier", "identifier"):
            return None
        return text_of(previous, source_bytes) or None
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_cpp_file(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> list[Symbol]:
    """Parse a single C++ file and return the symbols it defines."""
    path = Path(file_path).resolve()
    source_bytes = path.read_bytes()

    language = _get_cpp_language()
    parser = _new_parser(language)
    tree: Tree = parser.parse(source_bytes)
    root = tree.root_node  # type: ignore[attr-defined]

    if root.has_error:
        logger.warning(
            "Syntax error detected in %s — extracting partial symbols",
            path,
        )

    symbol_path = _relative_to(path, repo_root)
    return _collect_cpp_symbols(root, source_bytes, symbol_path)


def scan_cpp_calls(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> set[CallEvidence]:
    """Parse a single C++ file and return all call evidence it contains."""
    path = Path(file_path).resolve()
    source_bytes = path.read_bytes()

    language = _get_cpp_language()
    parser = _new_parser(language)
    tree: Tree = parser.parse(source_bytes)
    root = tree.root_node  # type: ignore[attr-defined]

    rel_path = _relative_to(path, repo_root)
    return _extract_cpp_calls(root, source_bytes, rel_path)


def _relative_to(path: Path, repo_root: str | Path | None) -> Path:
    """Resolve *path* against *repo_root*, falling back to the absolute path."""
    if repo_root is None:
        return path
    try:
        return path.relative_to(Path(repo_root).resolve())
    except ValueError:
        return path


# ---------------------------------------------------------------------------
# Hashes
# ---------------------------------------------------------------------------


def _declaration_hash(node: Node, source_bytes: bytes) -> str:
    """Content hash for one function-like declaration.

    C++ semicolons are required syntax (E8), so no leaf type is excluded
    and no string normaliser is supplied beyond the shared
    ``STRING_NODE_TYPES`` rule (E7).
    """
    return structural_hash(node, source_bytes)


def _type_shell_hash(
    node: Node,
    symbol_type: SymbolType,
    source_bytes: bytes,
) -> str | None:
    """Shell hash for a type declaration, or ``None`` when it has none.

    CLASS/ENUM bodies are class-shell content: data fields, base lists,
    access specifiers, enum cases, nested types and template parameters
    are hashed, while ``function_definition`` subtrees are excluded so a
    method edit can never fire ``CHANGED_CLASS``.  TYPE_ALIAS declarations
    carry no hash — there is no ``CHANGED_TYPE_ALIAS`` claim type.
    """
    if symbol_type in (SymbolType.CLASS, SymbolType.ENUM):
        return class_shell_hash(
            node,
            source_bytes,
            method_node_types=_METHOD_NODE_TYPES,
        )
    return None


# ---------------------------------------------------------------------------
# Symbol collection
# ---------------------------------------------------------------------------


def _collect_cpp_symbols(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> list[Symbol]:
    """Collect symbols from a translation unit."""
    symbols: list[Symbol] = []
    _walk_scope(root_node, source_bytes, file_path, symbols, class_name=None)
    return symbols


def _walk_scope(
    container: Node,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
    *,
    class_name: str | None,
) -> None:
    """Walk one declaration scope, collecting its declarations.

    ``class_name`` is the enclosing type name for a class/enum body and
    ``None`` at module, namespace and ``extern "C"`` scope.  Preprocessor
    regions are descended without changing the scope (E6); a
    ``template_declaration`` is unwrapped so the wrapped declaration is
    the symbol while the whole wrapper supplies the hash (E5).
    """
    for child in container.named_children:
        if child.type in _PREPROC_KINDS:
            _walk_scope(child, source_bytes, file_path, symbols, class_name=class_name)
            continue
        if child.type in _MODULE_WRAPPERS:
            body = child.child_by_field_name("body")
            if body is None:
                continue
            if body.type == "declaration_list":
                _walk_scope(
                    body, source_bytes, file_path, symbols, class_name=class_name
                )
            else:
                # The single-declaration ``extern "C"`` form (``extern "C"
                # int f() { ... }``) puts the declaration itself in the
                # ``body`` field instead of a ``declaration_list`` (E18).
                # Walking its children would visit the declarator and the
                # body as if they were declarations and drop the symbol.
                _emit_declaration(
                    body,
                    hash_node=None,
                    source_bytes=source_bytes,
                    file_path=file_path,
                    symbols=symbols,
                    class_name=class_name,
                )
            continue
        if child.type == "template_declaration":
            wrapped = _wrapped_declaration(child)
            if wrapped is not None:
                _emit_declaration(
                    wrapped,
                    hash_node=child,
                    source_bytes=source_bytes,
                    file_path=file_path,
                    symbols=symbols,
                    class_name=class_name,
                )
            continue
        _emit_declaration(
            child,
            hash_node=None,
            source_bytes=source_bytes,
            file_path=file_path,
            symbols=symbols,
            class_name=class_name,
        )


def _wrapped_declaration(template_declaration: Node) -> Node | None:
    """The declaration wrapped by a ``template_declaration`` (E5)."""
    for child in template_declaration.named_children:
        if child.type == "template_parameter_list":
            continue
        if child.type in (
            _TYPE_KINDS | {"function_definition", "declaration", "field_declaration"}
        ):
            return child
    return None


def _emit_declaration(
    node: Node,
    *,
    hash_node: Node | None,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
    class_name: str | None,
) -> None:
    """Emit the symbol(s) for one declaration node.

    ``hash_node`` is the enclosing ``template_declaration`` when present
    (E5 folding), otherwise ``None`` and *node* itself is hashed.
    """
    if node.type in _CLASS_KINDS:
        _collect_type_declaration(
            node,
            SymbolType.CLASS,
            hash_node=hash_node,
            source_bytes=source_bytes,
            file_path=file_path,
            symbols=symbols,
        )
    elif node.type in _ENUM_KINDS:
        _collect_type_declaration(
            node,
            SymbolType.ENUM,
            hash_node=hash_node,
            source_bytes=source_bytes,
            file_path=file_path,
            symbols=symbols,
        )
    elif node.type in _TYPE_ALIAS_KINDS:
        _collect_nested_type_specifiers(
            node,
            hash_node=hash_node,
            source_bytes=source_bytes,
            file_path=file_path,
            symbols=symbols,
        )
        _collect_type_alias(
            node, source_bytes=source_bytes, file_path=file_path, symbols=symbols
        )
    elif node.type == "function_definition":
        _collect_function_definition(
            node,
            hash_node=hash_node,
            source_bytes=source_bytes,
            file_path=file_path,
            symbols=symbols,
            class_name=class_name,
        )
    elif node.type in ("declaration", "field_declaration"):
        _collect_nested_type_specifiers(
            node,
            hash_node=hash_node,
            source_bytes=source_bytes,
            file_path=file_path,
            symbols=symbols,
        )
        _collect_declaration(
            node,
            source_bytes=source_bytes,
            file_path=file_path,
            symbols=symbols,
            class_name=class_name,
        )


def _collect_nested_type_specifiers(
    node: Node,
    *,
    hash_node: Node | None,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
) -> None:
    """Emit every type *defined* inside a variable/typedef declaration.

    A tagged declaration (``struct Foo { ... } obj;``), a nested type member
    (``struct B { ... };`` in a class body) and a ``typedef struct Foo { ...
    } FooT;`` wrap their ``struct_specifier``/``enum_specifier`` as a child
    of a ``declaration``/``field_declaration``/``type_definition`` rather
    than being the declaration node itself (E18), so the scope walk would
    never reach the type — and would lose its members with it.  Only a
    specifier **with a body** is a symbol: ``struct Foo x;`` names a use of
    an elaborated type, not a definition.

    The type is emitted with no ``parent_class`` (like a Java nested class,
    the type name is a file-level fact); its own members are walked with
    the type as their parent by :func:`_collect_type_declaration`.
    """
    for child in node.named_children:
        if child.type not in _TYPE_KINDS or _type_body(child) is None:
            continue
        _emit_declaration(
            child,
            hash_node=hash_node,
            source_bytes=source_bytes,
            file_path=file_path,
            symbols=symbols,
            class_name=None,
        )


def _collect_type_declaration(
    node: Node,
    symbol_type: SymbolType,
    *,
    hash_node: Node | None,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
) -> None:
    """Emit a class/struct/enum symbol and collect its members."""
    name = _type_name(node, source_bytes)
    if not name:
        return
    hashed = hash_node if hash_node is not None else node
    symbols.append(
        Symbol(
            name=name,
            symbol_type=symbol_type,
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            body_hash=_type_shell_hash(hashed, symbol_type, source_bytes),
        )
    )
    body = _type_body(node)
    if body is not None:
        _walk_scope(body, source_bytes, file_path, symbols, class_name=name)


def _type_body(node: Node) -> Node | None:
    """The body container of a class/struct/enum declaration, or ``None``."""
    return node.child_by_field_name("body")


def _collect_type_alias(
    node: Node,
    *,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
) -> None:
    """Emit a ``TYPE_ALIAS`` symbol for ``using X = Y`` / ``typedef``.

    TYPE_ALIAS symbols carry no hash — there is no ``CHANGED_TYPE_ALIAS``
    claim type, so a signature edit surfaces as ADD/REMOVE only.
    """
    declarator = node.child_by_field_name("declarator")
    name = None
    if node.type == "alias_declaration":
        name = _type_name(node, source_bytes)
        if name is None:
            name, _ = _resolve_declarator(declarator, source_bytes)
    else:
        name, _ = _resolve_declarator(declarator, source_bytes)
    if not name:
        return
    symbols.append(
        Symbol(
            name=name,
            symbol_type=SymbolType.TYPE_ALIAS,
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            body_hash=None,
        )
    )


def _collect_function_definition(
    node: Node,
    *,
    hash_node: Node | None,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
    class_name: str | None,
) -> None:
    """Emit a FUNCTION/METHOD symbol for a definition with a body."""
    name, qualifier = _resolve_declarator(
        node.child_by_field_name("declarator"), source_bytes
    )
    if not name:
        return
    parent = qualifier or class_name
    hashed = hash_node if hash_node is not None else node
    symbols.append(
        Symbol(
            name=name,
            symbol_type=SymbolType.METHOD if parent else SymbolType.FUNCTION,
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            parent_class=parent,
            body_hash=_declaration_hash(hashed, source_bytes),
        )
    )


def _collect_declaration(
    node: Node,
    *,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
    class_name: str | None,
) -> None:
    """Collect declaration-only members (E9) and named lambdas (E12).

    A ``declaration``/``field_declaration`` whose declarator is a function
    declarator is a declaration-only member: it carries
    ``body_hash=None`` so it can never fire ``CHANGED_FUNCTION``.  A
    declaration whose ``init_declarator`` value is a lambda yields a
    FUNCTION symbol named by the declared variable (E12); anything else
    (a data field, a variable) is shell content and yields no symbol.
    """
    declarator = node.child_by_field_name("declarator")
    resolved = _function_declarator_name(declarator, source_bytes)
    if resolved is not None:
        name, qualifier = resolved
        parent = qualifier or class_name
        symbols.append(
            Symbol(
                name=name,
                symbol_type=SymbolType.METHOD if parent else SymbolType.FUNCTION,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                parent_class=parent,
                body_hash=None,
            )
        )
        return
    for child in node.named_children:
        if child.type != "init_declarator":
            continue
        value = child.child_by_field_name("value")
        if value is None or value.type != "lambda_expression":
            continue
        lambda_name = _named_lambda_name(value, source_bytes)
        if not lambda_name:
            continue
        symbols.append(
            Symbol(
                name=lambda_name,
                symbol_type=SymbolType.FUNCTION,
                file_path=file_path,
                line_number=value.start_point[0] + 1,
                body_hash=_declaration_hash(value, source_bytes),
            )
        )


# ---------------------------------------------------------------------------
# Call detection
# ---------------------------------------------------------------------------


def _extract_cpp_calls(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> set[CallEvidence]:
    """Extract all :class:`CallEvidence` objects from a parsed C++ CST."""
    calls: set[CallEvidence] = set()
    callers: list[tuple[str, Node, str | None]] = []

    _collect_cpp_callers(root_node, source_bytes, callers)

    for caller_name, func_node, caller_parent_class in callers:
        _find_cpp_calls_in_body(
            func_node,
            caller_name,
            func_node,
            source_bytes,
            file_path,
            calls,
            caller_parent_class=caller_parent_class,
        )

    return calls


def _collect_cpp_callers(
    node: Node,
    source_bytes: bytes,
    result: list[tuple[str, Node, str | None]],
    class_name: str | None = None,
) -> None:
    """Recursively collect every function-like node that owns calls.

    Each entry is ``(caller_name, function_node, caller_parent_class)``.
    Type declarations set the class attribution for their subtree; an
    out-of-line definition's qualifier wins over the enclosing context.
    A named lambda is a caller (E12) — an unnamed one has no name to
    attribute its calls to, so those calls belong to the nearest enclosing
    named caller.
    """
    for child in node.named_children:
        if child.type in _CLASS_KINDS or child.type in _ENUM_KINDS:
            nested_name = _type_name(child, source_bytes)
            _collect_cpp_callers(child, source_bytes, result, class_name=nested_name)
        elif child.type == "function_definition":
            name, qualifier = _resolve_declarator(
                child.child_by_field_name("declarator"), source_bytes
            )
            if name:
                result.append((name, child, qualifier or class_name))
            _collect_cpp_callers(child, source_bytes, result, class_name=class_name)
        elif child.type == "lambda_expression":
            owner = _named_lambda_name(child, source_bytes)
            if owner:
                result.append((owner, child, class_name))
            _collect_cpp_callers(child, source_bytes, result, class_name=class_name)
        else:
            _collect_cpp_callers(child, source_bytes, result, class_name=class_name)


def _has_own_cpp_caller(node: Node, source_bytes: bytes) -> bool:
    """Whether *node* carries its own caller entry."""
    if node.type == "function_definition":
        return True
    if node.type == "lambda_expression":
        return _named_lambda_name(node, source_bytes) is not None
    return False


def _find_cpp_calls_in_body(
    node: Node,
    caller_name: str,
    root_func_node: Node,
    source_bytes: bytes,
    file_path: Path,
    calls: set[CallEvidence],
    caller_parent_class: str | None = None,
) -> None:
    """Walk *node* finding call nodes.

    Nested callers (methods and named lambdas) carry their own entry, so
    they are skipped — each call is attributed to exactly one caller.
    Unnamed lambdas are deliberately *not* skipped: they have no entry of
    their own, so calls inside them belong to the nearest enclosing named
    caller (the Phase 1 G1/G2 rule).
    """
    for child in node.named_children:
        if child is not root_func_node and _has_own_cpp_caller(child, source_bytes):
            continue

        if child.type == "call_expression":
            called_name = _cpp_called_name(child, source_bytes)
            if called_name is not None:
                calls.add(
                    CallEvidence(
                        file_path=file_path,
                        caller_name=caller_name,
                        called_name=called_name,
                        caller_parent_class=caller_parent_class,
                    )
                )

        _find_cpp_calls_in_body(
            child,
            caller_name,
            root_func_node,
            source_bytes,
            file_path,
            calls,
            caller_parent_class=caller_parent_class,
        )


def _cpp_called_name(node: Node, source_bytes: bytes) -> str | None:
    """Called name of a C++ ``call_expression``, or ``None``.

    Only grammar-exposed call targets yield a name: a bare ``identifier``,
    a ``field_expression`` member (``a.b()``/``a->b()``), a
    ``qualified_identifier`` (``ns::f()``/``Class::static()``) or a
    ``template_function``/``template_method`` head (``f<int>()``,
    ``box.put<int>(v)``).  A receiver that is itself a call
    (``f().bar()``) has no static target and is excluded, matching
    JS/TS/PHP.  A dunder-style final name is never captured (the shared
    rule), and neither is a reserved keyword the grammar happens to expose
    in call position (``static_cast``, ``typeid``, ...) — it can never
    name a user function.  A call whose subtree carries a grammar error is
    skipped rather than guessed at: error recovery would otherwise invent
    a call from the leftover identifier (E18).
    """
    target = node.child_by_field_name("function")
    if target is None or node.has_error or target.has_error:
        return None
    name = _call_target_name(target, source_bytes)
    if name is None or is_dunder_name(name) or name in _RESERVED_CALL_KEYWORDS:
        return None
    return name


def _call_target_name(node: Node, source_bytes: bytes) -> str | None:
    """Final name of a call target node, or ``None`` when there is none."""
    node_type = node.type
    if node_type == "identifier":
        return text_of(node, source_bytes) or None
    if node_type == "field_expression":
        argument = node.child_by_field_name("argument")
        if argument is not None and argument.type == "call_expression":
            return None
        field = node.child_by_field_name("field")
        if field is None:
            return None
        return _final_name(field, source_bytes)
    if node_type == "qualified_identifier":
        return _qualified_final_name(node, source_bytes)
    if node_type in ("template_function", "template_method"):
        return _final_name(node.child_by_field_name("name"), source_bytes)
    return None


def _final_name(node: Node | None, source_bytes: bytes) -> str | None:
    """The static name of a call target's final segment."""
    if node is None:
        return None
    if node.type in ("identifier", "field_identifier"):
        return text_of(node, source_bytes) or None
    if node.type in ("destructor_name", "operator_name"):
        return _collapse_operator_name(text_of(node, source_bytes)) or None
    if node.type == "qualified_identifier":
        return _qualified_final_name(node, source_bytes)
    if node.type in ("template_function", "template_method"):
        return _final_name(node.child_by_field_name("name"), source_bytes)
    return None


def _qualified_final_name(node: Node, source_bytes: bytes) -> str | None:
    """The innermost ``name`` of a ``qualified_identifier`` (E2)."""
    return _final_name(node.child_by_field_name("name"), source_bytes)
