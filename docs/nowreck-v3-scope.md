# NoWreck — v3 Scope (JavaScript Support Only)

**Status:** Draft. Local development only — not published, not merged into the
public repo, until proven and deliberately released. Same discipline as v2.

## Principle

Same rule as v2: one small thing at a time, proven before expanding. v3 was
nearly scoped as JS + TypeScript + Rust + Go + caching, all at once — that
was caught and rejected before any code was written, for the same reason
RFC v2 (the very first draft of this whole project) had to be audited back
down to something buildable. **v3 is JavaScript support only. Nothing else.**

TypeScript, Rust, Go, and caching are real, legitimate future directions —
each gets its own scope document, later, only after JS is proven working.

## Mandatory build discipline for this increment

This section exists specifically because fast, all-at-once code generation
is a known risk with the tool being used to build this. The following rules
apply to every session working on v3, without exception:

1. **Build in phases, one component at a time** — following the same order
   as the original pipeline (§3.2 of the frozen spec): scanner → symbol
   index → detector → claim verification → reporting. Do not write code for
   a later phase before the current phase is complete, tested, and reviewed.
2. **No phase is "done" until it's been shown to work on a real, hand-built
   test file** — not just claimed to work, not just passing an automated
   test the same session that wrote it. This mirrors Milestone 1 from the
   original frozen spec.
3. **Stop and report after each phase**, don't continue straight into the
   next one unprompted. A human checkpoint between phases is required, not
   optional — this is exactly the "verified against frozen RFC" claim that
   turned out not to be true once, earlier in this project. Trust is
   re-established by checking, not by assuming compliance.
4. **If asked to build multiple phases in one response, refuse and ask
   which single phase to focus on first.** Speed is not the goal here.
   Correctness and verifiability are.

## What's in scope for this v3 increment

**JavaScript symbol scanning and claim verification, added as a second
`LanguageAdapter` alongside the existing Python one.**

### Parser choice: Tree-sitter, justified

Python uses stdlib `ast` because it's built in and Python-specific. JS has
no equivalent standard library parser, so a real dependency is needed here
regardless. Tree-sitter is chosen because:
- It has mature, well-maintained JavaScript grammar support
- It's the same parser family that would be used for future languages
  (Go, Rust, etc.), so this integration effort is somewhat reusable, not a
  one-off dependency choice
- It provides concrete syntax trees with real source positions, which
  matters for accurate claim-to-diff line mapping (the same reason LibCST
  was considered, and rejected as unnecessary, for Python — but JS doesn't
  have Python's simpler stdlib option)

### Repo scope for v3

Repos can mix Python and JavaScript files. The `LanguageAdapter` interface
(already anticipated in earlier architecture drafts) means each file is
routed to the correct scanner based on its extension (`.py` → Python
adapter, `.js` → JavaScript adapter), and both adapters produce the same
`Symbol` / `DetectedChange` data shapes so the verifier doesn't need to know
or care which language it's looking at.

### Claim types: unchanged

Exactly the same 7 claim types as the Python MVP — `ADD_FUNCTION`,
`REMOVE_FUNCTION`, `ADD_CLASS`, `REMOVE_CLASS`, `FILE_CREATED`,
`FILE_DELETED`, `CALLS_FUNCTION`. No new claim types, no semantic/heuristic
claims. If a JS-specific claim type genuinely seems necessary later (e.g.
something around `export`/`import` patterns), that's a future scope
decision, made deliberately, not something to add mid-build because it
seems easy.

### JS-specific symbol handling (kept as simple as possible for v3)

- Function declarations (`function foo() {}`)
- Arrow functions assigned to a variable (`const foo = () => {}`) — common
  enough in real JS code to be worth covering in v3, unlike Python's nested
  functions which were deferred
- Classes and class methods (`class Foo { bar() {} }`)
- Top-level `require`/`import` statements, tracked the same shallow way as
  Python's direct-import-only approach — no chain-following, no re-export
  resolution, matching the same simplicity decision made for Python

### Explicitly deferred, even within "JS support"

- Arrow functions as object properties, IIFEs, and other less common
  patterns — cover the common cases first, expand only if real usage shows
  gaps
- CommonJS vs ES module distinction beyond basic import/require detection
- Any TypeScript syntax (types, interfaces, generics) — this is JS only

## Do Not Build Yet (v3 edition)

Everything from v2's list still applies, plus:

- TypeScript support (explicitly deferred to its own future scope, even
  though it's closely related to this work)
- Rust, Go, or any other language
- Caching of any kind — including for the new JS scanner. Confirmed in
  discussion: caching and language support are independent problems and
  should not be built together. Caching is validated against Python (the
  proven, stable language support) if and when it's built, not against a
  brand-new JS integration at the same time.
- Cross-file import resolution beyond direct, single-level require/import
- Any claim type beyond the existing 7

## Implementation notes

- Likely library: `tree-sitter` + `tree-sitter-javascript` grammar
- Build and test in the local development copy only, same workflow as v2 —
  no git remote pushes until this is deliberately ready to share
- Definition of done: the same hallucination-catch test used to validate
  Python (a real prompt, a real model, a deliberately induced false claim)
  succeeds on a JavaScript test file, with CONFIRMED/CONTRADICTED results
  matching reality

## Explicitly not a roadmap

Same as v2's scope doc: this covers exactly one thing — JavaScript support,
same claim types, phase-by-phase, human-checked at every step. When it's
done and proven, the next increment (TypeScript, another language, or
caching) gets its own equally narrow scoping conversation.
