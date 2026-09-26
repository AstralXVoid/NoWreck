"""Kotlin scanner — symbol and call extraction via ``tree-sitter-kotlin``.

Phase 3 of v0.17.0.  The grammar (``tree-sitter-kotlin 1.1.0``, ABI 14, on
``tree-sitter 0.26.0``) is the only Kotlin grammar published on PyPI, and
it has **seven confirmed misparses** on ordinary source — three loud
(``has_error`` is set) and four silent.  Every one of them was
reproduced deterministically, pinned in ``tests/test_kotlin_probes.py``
(probes K1–K16), and handled here deliberately rather than papered over:

``D1`` **One-line class-like body with a member** (``class A { fun f() {} }``)
    is a parse *error* — the body is mislabelled ``enum_class_body`` and
    the member is swallowed by an ``ERROR`` node, so it is invisible to a
    member walk.  Accepted edge: the multi-line body every Kotlin style
    guide mandates is unaffected, and a newline or ``;`` before the brace
    avoids it entirely.  The class symbol itself is still emitted.

``D2`` **An annotated single-entry enum without a trailing comma**
    (``@Ann(1) enum class E { A }``) loses the whole declaration: it
    becomes ``annotated_expression → infix_expression(enum, class,
    call_expression(E, lambda))``.  Two entries, or a trailing comma,
    parse correctly.  **Recovered** by the blinded re-parse (D7 below).

``D3`` **An annotated ``annotation class``** — the idiomatic
    ``@Target(…) @Retention(…) annotation class X`` — loses the whole
    declaration the same way (``infix_expression(annotation, class, X)``).
    **Recovered** the same way (D7).

``D4`` **A top-level ``fun``/``object``/``enum class`` whose annotation
    has a following sibling** — *including a trailing comment* — gets its
    annotation **detached** into a sibling ``annotated_expression`` whose
    argument list becomes a sibling ``parenthesized_expression``.  The
    declaration survives, but the same source therefore has two different
    CST shapes, so an annotation cannot be hashed by CST shape.  Handled
    by hashing annotations as their normalised **leaf-token signature**
    (:func:`~nowreck.scanner._tree_sitter_helpers.leaf_token_signature`),
    which is grouping-independent — so appending a comment never fires a
    change, and editing an annotation always does.

``D5`` **A ``fun`` named after a type soft keyword** (``fun dynamic()``,
    ``fun suspend()``) loses its name: the grammar accepts the name as a
    modifier, so inside a type body the declaration survives carrying a
    zero-width ``MISSING`` name node, and at top level it becomes an
    ``anonymous_function`` whose first child is an ``ERROR`` holding the
    name.  Both spellings are valid Kotlin, so the name is **recovered**
    (:func:`_declaration_name`) — from the swallowed token the grammar keeps
    as an unnamed child in the type-body form, and from the ``ERROR`` node's
    text in the top-level form — so the symbol and its calls are emitted
    under the right name rather than dropped, and never emitted nameless.
    A ``suspend`` name collapses the file instead (see D6); an extension
    function is unaffected, since the receiver's dot disambiguates.

``D6`` **The same two soft keywords in other identifier positions**
    (``val dynamic = 1``, a bare ``dynamic()`` call, a named argument
    ``f(dynamic = 1)``, a lambda parameter named ``dynamic``) collapse the
    **whole file** into one ``ERROR`` node.  Accepted edge, and a loud one:
    ``has_error`` is set, so the family's parse warning fires.  Only
    ``dynamic``/``suspend`` are affected — ``value``, ``field``, ``get``,
    ``set``, ``by``, ``where``, ``init`` and ``param`` are ordinary
    identifiers to this grammar (probe K12e).

``D7`` **A stack of two or more annotations at top level dissolves the
    declaration it annotates, silently** (``has_error`` stays ``False``):
    a plain ``class``/``interface``/``annotation class`` (also
    ``sealed class`` and ``data object``, though not ``data class``,
    ``value class``, ``enum class``, ``fun interface`` or ``object`` —
    which heads survive is grammar luck) becomes an
    ``annotated_expression`` chain ending in an ``infix_expression`` as
    soon as *any* declaration follows, and a *bodyless* destroyed
    declaration keeps absorbing the following class-like declaration into
    its own chain, so two declarations become one node and both disappear
    (probes K13/K14).  The same "a sibling follows" trigger detaches an
    argument-bearing ``@Ann(1)`` on a top-level ``fun`` into a sibling
    ``annotated_expression``, even when the only follower is a comment
    (probe K15).  **Recovered** by blinding every annotation span and
    re-parsing (:func:`_prepare_source`): the blinded source is ordinary
    undamaged Kotlin, and each annotation is folded into the declaration
    it owns by position, so how the grammar chose to attach it no longer
    matters.  One trap: the ``annotation`` keyword of ``annotation class``
    is itself a *childless* node of type ``annotation`` (probe K16), so
    only nodes that carry children are blinded (:func:`_is_annotation_node`).

Invariant: a symbol name and a caller name are **never empty**.  A
function-like declaration whose name cannot be recovered contributes
nothing at all, and a property whose initialiser is a function literal is
only a caller when it actually has a name — a ``MISSING`` name node
(``text == ""``) is refused in both cases.

Symbol model (K1/K2/K3/K9/K11): ``class``/``data class``/``sealed class``/
``value class`` → ``CLASS``; ``interface`` and ``fun interface`` (a direct
``interface`` token) → ``INTERFACE``; ``enum class`` → ``ENUM``;
``object``/``data object`` → ``CLASS``; ``typealias`` → ``TYPE_ALIAS``
(named by the ``type`` field — this grammar has no ``name`` field for
aliases).  ``annotation class`` → ``INTERFACE``, the same kind Java's
``@interface`` maps to: both declare an annotation type.  A class-body
``fun`` and a ``secondary_constructor`` → ``METHOD`` with
``parent_class``; a top-level ``fun`` (including an extension function,
whose receiver is not a containing class) → ``FUNCTION``.  Local
functions/classes and enum-entry bodies produce no symbols — Java's
established boundary — but they are still callers.

Callers: a named body owns the calls in it.  Besides functions, secondary
constructors (named after the class) and function-valued properties, a
property **accessor** is a caller named after its property — Kotlin's
spelling of the TS ``get value() { … }`` rule.  Unnamed bodies (``init``
blocks, property initialisers, bare lambdas) own nothing: their calls
belong to the nearest enclosing named caller, and at class level there is
no such caller, so they are dropped — exactly as Java's instance
initialisers are (probe K11).

Hash model: ``CLASS``/``ENUM`` carry a class-*shell* hash with
``function_declaration`` and ``secondary_constructor`` excluded, so a
companion- or instance-method edit fires ``CHANGED_FUNCTION`` only
(K3, generalising the v16 disjoint-facts rule).  ``INTERFACE`` and
``TYPE_ALIAS`` carry no hash — the claim taxonomy has no
``CHANGED_INTERFACE``/``CHANGED_TYPE_ALIAS``, matching every other
language.  Kotlin takes the JS/TS/Go ASI exclusion for ``;``: the grammar
already drops optional semicolons and only retains the one that
terminates an enum entry list (K10), where it stays optional whenever the
enum has no members.
"""

from __future__ import annotations

import hashlib
import logging
import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from tree_sitter import Language, Parser, Tree

from nowreck.scanner._tree_sitter_helpers import (
    ASI_LEAF_EXCLUSIONS,
    COMMENT_NODE_TYPES,
    METHOD_NODE_TYPES,
    class_shell_hash,
    is_dunder_name,
    leaf_token_signature,
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

_kotlin_language_cache: Language | None = None


def _get_kotlin_language() -> Language:
    """Return the Kotlin tree-sitter language, loading it on first call."""
    global _kotlin_language_cache  # noqa: PLW0603
    if _kotlin_language_cache is None:
        import tree_sitter_kotlin as ts_kotlin  # noqa: PLC0415

        _kotlin_language_cache = Language(ts_kotlin.language())
    return _kotlin_language_cache


def _new_parser(language: Language) -> Parser:
    """Create a fresh parser wired to the given grammar."""
    return Parser(language)


# ---------------------------------------------------------------------------
# Grammar vocabulary (resolved by probes K1-K12)
# ---------------------------------------------------------------------------

# Type declarations that become symbols.  ``class_declaration`` covers
# ``class``/``data class``/``sealed class``/``value class``/``interface``/
# ``fun interface``/``enum class``/``annotation class`` — the keyword is
# either a direct token (``interface``) or a ``class_modifier`` — so the
# kind is decided by :func:`_class_kind`, not by node type.
_TYPE_DECL_KINDS: frozenset[str] = frozenset(
    {"class_declaration", "object_declaration"}
)

# Bodies that hold a type's members.  Kotlin has no ``body`` *field*
# (probe K2/K3) — the body is found by node type.
_TYPE_BODY_CONTAINERS: frozenset[str] = frozenset({"class_body", "enum_class_body"})

# Callables inside a type body: an ordinary method, and a secondary
# constructor (which carries no name of its own — it is named after the
# enclosing class, exactly like a Java ``constructor_declaration``).
_METHOD_DECL_TYPES: frozenset[str] = frozenset(
    {"function_declaration", "secondary_constructor"}
)

# Method-like nodes a class *shell* must skip so a method edit never fires
# ``CHANGED_CLASS`` (disjoint-facts rule).  Kotlin adds its own method
# forms to the shared set; the default set still governs JS/TS/Java.
_KOTLIN_METHOD_NODE_TYPES: frozenset[str] = METHOD_NODE_TYPES | _METHOD_DECL_TYPES

# Property values that make the property itself a caller (probe K6 —
# the Kotlin spelling of the JS/TS ``const f = () => {}`` rule).
_FUNCTION_VALUE_TYPES: frozenset[str] = frozenset(
    {"lambda_literal", "anonymous_function"}
)

# Property accessors (probe K11).  Each is a *named* body — the Kotlin
# spelling of the TS accessor rule — so it owns the calls in it.
_PROPERTY_ACCESSOR_TYPES: frozenset[str] = frozenset({"getter", "setter"})

# ``object : Runnable { ... }`` — an anonymous type expression (K11).
_OBJECT_LITERAL = "object_literal"

# Containers whose direct children are declarations.  An
# ``anonymous_function`` seen directly inside one is therefore a D5 mangle,
# never a function *value* (a value always sits inside a
# ``property_declaration``).
_STATEMENT_CONTAINERS: frozenset[str] = frozenset(
    {"source_file", "class_body", "enum_class_body"}
)


# ---------------------------------------------------------------------------
# D5 recovery — a ``fun`` name the grammar consumed as a modifier
# ---------------------------------------------------------------------------

# ``dynamic`` and ``suspend`` are *soft* keywords, so ``fun dynamic()`` is
# valid Kotlin and the grammar accepts the name as a type modifier: inside a
# type body the declaration survives carrying a zero-width ``MISSING`` name
# node, while at top level it becomes an ``anonymous_function`` whose first
# child is an ``ERROR`` holding the name.  The name is read back from the
# bytes in both spellings, because an unnamed symbol — or worse, an unnamed
# *caller* — would be a silent lie about the source.
_SIMPLE_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _name_before_missing(
    node: Node,
    missing: Node,
    source_bytes: bytes,
) -> str | None:
    """The token the grammar swallowed where the ``MISSING`` name sits (D5).

    The grammar keeps the token it consumed as an *unnamed* child of the same
    declaration — ``fun dynamic()`` serialises as the ``fun`` token, the
    ``dynamic`` token, then a zero-width ``MISSING identifier`` — so the name
    is the nearest preceding child that touches the gap.  Only whitespace may
    sit between them, and only the ``fun`` keyword is refused: it is the one
    token that can legitimately precede a missing name in malformed source,
    and it is never a function's name.
    """
    for candidate in reversed(node.children):
        if candidate.is_missing or candidate.end_byte > missing.start_byte:
            continue
        if source_bytes[candidate.end_byte : missing.start_byte].strip():
            return None
        text = text_of(candidate, source_bytes)
        if candidate.type == "fun" or not _SIMPLE_IDENTIFIER.match(text):
            return None
        return text
    return None


def _name_from_error(node: Node, source_bytes: bytes) -> str | None:
    """The name an ``ERROR`` child carries (D5, top-level form).

    The top-level mangle serialises as
    ``anonymous_function (ERROR <name>) (function_value_parameters) …``, so
    the name survives as the ``ERROR`` node's text.  Anything that is not a
    simple identifier — most importantly the empty text of an ``ERROR``
    spanning a whole malformed file — is refused rather than guessed at.
    """
    if node.named_child_count == 0:
        return None
    first = node.named_children[0]
    if first.type != "ERROR":
        return None
    name = text_of(first, source_bytes)
    return name if _SIMPLE_IDENTIFIER.match(name) else None


def _declaration_name(node: Node, source_bytes: bytes) -> str | None:
    """Name of a function-like declaration, recovering a stripped one (D5).

    Returns ``None`` when no name exists or can be recovered.  Every caller
    then emits nothing at all: a symbol or a caller with an empty name would
    enter the index as a phantom entry, so it is never produced.
    """
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        name = text_of(name_node, source_bytes)
        if name:
            return name
        if name_node.is_missing:
            return _name_before_missing(node, name_node, source_bytes)
        return None
    if node.type == "anonymous_function":
        return _name_from_error(node, source_bytes)
    return None


# ---------------------------------------------------------------------------
# D7 recovery — annotations are blanked before the real parse
# ---------------------------------------------------------------------------

# The grammar's annotation handling is *shape-dependent*, silently so
# (probes K13–K16).  One annotation stays inside the declaration it
# annotates; two or more destroy a plain ``class``/``interface``/
# ``annotation class`` into an ``infix_expression`` as soon as any sibling
# follows; a ``fun`` whose annotation has arguments loses the annotation to
# a sibling; and a *bodyless* destroyed declaration keeps absorbing the
# following declarations into its chain.  ``has_error`` stays ``False`` in
# every one of those shapes, so shape-by-shape recovery would keep growing
# with the grammar and would still miss the next variant.
#
# Instead the source is **blinded**: every annotation's bytes are replaced
# by spaces — newlines are kept, so every offset and line number survives —
# and the file is parsed again.  The blinded parse is a parse of ordinary,
# undamaged Kotlin, and each annotation is folded back into the declaration
# it belongs to as its canonical leaf-token signature (:func:`_annotation_
# signature`), which is exactly the signature the attached spelling
# produces.  Attachment therefore stops being a parsing accident and
# becomes a lookup.


def _is_annotation_node(node: Node) -> bool:
    """Whether *node* is a real annotation (``@Ann``).

    The ``annotation`` keyword of ``annotation class`` parses as a node of
    type ``annotation`` too, as a childless leaf under ``class_modifier``;
    a real annotation always carries its ``@`` token, so a childless node
    is a keyword, never an annotation.
    """
    return node.type == "annotation" and node.child_count > 0


def _annotation_layer(node: Node) -> tuple[list[Node], list[Node]]:
    """The annotation units and payloads of one ``annotated_expression``.

    Units are the ``annotation`` children plus, in the detached spelling,
    the ``parenthesized_expression`` holding the annotation's arguments
    (the grammar keeps those outside the ``annotation`` node when it
    detaches the unit).  Payloads are everything else — the damaged or
    intact declaration the layer was wrapped around.
    """
    units: list[Node] = []
    payloads: list[Node] = []
    for child in node.named_children:
        if _is_annotation_node(child):
            units.append(child)
        elif child.type == "annotated_expression":
            payloads.append(child)
        elif child.type == "parenthesized_expression" and units:
            units.append(child)
        else:
            payloads.append(child)
    return units, payloads


def _annotation_chain(
    node: Node,
) -> tuple[tuple[int, int, list[Node]] | None, list[Node]]:
    """Annotation-only span of an ``annotated_expression`` chain, and payloads.

    A stack of annotations serialises as nested ``annotated_expression``
    layers.  The returned span covers the annotation text only — never the
    payload, which may be an entire declaration — so blinding it removes
    the annotations and leaves the declaration's own bytes untouched.
    """
    units: list[Node] = []
    payloads: list[Node] = []
    cursor: Node | None = node
    end = node.start_byte
    while cursor is not None and cursor.type == "annotated_expression":
        layer_units, payloads = _annotation_layer(cursor)
        if not layer_units:
            break
        units.extend(layer_units)
        end = max(end, max(unit.end_byte for unit in layer_units))
        cursor = payloads[0] if len(payloads) == 1 else None
    if not units:
        return None, payloads
    start = min(unit.start_byte for unit in units)
    return (start, end, units), payloads


def _annotation_runs(root: Node) -> list[tuple[int, int, list[Node]]]:
    """Every annotation in *root* as an annotation-only span.

    Both spellings are collected: a detached ``annotated_expression`` chain
    becomes one run (arguments included), and an attached ``annotation``
    node — inside ``modifiers``, ``parameter_modifiers``, type arguments,
    everywhere — becomes a run of its own.
    """
    runs: list[tuple[int, int, list[Node]]] = []

    def walk(node: Node) -> None:
        if node.type == "annotated_expression":
            run, payloads = _annotation_chain(node)
            if run is not None:
                runs.append(run)
            for payload in payloads:
                walk(payload)
            return
        if _is_annotation_node(node):
            runs.append((node.start_byte, node.end_byte, [node]))
            return
        for child in node.children:
            walk(child)

    walk(root)
    return runs


def _blind_source(
    source_bytes: bytes,
    runs: list[tuple[int, int, list[Node]]],
) -> bytes:
    """*source_bytes* with every annotation region replaced by spaces.

    Newlines are kept so every byte offset and line number in the blinded
    source matches the original — symbols, line numbers and call sites are
    all reported against the real file.
    """
    blinded = bytearray(source_bytes)
    for start, end, _ in runs:
        for index in range(start, end):
            if blinded[index] not in (0x0A, 0x0D):
                blinded[index] = 0x20
    return bytes(blinded)


def _comment_spans(root: Node) -> list[tuple[int, int]]:
    """The byte spans of every comment in *root*."""
    spans: list[tuple[int, int]] = []

    def walk(node: Node) -> None:
        if node.type in COMMENT_NODE_TYPES:
            spans.append((node.start_byte, node.end_byte))
            return
        for child in node.children:
            walk(child)

    walk(root)
    return spans


def _symbol_declarations(root: Node) -> list[Node]:
    """Every node of the blinded tree that will yield a symbol, in order.

    The walk stops at function bodies, exactly like the symbol collectors:
    a local function or local class is not a symbol, so an annotation in
    front of one belongs to the enclosing symbol instead of vanishing.
    """
    declarations: list[Node] = []

    def walk_container(container: Node) -> None:
        for child in container.named_children:
            if child.type in _TYPE_DECL_KINDS or child.type in (
                "function_declaration",
                "anonymous_function",
                "secondary_constructor",
                "type_alias",
            ):
                declarations.append(child)
                body = _body_of(child)
                if body is not None:
                    walk_container(body)
            elif child.type == "companion_object":
                body = _body_of(child)
                if body is not None:
                    walk_container(body)
            elif child.type in _TYPE_BODY_CONTAINERS:
                walk_container(child)

    walk_container(root)
    return declarations


def _annotation_owners(
    blinded_root: Node,
    runs: list[tuple[int, int, list[Node]]],
    comment_spans: list[tuple[int, int]],
    blinded_bytes: bytes,
) -> dict[int, list[Node]]:
    """Map every declaration's blinded start byte to the annotations it owns.

    Two rules, both positional and therefore independent of how the
    grammar chose to parse the annotation:

    * **Preceding** — the run sits directly before a declaration, with only
      whitespace, comments and other runs in between, so it annotates that
      declaration (the attached and detached spellings both land here).
    * **Contained** — the run sits inside a declaration but in front of a
      non-symbol declaration (a property, an enum entry, a parameter, a
      type argument), so it belongs to the declaration it is inside.

    A run that neither precedes a symbol declaration nor sits inside one
    (a file annotation, an annotation on a top-level property) is owned by
    nothing: it is not part of any declaration's content.
    """
    ordered = sorted(
        _symbol_declarations(blinded_root), key=lambda node: node.start_byte
    )
    starts = [declaration.start_byte for declaration in ordered]
    owners: dict[int, list[Node]] = {}

    for start, end, units in runs:
        index = bisect_left(starts, end)
        following = ordered[index] if index < len(ordered) else None
        if following is not None and _gap_is_blank(
            blinded_bytes, end, following.start_byte, comment_spans
        ):
            owners.setdefault(following.start_byte, []).extend(units)
            continue

        # Contained rule: the innermost declaration containing the run.  Any
        # candidate starts at or before the run, so scanning backwards from
        # the insertion point reaches the deepest enclosing declaration first.
        position = bisect_right(starts, start) - 1
        while position >= 0:
            candidate = ordered[position]
            if end <= candidate.end_byte:
                owners.setdefault(candidate.start_byte, []).extend(units)
                break
            position -= 1

    return owners


def _gap_is_blank(
    source_bytes: bytes,
    start: int,
    end: int,
    comment_spans: list[tuple[int, int]],
) -> bool:
    """Whether only whitespace and comments sit between two byte offsets."""
    gap = bytearray(source_bytes[start:end])
    for comment_start, comment_end in comment_spans:
        if start <= comment_start and comment_end <= end:
            for index in range(comment_start - start, comment_end - start):
                gap[index] = 0x20
    return bytes(gap).strip() == b""


@dataclass(frozen=True)
class _AnnotationContext:
    """Annotation ownership for a blinded parse (D7).

    Attributes:
        owners: Declaration start byte (in the blinded source) to the
            annotation units folded into that declaration's hash.
        original_bytes: The unblinded source, whose text the annotation
            signatures are read from.
    """

    owners: dict[int, list[Node]]
    original_bytes: bytes


def _annotation_units(
    node: Node,
    context: _AnnotationContext | None,
) -> list[Node]:
    """The annotations folded into *node*'s hash (D7).

    A file with annotations is always collected from a blinded parse, so the
    ownership map answers; without one the file has no annotations at all —
    the only way ``_prepare_source`` declines — and there is nothing to fold.
    """
    if context is None:
        return []
    return context.owners.get(node.start_byte, [])


def _annotation_bytes(
    context: _AnnotationContext | None,
    source_bytes: bytes,
) -> bytes:
    """The bytes an annotation's signature is read from (D7)."""
    return source_bytes if context is None else context.original_bytes


def _prepare_source(
    parser: Parser,
    original_root: Node,
    original_bytes: bytes,
) -> tuple[bytes, Tree, _AnnotationContext] | None:
    """Blind *original_bytes* and parse it again, or ``None`` if unannotated.

    Only a file that actually contains annotations needs the second parse:
    without annotations the original tree is the blinded tree, so the
    scanner's long-standing path stays in place byte for byte.
    """
    runs = _annotation_runs(original_root)
    if not runs:
        return None
    blinded = _blind_source(original_bytes, runs)
    tree: Tree = parser.parse(blinded)
    owners = _annotation_owners(
        tree.root_node,  # type: ignore[attr-defined]
        runs,
        _comment_spans(original_root),
        blinded,
    )
    context = _AnnotationContext(owners=owners, original_bytes=original_bytes)
    return blinded, tree, context


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_kotlin_file(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> list[Symbol]:
    """Parse a single ``.kt``/``.kts`` file and return the symbols it defines."""
    path = Path(file_path).resolve()
    original_bytes = path.read_bytes()

    language = _get_kotlin_language()
    parser = _new_parser(language)
    tree: Tree = parser.parse(original_bytes)
    root = tree.root_node  # type: ignore[attr-defined]

    if root.has_error:
        logger.warning(
            "Syntax error detected in %s — extracting partial symbols",
            path,
        )

    symbol_path = _relative_to(path, repo_root)
    prepared = _prepare_source(parser, root, original_bytes)
    if prepared is None:
        return _collect_kotlin_symbols(root, original_bytes, symbol_path)

    blinded, blinded_tree, context = prepared
    return _collect_kotlin_symbols(
        blinded_tree.root_node,  # type: ignore[attr-defined]
        blinded,
        symbol_path,
        context=context,
    )


def scan_kotlin_calls(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> set[CallEvidence]:
    """Parse a single ``.kt``/``.kts`` file and return all call evidence."""
    path = Path(file_path).resolve()
    original_bytes = path.read_bytes()

    language = _get_kotlin_language()
    parser = _new_parser(language)
    tree: Tree = parser.parse(original_bytes)
    root = tree.root_node  # type: ignore[attr-defined]

    rel_path = _relative_to(path, repo_root)
    prepared = _prepare_source(parser, root, original_bytes)
    if prepared is None:
        return _extract_kotlin_calls(root, original_bytes, rel_path)

    blinded, blinded_tree, _ = prepared
    return _extract_kotlin_calls(
        blinded_tree.root_node,  # type: ignore[attr-defined]
        blinded,
        rel_path,
    )


def _relative_to(path: Path, repo_root: str | Path | None) -> Path:
    """Resolve *path* against *repo_root*, falling back to the absolute path."""
    if repo_root is None:
        return path
    try:
        return path.relative_to(Path(repo_root).resolve())
    except ValueError:
        return path


# ---------------------------------------------------------------------------
# Hashing (K8/D4 — annotations are hash-invariant across CST shapes)
# ---------------------------------------------------------------------------


def _annotation_signature(units: list[Node], source_bytes: bytes) -> str:
    """Canonical, grouping-independent signature of *units*.

    Every leaf of every unit is flattened into one whitespace-normalised
    token sequence, so ``@Ann(name = "x")`` produces the same signature
    whether the grammar wrapped the argument in a ``constructor_invocation``
    (attached) or handed it to a sibling ``parenthesized_expression``
    (detached, D4).
    """
    parts = [
        leaf_token_signature(
            unit, source_bytes, excluded_leaf_types=ASI_LEAF_EXCLUSIONS
        )
        for unit in units
    ]
    return "\x1f".join(part for part in parts if part)


def _declaration_hash(
    node: Node,
    units: list[Node],
    source_bytes: bytes,
    *,
    annotation_bytes: bytes | None = None,
    shell: bool,
) -> str:
    """Content hash for one Kotlin declaration.

    *units* are the annotations belonging to the declaration (D4/D7) and
    *annotation_bytes* is the source they are read from — the original file
    when the declaration was collected from a blinded parse, whose own
    *source_bytes* have the annotation text blanked out.

    The annotations are folded in as their canonical signature.  Under a
    blinded parse the declaration's own bytes are already annotation-free,
    which is what makes the attached and detached spellings hash identically.
    """
    parts: list[str] = []
    signature = _annotation_signature(
        units,
        source_bytes if annotation_bytes is None else annotation_bytes,
    )
    if signature:
        parts.append(signature)
    if shell:
        parts.append(
            class_shell_hash(
                node,
                source_bytes,
                excluded_leaf_types=ASI_LEAF_EXCLUSIONS,
                method_node_types=_KOTLIN_METHOD_NODE_TYPES,
            )
        )
    else:
        parts.append(
            structural_hash(
                node,
                source_bytes,
                excluded_leaf_types=ASI_LEAF_EXCLUSIONS,
            )
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Symbol collection
# ---------------------------------------------------------------------------


def _class_kind(node: Node, source_bytes: bytes) -> SymbolType:
    """Map a ``class_declaration`` to its symbol kind (probe K2).

    ``interface`` is a direct token (including ``fun interface`` and
    ``sealed interface``); ``enum``/``annotation``/``data``/``sealed``/
    ``value`` are ``class_modifier`` children.  ``annotation class`` maps
    to ``INTERFACE`` — the kind Java's ``@interface`` maps to, since both
    declare an annotation type.
    """
    for child in node.children:
        if child.type == "interface":
            return SymbolType.INTERFACE
    for child in node.named_children:
        if child.type != "modifiers":
            continue
        for modifier in child.named_children:
            if modifier.type != "class_modifier":
                continue
            keyword = text_of(modifier, source_bytes)
            if "enum" in keyword:
                return SymbolType.ENUM
            if "interface" in keyword or "annotation" in keyword:
                return SymbolType.INTERFACE
    return SymbolType.CLASS


def _body_of(node: Node) -> Node | None:
    """The type-body container of *node*, or ``None``.

    Kotlin gives type declarations no ``body`` *field* (probe K2/K3), so
    the body is located by node type.
    """
    for child in node.named_children:
        if child.type in _TYPE_BODY_CONTAINERS:
            return child
    return None


def _start_line(node: Node, units: list[Node]) -> int:
    """1-based line of a declaration, counting a *preceding* annotation.

    The grammar's attached form begins a declaration at its annotation, so
    an annotation that sits before the declaration must report the same
    line in both spellings (D4, and the blinded re-parse of D7).  An
    annotation *inside* the declaration — a property annotation, a
    parameter annotation, a local declaration's annotation — is content,
    not a prefix: the declaration keeps reporting its own line, exactly as
    it did before annotations were folded back in.
    """
    preceding = [unit for unit in units if unit.start_byte < node.start_byte]
    first = min(preceding, key=lambda unit: unit.start_byte) if preceding else node
    return first.start_point[0] + 1


def _collect_kotlin_symbols(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
    *,
    context: _AnnotationContext | None = None,
) -> list[Symbol]:
    """Collect symbols from every top-level declaration.

    ``package``/``import`` statements carry no symbols.  With *context* set
    the tree is a blinded parse (D7): annotations are looked up per
    declaration through the ownership map instead of read off the CST, and
    the signature bytes are the unblinded source.
    """
    symbols: list[Symbol] = []

    for child in root_node.named_children:
        if child.type in _TYPE_DECL_KINDS:
            _collect_type_declaration(
                child,
                source_bytes,
                file_path,
                symbols,
                context=context,
            )
        elif child.type in ("function_declaration", "anonymous_function"):
            if child.type == "anonymous_function" and (
                _name_from_error(child, source_bytes) is None
            ):
                continue
            # A top-level ``fun`` is FUNCTION with no ``parent_class`` —
            # including an extension function, whose receiver is not a
            # containing class (probe K4).  A top-level ``fun`` whose name
            # the grammar consumed as a modifier arrives as an
            # ``anonymous_function`` and is recovered (D5).
            _collect_function(
                child,
                source_bytes,
                file_path,
                symbols,
                context,
            )
        elif child.type == "type_alias":
            # This grammar names an alias with the ``type`` field (K9).
            name_node = child.child_by_field_name("type")
            if name_node is not None and text_of(name_node, source_bytes):
                units = _annotation_units(child, context)
                symbols.append(
                    Symbol(
                        name=text_of(name_node, source_bytes),
                        symbol_type=SymbolType.TYPE_ALIAS,
                        file_path=file_path,
                        line_number=_start_line(child, units),
                    )
                )

    return symbols


def _collect_function(
    node: Node,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
    context: _AnnotationContext | None = None,
) -> None:
    """Emit a top-level ``FUNCTION`` symbol."""
    name = _declaration_name(node, source_bytes)
    if name is None:
        return
    units = _annotation_units(node, context)
    symbols.append(
        Symbol(
            name=name,
            symbol_type=SymbolType.FUNCTION,
            file_path=file_path,
            line_number=_start_line(node, units),
            body_hash=_declaration_hash(
                node,
                units,
                source_bytes,
                annotation_bytes=_annotation_bytes(context, source_bytes),
                shell=False,
            ),
        )
    )


def _collect_type_declaration(
    node: Node,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
    *,
    enclosing_class: str | None = None,
    context: _AnnotationContext | None = None,
) -> None:
    """Emit one type declaration's symbol and collect its members."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return

    name = text_of(name_node, source_bytes)
    if not name:
        return

    symbol_type = (
        _class_kind(node, source_bytes)
        if node.type == "class_declaration"
        else SymbolType.CLASS
    )

    units = _annotation_units(node, context)
    body_hash: str | None = None
    if symbol_type in (SymbolType.CLASS, SymbolType.ENUM):
        body_hash = _declaration_hash(
            node,
            units,
            source_bytes,
            annotation_bytes=_annotation_bytes(context, source_bytes),
            shell=True,
        )

    symbols.append(
        Symbol(
            name=name,
            symbol_type=symbol_type,
            file_path=file_path,
            line_number=_start_line(node, units),
            parent_class=enclosing_class,
            body_hash=body_hash,
        )
    )

    body = _body_of(node)
    if body is not None:
        _walk_members(
            body,
            source_bytes,
            file_path,
            name,
            symbols,
            context=context,
        )


def _walk_members(
    container: Node,
    source_bytes: bytes,
    file_path: Path,
    class_name: str,
    symbols: list[Symbol],
    *,
    context: _AnnotationContext | None = None,
) -> None:
    """Collect the direct members of one type body.

    Only *direct* members become symbols, so a local function or class
    (inside a method body) and an enum-entry body (probe K11, matching
    Java's established boundary) yield no symbols — this walk never
    descends into a method body.  A companion object's entries are
    attributed to the **outer** class (probe K3), so its methods fire
    ``CHANGED_FUNCTION`` rather than a coarse ``CHANGED_CLASS``.
    """
    children = list(container.named_children)

    for member in children:
        if member.type in _TYPE_DECL_KINDS:
            _collect_type_declaration(
                member,
                source_bytes,
                file_path,
                symbols,
                enclosing_class=class_name,
                context=context,
            )
        elif member.type in ("function_declaration", "anonymous_function"):
            name = _declaration_name(member, source_bytes)
            if name is None:
                continue
            units = _annotation_units(member, context)
            symbols.append(
                Symbol(
                    name=name,
                    symbol_type=SymbolType.METHOD,
                    file_path=file_path,
                    line_number=_start_line(member, units),
                    parent_class=class_name,
                    body_hash=_declaration_hash(
                        member,
                        units,
                        source_bytes,
                        annotation_bytes=_annotation_bytes(context, source_bytes),
                        shell=False,
                    ),
                )
            )
        elif member.type == "secondary_constructor":
            units = _annotation_units(member, context)
            symbols.append(
                Symbol(
                    name=class_name,
                    symbol_type=SymbolType.METHOD,
                    file_path=file_path,
                    line_number=_start_line(member, units),
                    parent_class=class_name,
                    body_hash=_declaration_hash(
                        member,
                        units,
                        source_bytes,
                        annotation_bytes=_annotation_bytes(context, source_bytes),
                        shell=False,
                    ),
                )
            )
        elif member.type == "companion_object":
            body = _body_of(member)
            if body is not None:
                _walk_members(
                    body,
                    source_bytes,
                    file_path,
                    class_name,
                    symbols,
                    context=context,
                )
        elif member.type in _TYPE_BODY_CONTAINERS:
            _walk_members(
                member,
                source_bytes,
                file_path,
                class_name,
                symbols,
                context=context,
            )


# ---------------------------------------------------------------------------
# Call detection
# ---------------------------------------------------------------------------


def _extract_kotlin_calls(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> set[CallEvidence]:
    """Extract all :class:`CallEvidence` objects from a parsed Kotlin CST."""
    calls: set[CallEvidence] = set()
    function_nodes: list[tuple[str, Node, str | None]] = []

    _collect_kotlin_callers(root_node, source_bytes, function_nodes)

    for caller_name, func_node, caller_parent_class in function_nodes:
        _find_kotlin_calls_in_body(
            func_node,
            caller_name,
            func_node,
            source_bytes,
            file_path,
            calls,
            caller_parent_class=caller_parent_class,
        )

    return calls


def _property_name(node: Node, source_bytes: bytes) -> str | None:
    """The single declared name of a property, or ``None``.

    A property that declares several names at once is deliberately left
    alone: Kotlin gives the single initialiser to the *last* declarator, and
    guessing which name owns the value is exactly the kind of over-reach
    this scanner avoids.  A ``MISSING`` name node reads as the empty string
    and is refused, so a nameless property can never become a caller.
    """
    declarators = [
        child for child in node.named_children if child.type == "variable_declaration"
    ]
    if len(declarators) != 1 or declarators[0].named_child_count == 0:
        return None
    name_node = declarators[0].named_children[0]
    if name_node.type != "identifier":
        return None
    name = text_of(name_node, source_bytes)
    return name or None


def _property_function_value(
    node: Node,
    source_bytes: bytes,
) -> tuple[str, Node] | None:
    """``(name, function node)`` when a property's value is a function literal.

    Mirrors the JS/TS rule for ``const f = () => {}`` (probe K6).
    """
    value = _value_after_assign(node)
    if value is None or value.type not in _FUNCTION_VALUE_TYPES:
        return None
    name = _property_name(node, source_bytes)
    if name is None:
        return None
    return name, value


def _property_accessors(
    node: Node,
    source_bytes: bytes,
) -> list[tuple[str, Node]]:
    """``(property name, accessor node)`` for each ``get``/``set`` body (K11).

    An accessor is a *named* body, so it owns the calls inside it — the same
    rule TS applies to ``get value() { … }``.  Without it every call inside
    ``get() = format(field)`` would be dropped and the call graph would
    silently lose real edges.
    """
    accessors = [
        child for child in node.named_children if child.type in _PROPERTY_ACCESSOR_TYPES
    ]
    if not accessors:
        return []
    name = _property_name(node, source_bytes)
    if name is None:
        return []
    return [(name, accessor) for accessor in accessors]


def _value_after_assign(node: Node) -> Node | None:
    """The named child that follows a property's ``=`` token, if any."""
    seen_assign = False
    for child in node.children:
        if child.type == "=":
            seen_assign = True
            continue
        if seen_assign and child.is_named:
            return child
    return None


def _has_own_kotlin_caller(node: Node, source_bytes: bytes) -> bool:
    """Whether *node* carries its own caller entry.

    Named functions and secondary constructors always do; a property does
    only when its value is a function literal.  Lambdas that are *not*
    bound to a name are deliberately not callers — their calls belong to
    the nearest enclosing named caller, the rule the Phase 1 audit
    established for JS/TS (G1/G2).
    """
    if node.type in _METHOD_DECL_TYPES:
        return True
    if node.type == "anonymous_function":
        # Only a D5 mangle owns its calls.  A real anonymous function is a
        # *value*, and its calls belong to the nearest enclosing caller.
        return _name_from_error(node, source_bytes) is not None
    if node.type == "property_declaration":
        return _property_function_value(node, source_bytes) is not None or bool(
            _property_accessors(node, source_bytes)
        )
    return False


def _collect_kotlin_callers(
    node: Node,
    source_bytes: bytes,
    result: list[tuple[str, Node, str | None]],
    class_name: str | None = None,
) -> None:
    """Recursively collect every function-like node that can own calls.

    Each entry is ``(caller_name, function_node, caller_parent_class)``.
    Type declarations set the class attribution for their subtree; a
    companion keeps the *outer* class's name (probe K3); an anonymous
    ``object`` expression resets it to ``None`` because the type has no
    name (probe K11), exactly as Java's anonymous-class bodies do.
    """
    for child in node.named_children:
        if child.type in _TYPE_DECL_KINDS:
            name_node = child.child_by_field_name("name")
            nested_name = (
                text_of(name_node, source_bytes) if name_node is not None else None
            )
            _collect_kotlin_callers(
                child,
                source_bytes,
                result,
                class_name=nested_name,
            )
        elif child.type == _OBJECT_LITERAL:
            _collect_kotlin_callers(child, source_bytes, result, class_name=None)
        elif child.type == "anonymous_function" and node.type in _STATEMENT_CONTAINERS:
            # D5: a top-level (or type-body) ``fun`` whose name the grammar
            # consumed as a modifier — it still owns the calls in its body.
            recovered = _name_from_error(child, source_bytes)
            if recovered is not None:
                result.append((recovered, child, class_name))
            _collect_kotlin_callers(child, source_bytes, result, class_name=class_name)
        elif child.type in _METHOD_DECL_TYPES:
            name = _caller_name_for(child, class_name, source_bytes)
            if name is not None:
                result.append((name, child, class_name))
            _collect_kotlin_callers(child, source_bytes, result, class_name=class_name)
        elif child.type == "property_declaration":
            owned = _property_function_value(child, source_bytes)
            if owned is not None:
                result.append((owned[0], owned[1], class_name))
            for accessor_name, accessor_node in _property_accessors(
                child, source_bytes
            ):
                result.append((accessor_name, accessor_node, class_name))
            _collect_kotlin_callers(child, source_bytes, result, class_name=class_name)
        else:
            _collect_kotlin_callers(child, source_bytes, result, class_name=class_name)


def _caller_name_for(
    node: Node,
    class_name: str | None,
    source_bytes: bytes,
) -> str | None:
    """The caller name of a method-like node.

    A ``function_declaration`` names itself (an extension function is
    named like any other, probe K4); a ``secondary_constructor`` has no
    name field and is named after its enclosing class, exactly like a
    Java constructor.
    """
    if node.type in ("function_declaration", "anonymous_function"):
        return _declaration_name(node, source_bytes)
    return class_name


def _kotlin_called_name(
    call_node: Node,
    source_bytes: bytes,
) -> str | None:
    """Called name of a Kotlin ``call_expression`` (probe K5).

    A bare call's callee is an ``identifier``.  A member call's callee is a
    ``navigation_expression`` whose last named child is the member
    ``identifier`` — regardless of the receiver spelling (``obj.`` /
    ``x?.`` / ``x!!.`` / ``this.`` / ``super.`` / ``a[0].``, and the
    chained ``a.b.c()``).  The one dynamic receiver, a call
    (``f().bar()``), yields ``None``, mirroring the JS/TS/Java rule.
    Dunder-style member names are excluded like every other language; a
    bare ``__foo__()`` is not.
    """
    if call_node.named_child_count == 0:
        return None
    callee = call_node.named_children[0]

    if callee.type == "identifier":
        return text_of(callee, source_bytes)

    if callee.type == "navigation_expression":
        children = callee.named_children
        if len(children) < 2:
            return None
        receiver = children[0]
        if receiver.type == "call_expression":
            return None
        member = children[-1]
        if member.type != "identifier":
            return None
        name = text_of(member, source_bytes)
        if is_dunder_name(name):
            return None
        return name

    return None


def _find_kotlin_calls_in_body(
    node: Node,
    caller_name: str,
    root_func_node: Node,
    source_bytes: bytes,
    file_path: Path,
    calls: set[CallEvidence],
    caller_parent_class: str | None = None,
) -> None:
    """Walk *node* finding ``call_expression`` nodes.

    Nested functions, secondary constructors and function-valued
    properties carry their own caller entry, so they are skipped — each
    call is attributed to exactly one caller.  Anonymous lambdas are
    deliberately *not* skipped: they have no entry of their own, so calls
    inside them belong to the nearest enclosing named caller.
    """
    for child in node.named_children:
        if child is not root_func_node and _has_own_kotlin_caller(child, source_bytes):
            continue

        if child.type == "call_expression":
            called_name = _kotlin_called_name(child, source_bytes)
            if called_name is not None:
                calls.add(
                    CallEvidence(
                        file_path=file_path,
                        caller_name=caller_name,
                        called_name=called_name,
                        caller_parent_class=caller_parent_class,
                    )
                )

        _find_kotlin_calls_in_body(
            child,
            caller_name,
            root_func_node,
            source_bytes,
            file_path,
            calls,
            caller_parent_class=caller_parent_class,
        )
