<div align="center">

# NoWreck

**Deterministic AI Verifier** — v0.17.0

</div>
<div align="center">
<img width="140" height="140" alt="tom" src="https://github.com/user-attachments/assets/49b7222a-5f92-47c5-880c-42646833e788" />

</div>

<div align="center">NoWreck is a deterministic structural verifier for AI-generated code-change
claims.<br></div> <div align="center">When an AI describes a code change, NoWreck compares the claims
against structural evidence derived by its own scanners — the verifier never
asks another AI for an opinion.</div><div align="center"> Where the evidence comes from depends on the
mode: in Pre/Post and Claims modes, from actual before/after repository
snapshots; in Prompt Mode, from the model's own proposed diff.</div>


<img width="1983" height="793" alt="ChatGPT Image Sep 10, 2026, 09_48_57 PM" src="https://github.com/user-attachments/assets/f5e28277-2f18-4b12-9090-ac7e33a687f0" />

```
$ nowreck fix "Add email validation to auth.py"

  Summary
  ────────────────────
  ● 3 claims total
  ● 2 confirmed
  ● 1 contradicted

  CONFIRMED
  ─────────
  ✓ ADD_FUNCTION validate_email → auth.py  (conf: 100%)
    Evidence: Function 'validate_email' was added in auth.py

  CONTRADICTED
  ────────────
  ✗ CALLS_FUNCTION validate_email → auth.py  (conf: 100%)
    Evidence: Function 'validate_email' was added in auth.py
```

## What it catches

- **Hallucinated functions or classes** — a claim that something was added when it isn't there
- **Fake internal API calls** — a claim that a function was called when it wasn't
- **Explanation-vs-diff mismatches** — a description of a change that doesn't match the actual diff
- **Unexplained changes** — structural changes that no supplied claim mentioned

NoWreck does **not** ask: *"Is this code good?"*

NoWreck asks: *"Do the supplied structural claims match the structural
changes actually detected in the compared repository states?"*

Nothing more, nothing less. NoWreck is deliberately narrow. It is **not** an
AI code reviewer, a test runner, a security scanner, a semantic verifier, or
a code-quality judge, and it does not determine whether code is secure,
performant, idiomatic, bug-free, or semantically correct.

```
Claims → structural evidence → deterministic comparison → verdict
```

**The verifier uses no AI judgment.** The decision stage never asks an AI
whether a claim is true. (NoWreck does use a model in Prompt Mode — to
generate the proposed diff and claims — but never in the decision stage.)
"Deterministic" describes *how* NoWreck decides: the scanner and verifier
follow explicit structural rules. It is not a promise of perfect analysis —
NoWreck is deterministic within its supported structural analysis model
(see [Limitations](#limitations)).

## Table of Contents

1. [What it catches](#what-it-catches)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Quick Start](#quick-start)
5. [Usage Modes](#usage-modes)
   - [Prompt Mode](#prompt-mode)
   - [Pre/Post Mode](#prepost-mode)
   - [Claims Mode](#claims-mode)
   - [Interactive Mode](#interactive-mode)
6. [Command Reference](#command-reference)
7. [How It Works](#how-it-works)
8. [Claim Types](#claim-types)
9. [Understanding the Report](#understanding-the-report)
10. [Confidence System](#confidence-system)
11. [JSON Output for CI](#json-output-for-ci)
12. [Limitations](#limitations)
13. [Comparison](#comparison)
14. [Troubleshooting](#troubleshooting)
15. [Roadmap](#roadmap)
16. [License](#license)

---

## Installation

Requires Python 3.11+.

```bash
# From PyPI (recommended)
pipx install nowreck
# or: pip install nowreck

# From source (development)
git clone https://github.com/AstralXVoid/NoWreck.git
cd NoWreck
pip install -e .
```

### Verify installation

```bash
nowreck --version
# → nowreck 0.17.0

nowreck
# → shows banner + usage
```

### Uninstall

```bash
pipx uninstall nowreck
# or
pip uninstall nowreck
```

---

## Configuration

NoWreck stores configuration in `.nowreck/config.json` under the current
working directory.

### Required settings for Prompt Mode

Before using `nowreck fix "<prompt>"`, configure an API key and model
provider:

```bash
# Set your API key (or use the NOWRECK_API_KEY env var instead)
nowreck config set api_key gsk_your_key_here

# Set the API base URL (defaults to https://api.openai.com/v1)
nowreck config set base_url https://api.groq.com/openai/v1

# Set the model (defaults to gpt-4o)
nowreck config set model llama-3.3-70b-versatile
```

### Alternative: environment variable

Set `NOWRECK_API_KEY` instead of storing the key in config:

```bash
export NOWRECK_API_KEY="gsk_your_key_here"
```

### Optional settings

```bash
# Temperature (0.0 = deterministic, default)
nowreck config set temperature 0.0

# Max retries on parse failure (default: 1)
nowreck config set max_retries 2

# Explicit provider override (auto-detected from base_url when unset)
nowreck config set provider anthropic   # or: gemini, openai
```

### View configuration

```bash
nowreck config show
# → api_key = gsk_your_key_here
# → base_url = https://api.groq.com/openai/v1
# → model = llama-3.3-70b-versatile
```

> **Heads-up:** `config show` prints stored values as-is — including your
> full API key. Run it only in trusted environments.

### Compatible providers

| Provider | Base URL | Format |
|----------|----------|--------|
| **OpenAI** | `https://api.openai.com/v1` (default) | OpenAI-compatible |
| **Anthropic** | `https://api.anthropic.com` | Anthropic Messages API |
| **Gemini** | `https://generativelanguage.googleapis.com` | Gemini generateContent |
| **Groq** | `https://api.groq.com/openai/v1` | OpenAI-compatible |
| **OpenRouter** | `https://openrouter.ai/api/v1` | OpenAI-compatible |
| **DeepSeek** | `https://api.deepseek.com/v1` | OpenAI-compatible |
| **Ollama (local)** | `http://localhost:11434/v1` | OpenAI-compatible |
| **LM Studio (local)** | `http://localhost:1234/v1` | OpenAI-compatible |
| **Any OpenAI-compatible** | Your custom endpoint | OpenAI-compatible |

Since v0.11.0, Anthropic and Gemini are supported natively via provider
adapters. The provider is **auto-detected from `base_url`** — set the
matching base URL and NoWreck handles the rest:

```bash
# Claude
nowreck config set base_url https://api.anthropic.com
nowreck config set api_key sk-ant-...
nowreck config set model claude-sonnet-4-20250514

# Gemini
nowreck config set base_url https://generativelanguage.googleapis.com
nowreck config set api_key AIza...
nowreck config set model gemini-2.0-flash
```

> **Note:** use the bare domain for Anthropic and Gemini base URLs — do
> not add a `/v1` or `/v1beta` suffix (NoWreck appends the versioned path
> itself). If auto-detection ever picks the wrong format, force it with
> `nowreck config set provider anthropic|gemini|openai`.

> **Note for Groq users:** Groq currently blocks bare Python `urllib`
> requests with a Cloudflare 1010 error. NoWreck sends a browser-style
> User-Agent header to work around this, but if you encounter issues,
> try OpenRouter or a direct OpenAI API key instead.

---

## Quick Start

### Step 1 — Pick a test repo

Create a small Python project with before and after snapshots:

```bash
mkdir -p /tmp/myapp/pre /tmp/myapp/post

# Pre: original code
cat > /tmp/myapp/pre/app.py << 'EOF'
def hello():
    return "Hello, World!"
EOF

# Post: add a new function (simulating an AI change)
cat > /tmp/myapp/post/app.py << 'EOF'
def hello():
    return "Hello, World!"

def greet(name: str) -> str:
    return f"Hello, {name}!"
EOF
```

### Step 2 — Pre/Post Mode: run detection (no claims)

```bash
nowreck fix --pre /tmp/myapp/pre --post /tmp/myapp/post
```

This is **Pre/Post Mode** with no claims supplied. NoWreck scans both
snapshots, detects the structural changes between them, and reports them as
**unexplained** — because no claims were supplied to match against
(NoWreck also prints a few scan-progress lines before the report):

```
═══════════════════════════════════════════════════════
  Nowreck Verification Report
═══════════════════════════════════════════════════════

  Summary
  ────────────────────
  ● 0 claims total
  ● 0 confirmed
  ● 1 unexplained change

  UNEXPLAINED CHANGES
  ───────────────────
  ! ADD_FUNCTION greet (app.py)

```

### Step 3 — Claims Mode: run with claims

```bash
nowreck fix \
  --pre /tmp/myapp/pre \
  --post /tmp/myapp/post \
  --claims '{
    "claims": [
      {
        "type": "ADD_FUNCTION",
        "symbol_name": "greet",
        "file_path": "app.py",
        "confidence": 0.99,
        "explanation": "Added the greet function as requested."
      },
      {
        "type": "CALLS_FUNCTION",
        "symbol_name": "greet",
        "file_path": "app.py",
        "caller_name": "greet",
        "called_name": "sanitize_input",
        "confidence": 0.85,
        "explanation": "greet calls sanitize_input before returning."
      }
    ]
  }'
```

This is **Claims Mode**: the claims are supplied externally, and NoWreck
verifies them against the structural changes detected from the two
snapshots. Expected output — the hallucinated `CALLS_FUNCTION` claim is
caught because the code contains no such call:

```
═══════════════════════════════════════════════════════
  Nowreck Verification Report
═══════════════════════════════════════════════════════

  Summary
  ────────────────────
  ● 2 claims total
  ● 1 confirmed
  ● 1 contradicted

  CONFIRMED
  ─────────
  ✓ ADD_FUNCTION greet → app.py  (conf: 100%)
    Evidence: Function 'greet' was added in app.py

  CONTRADICTED
  ────────────
  ✗ CALLS_FUNCTION greet → app.py  (conf: 100%)
    Evidence: Function 'greet' was added in app.py

```

---

## Usage Modes

NoWreck has three verification modes. They share the same pipeline and
differ in where claims and evidence come from.

### Prompt Mode

Describe a change in natural language. NoWreck calls the configured model
and verifies the claims that model produces.

How it works:

1. NoWreck sends your prompt to the configured model.
2. The model returns a **proposed diff** plus **structured claims**
   describing that diff.
3. NoWreck derives the post-change repository state implied by the proposed
   diff, scans it against the current state, and produces `DetectedChange`
   facts.
4. The deterministic verifier matches each claim against those facts and
   prints the report.

**What Prompt Mode verifies.** Since v0.10.0, Prompt Mode uses independent
verification: NoWreck captures the repository state before and after the
model applies its patch, scans both states independently, and verifies
the model's claims against the independently observed changes.

Concretely:

- If the model claims `validate_email()` was added but the patch doesn't
  add it — NoWreck reports **CONTRADICTED**.
- If the model claims a function calls `sanitize_input()` but the actual
  code doesn't — NoWreck reports **CONTRADICTED**.
- If no before/after transition is available — NoWreck reports
  **UNVERIFIABLE** (never guesses).

The fundamental invariant: **a model claim must never be used as the
source of evidence for verifying that same claim.**

**Requirements:** an API key (config or `NOWRECK_API_KEY` env var) and a
configured model (defaults to `gpt-4o`).

```bash
nowreck fix "Add a validation function to app.py"
```

### Pre/Post Mode

Two directory snapshots already exist. NoWreck scans both and reports the
structural changes between them. **No API key or model is required** — this
mode runs fully offline.

This is the cleanest independent-verification workflow in v0.10.0:

```
actual before snapshot
+ actual after snapshot
+ external claims (optional, via --claims)
→ deterministic structural verification
```

The snapshots are real repository states, and any claims — from any AI,
another tool, or a person — can be supplied through `--claims`. NoWreck
does not generate the claims itself; it only verifies them against the
evidence.

```bash
nowreck fix --pre ./repo-before --post ./repo-after
```

Useful for:

- Manual testing during development
- CI/CD pipelines where you have two checkouts
- Verifying changes without an AI model

### Claims Mode

Combine Pre/Post Mode with externally supplied claims. NoWreck detects the
changes *and* verifies the claims against them:

```bash
nowreck fix \
  --pre ./repo-before \
  --post ./repo-after \
  --claims '{"claims": [{"type": "ADD_FUNCTION", "symbol_name": "greet", "file_path": "app.py"}]}'
```

Because the claims come from outside NoWreck and the evidence comes from
real before/after snapshots, Claims Mode — together with Pre/Post Mode — is
a genuinely independent verification path. (Since v0.10.0, Prompt Mode is
also independent — it captures before/after state automatically.)

Claims can be passed inline via `--claims`, or read from a file using the
`@` prefix — useful for large claim sets and CI pipelines that generate
claims files:

```bash
# Read claims from a file (@ prefix)
nowreck fix --pre ./repo-before --post ./repo-after --claims @claims.json
```

### Interactive Mode
<div align="center">
<img width="480" height="270" alt="premium_terminal_intercative" src="https://github.com/user-attachments/assets/5294eb73-5073-474e-b772-adfb5d68b372" />
</div>


`nowreck --interactive` launches a menu-driven terminal picker for users who
prefer exploring options without memorizing commands:

- **Verify with AI prompt** — Prompt Mode against the current repository
- **Scan two directories for changes** — Pre/Post Mode; optionally supply
  claims afterwards to switch into Claims Mode
- **Set up or change your API key** — guided configuration
- **View last report** — re-render the most recent verification report

Great for beginners, one-off verifications, and learning the tool's
capabilities.

<img width="961" height="701" alt="NoWreck interactive mode menu" src="https://github.com/user-attachments/assets/1608ea03-fc56-409e-87dd-42d9025c84e3" />

### Flags

| Flag | Applies to | Description |
|------|-----------|-------------|
| `--json` | All modes | Output structured JSON instead of coloured text (for CI) |
| `--no-colour` | All modes | Disable ANSI colour codes |
| `--verbose` | All modes | Show full deterministic evidence per claim; no-op with `--json` |
| `--pre PATH` | Pre/Post, Claims | Path to the pre-change snapshot |
| `--post PATH` | Pre/Post, Claims | Path to the post-change snapshot |
| `--claims JSON` | Claims | JSON string of claims to verify |

---

## Command Reference

| Command | Description |
|---------|-------------|
| `nowreck` | Show help / usage |
| `nowreck --version` | Show version |
| `nowreck --interactive` | Launch the interactive terminal picker |
| `nowreck fix "<prompt>"` | **Prompt Mode** — describe a change; NoWreck calls the model and verifies its claims |
| `nowreck fix --pre PATH --post PATH` | **Pre/Post Mode** — scan two snapshots and detect structural changes |
| `nowreck fix --pre PATH --post PATH --claims JSON` | **Claims Mode** — detect changes *and* verify externally supplied claims |
| `nowreck fix --json` | Output flag — structured JSON instead of coloured text (works with any `nowreck fix` mode) |
| `nowreck fix --no-colour` | Output flag — disable ANSI colours (works with any `nowreck fix` mode) |
| `nowreck fix --verbose` | Output flag — full deterministic evidence per claim (works with any `nowreck fix` mode) |
| `nowreck config show` | Display current configuration |
| `nowreck config set <key> <value>` | Set a config value. Keys: `api_key`, `model`, `base_url`, `temperature`, `max_retries`, `provider` |

---

## How It Works

From the user's perspective, the pipeline is **Scan → Detect → Verify**.
Architecturally, **Scan + Detect form the evidence stage** — they parse code
and produce `DetectedChange` facts — and **Verify is the comparison stage**,
where the deterministic verifier checks claims against those facts.

```
  claims source                          repository evidence source
  (AI model, or external AI /            (actual snapshots, or the
   tool / person)                        model's proposed diff)
           │                                   │
           ▼                                   ▼
        Claims ──────────────────►  Structural scanner
           │                                   │
           │                                   ▼
           │                     DetectedChange facts  (source of truth)
           │                                   │
           └───────────────►  Deterministic verifier
                                        │
                                        ▼
                  CONFIRMED / CONTRADICTED / UNVERIFIABLE
```

The two boundaries:

```
Scanner:   source code → structural facts
Verifier:  claims + structural facts → verdict
```

- **Claims come from somewhere.** In Prompt Mode, the model generates them.
  In Claims Mode, they are supplied externally. The verifier treats them
  the same either way.
- **The scanner derives structural facts.** It parses both states and
  produces a `list[DetectedChange]` — the single source of truth that the
  verifier references exclusively.
- **The verifier compares fields.** AST and Tree-sitter parsing happen
  upstream, during scanning. The verifier consumes only `DetectedChange`
  records and performs deterministic field-based comparison: same type and
  identity fields → **CONFIRMED**. Contradicting change → **CONTRADICTED**.
  No match → **UNVERIFIABLE**.
- **The verifier uses no AI judgment.** It never asks an AI whether a claim
  is correct, and it never re-reads or re-parses the source code itself.
- **No guessing.** If NoWreck cannot establish a structural fact, it reports
  `UNVERIFIABLE` rather than inventing an answer.

### Independence in v0.10.0

Since v0.10.0, **all modes use independent verification.** Claims and
evidence always come from different sources:

```
Prompt Mode (v0.10.0):
  model ──► claims ──────────────────────────────────────────────────────┐
                                                                         ├──► verifier ──► verdict
  before state ──┐                                                       │
  model patch ───┴──► after state ──► scanner ──► DetectedChange facts ─┘

Pre/Post + Claims:
  external AI / tool ──► claims ──┐
                                  ├──► deterministic verifier ──► verdict
  before snapshot ──┐             │
  after snapshot ───┴──► scanner ─┴──► DetectedChange facts
```

The fundamental invariant: **a model claim must never be used as the
source of evidence for verifying that same claim.**

### Stage 1 — Scan

Recursively discovers source files and parses each with the appropriate
parser, building a symbol index of every function, class, and method:

| Language | Files | Parser |
|----------|-------|--------|
| Python | `.py` | Built-in `ast` module |
| JavaScript | `.js` | Tree-sitter (`tree-sitter-javascript`) |
| TypeScript | `.ts`, `.tsx` | Tree-sitter (`tree-sitter-typescript`) |
| Rust | `.rs` | Tree-sitter (`tree-sitter-rust`) |
| Go | `.go` | Tree-sitter (`tree-sitter-go`) |
| Java | `.java` | Tree-sitter (`tree-sitter-java`) |
| Kotlin | `.kt`, `.kts` | Tree-sitter (`tree-sitter-kotlin`) |
| PHP | `.php` | Tree-sitter (`tree-sitter-php`) |
| C++ | `.cpp`, `.cc`, `.cxx`, `.c++`, `.hpp`, `.hh`, `.hxx`, `.h++`, `.h` | Tree-sitter (`tree-sitter-cpp`) |

All parsers produce the same `Symbol` / `SymbolType` data shapes, so the
rest of the pipeline never knows (or cares) which language produced the
data. This is structural parsing, not semantic analysis.

### Stage 2 — Detect

Compares the pre and post symbol indices to find structural changes:
added/removed functions, classes, files, and new function calls. This
produces the **single source of truth** — a `list[DetectedChange]` that the
verifier references exclusively.

### Stage 3 — Verify

For each claim, the verifier looks for a matching `DetectedChange`. If one
exists with the same type and identity fields → **CONFIRMED**. If a
contradicting change exists (e.g., claim says "added" but detection shows
"removed") → **CONTRADICTED**. If nothing matches → **UNVERIFIABLE**.

---

## Claim Types

| Claim type | What it means | Verified by |
|------------|---------------|-------------|
| `ADD_FUNCTION` | A function was added | Structural existence check |
| `REMOVE_FUNCTION` | A function was removed | Structural existence check |
| `ADD_CLASS` | A class was added | Structural existence check |
| `REMOVE_CLASS` | A class was removed | Structural existence check |
| `ADD_INTERFACE` | An interface was added (TS/TSX, Rust, Go, Java, Kotlin, PHP) | Structural existence check |
| `REMOVE_INTERFACE` | An interface was removed (TS/TSX, Rust, Go, Java, Kotlin, PHP) | Structural existence check |
| `ADD_ENUM` | An enum was added (TS/TSX, Rust, Java, Kotlin, PHP, C++) | Structural existence check |
| `REMOVE_ENUM` | An enum was removed (TS/TSX, Rust, Java, Kotlin, PHP, C++) | Structural existence check |
| `ADD_TYPE_ALIAS` | A type alias was added (TS/TSX, Rust, Go, Kotlin, C++) | Structural existence check |
| `REMOVE_TYPE_ALIAS` | A type alias was removed (TS/TSX, Rust, Go, Kotlin, C++) | Structural existence check |
| `CHANGED_FUNCTION` | A function's body was changed | Structural body-diff |
| `CHANGED_CLASS` | A class's shell (fields, bases, decorators) was changed | Structural body-diff |
| `FILE_CREATED` | A new file appeared | File-list diff |
| `FILE_DELETED` | A file was removed | File-list diff |
| `CALLS_FUNCTION` | A function now calls another | Structural call-site detection |

All fifteen are evaluated using deterministic structural evidence. Note
that the mechanisms differ: `CALLS_FUNCTION` uses call-site analysis, while
the existence-based claim types use symbol-existence comparison, and the
`CHANGED_*` types use a formatting-insensitive structural body hash (edited
logic always changes it; reformatting, comment, and quote-style edits do
not).

**Per-language notes:**

- **Java** — no top-level functions: every function symbol is a method, so
  `ADD_FUNCTION` / `CHANGED_FUNCTION` claims always name it with
  `parent_class`; `@interface` maps to INTERFACE.
- **Kotlin** — extension functions are indexed as ordinary top-level
  functions (no `parent_class`); `annotation class` maps to INTERFACE.
- **PHP** — traits map to CLASS (their methods carry the trait name as
  `parent_class`); `TYPE_ALIAS` never fires; `$obj->m()`, `Class::m()`, and
  `self::` / `static::` / `parent::` calls resolve to the method name.
- **C++** — `INTERFACE` never fires (C++ has no interface keyword); a
  declaration and its out-of-line definition are independent per-file
  facts; `obj->m()` and `Class::m()` calls are captured.

### Claim fields

Every claim accepts:

- `type` — one of the claim types above (required)
- `symbol_name` — the symbol the claim is about
- `file_path` — path to the file, relative to the scanned root
- `confidence` — 0.0 to 1.0, how certain the claimer is
- `explanation` — why the change was made
- `parent_class` — required when the symbol is a method inside a class
- `line_number` — optional 1-based line number

`CALLS_FUNCTION` additionally requires `caller_name` (the function that
makes the call) and `called_name` (the function being called). When the
caller is a method, `parent_class` is **required** — evidence is matched
strictly on the enclosing class.

---

## Understanding the Report

### Sample output

```
═══════════════════════════════════════════════════════
  Nowreck Verification Report
═══════════════════════════════════════════════════════

  Summary
  ────────────────────
  ● 3 claims total
  ● 2 confirmed
  ● 1 contradicted
  ● 1 unexplained change

  CONFIRMED
  ─────────
  ✓ ADD_FUNCTION validate_email → auth.py  (conf: 100%)
    Evidence: Function 'validate_email' was added in auth.py
  ✓ FILE_CREATED → validators.py  (conf: 100%)
    Evidence: File 'validators.py' was created

  CONTRADICTED
  ────────────
  ✗ CALLS_FUNCTION validate_email → auth.py  (conf: 100%)
    Evidence: Function 'validate_email' was added in auth.py

  UNEXPLAINED CHANGES
  ───────────────────
  ! REMOVE_FUNCTION legacy_func (app.py)

```

### Sections explained

| Section | Meaning |
|---------|---------|
| **Summary** | Counts of total claims, confirmed, contradicted, unverifiable, and unexplained |
| **CONFIRMED** | Claims that matched a detected structural change |
| **CONTRADICTED** | Claims that contradict the structural evidence (e.g., a claimed call doesn't exist) |
| **UNVERIFIABLE** | Claims with no matching detected change one way or the other |
| **UNEXPLAINED CHANGES** | Structural changes detected from the compared repository states that no supplied claim matched. NoWreck does not infer intent — it cannot tell you whether a change was necessary, correct, or malicious, only that it exists and was not explained |

### Exit codes

| Exit code | Meaning |
|-----------|---------|
| `0` | Every claim confirmed (none contradicted or unverifiable), nothing unexplained |
| `1` | One or more contradicted, unverifiable, or unexplained changes |

---

## Confidence System

Confidence reflects NoWreck's certainty in its **verification result**,
within its supported structural analysis model. It is not confidence that
the code change is correct, and it is not a rating of the claim's quality.

| Verdict | Displayed confidence | Meaning |
|---------|---------------------|---------|
| **CONFIRMED** | `100%` | The verifier deterministically established that the required structural condition for the claim exists within its supported analysis model |
| **CONTRADICTED** | `100%` | The verifier deterministically established the structural condition required for that verdict — e.g., the detected change is the opposite of the claim, or the claimed supported structural fact is absent from the analyzed state |
| **UNVERIFIABLE** | The claimer's original confidence | NoWreck could not establish the claim from its supported structural evidence; it reports the claim's own confidence rather than inventing a number |

A 100% verdict applies to the specific claim being checked, within the
supported analysis model — it does **not** mean the overall code change is
correct, and it does **not** prove universal semantic facts. For example,
a CONTRADICTED `CALLS_FUNCTION` verdict establishes that no matching
call-site change exists among the detected structural facts; it does not
prove the function can never be invoked dynamically elsewhere.

---

## JSON Output for CI

Use the `--json` flag to get a machine-readable report. The schema depends
on the mode:

### Prompt Mode schema

```bash
nowreck fix "Add validation to auth.py" --json
```

```json
{
  "version": "0.17.0",
  "mode": "prompt_v10",
  "success": false,
  "evidence": {
    "independent": true,
    "patch_applied": true,
    "patch_files": ["auth.py"]
  },
  "summary": {
    "total_claims": 3,
    "confirmed": 2,
    "contradicted": 1,
    "unverifiable": 0,
    "unexplained_count": 0
  },
  "results": [
    {
      "claim": {
        "type": "ADD_FUNCTION",
        "symbol_name": "validate_email",
        "file_path": "auth.py",
        "parent_class": null,
        "line_number": null,
        "caller_name": null,
        "called_name": null,
        "confidence": 0.99
      },
      "verdict": "CONFIRMED",
      "verifier_confidence": 1.0,
      "matched_change": {
        "change_type": "ADD_FUNCTION",
        "file_path": "auth.py",
        "symbol_name": "validate_email",
        "parent_class": null,
        "line_number": 5,
        "caller_name": null,
        "called_name": null
      }
    }
  ],
  "unexplained_changes": []
}
```

The `evidence` block reports whether the v10 independent-verification path
ran: claims were checked against changes observed in the repository before
and after the model's patch was applied (see
[How It Works](#how-it-works)).

### Pre/Post and Claims Mode schema

`--pre`/`--post` runs omit the `mode` and `evidence` fields; everything
else is identical:

```json
{
  "version": "0.17.0",
  "success": false,
  "summary": { "total_claims": 3, "confirmed": 2, "contradicted": 1, "unverifiable": 0, "unexplained_count": 0 },
  "results": [ { "claim": {}, "verdict": "CONFIRMED", "verifier_confidence": 1.0, "matched_change": {} } ],
  "unexplained_changes": []
}
```

Notes:

- `success` is `true` only when every claim is confirmed (none
  contradicted **or unverifiable**) and there are no unexplained changes;
  otherwise it is `false`. It is a JSON boolean (`true` / `false`), not a
  string.
- Claim objects contain exactly: `type`, `symbol_name`, `file_path`,
  `parent_class`, `line_number`, `caller_name`, `called_name`,
  `confidence`. The free-text `explanation` is **not** included in JSON
  output — it is accepted on input and kept on the claim, but NoWreck's
  reports do not render it.

### CI integration

The simplest and most robust integration is to rely on NoWreck's exit code:

```yaml
# GitHub Actions — fail the job when verification fails.
# Exit code 0 → all claims confirmed, nothing unexplained.
# Exit code 1 → contradicted, unverifiable, or unexplained changes.
- name: Verify AI changes
  run: nowreck fix "Add validation to auth.py" --json
```

If you prefer to parse the JSON instead:

```bash
REPORT=$(nowreck fix "Add validation to auth.py" --json)
echo "$REPORT" | python3 -c "import sys, json; d = json.load(sys.stdin); print('success:', d['success'])"
# 'success' is a JSON boolean — compare with True/False, not the string "True".
```

---

## Limitations

NoWreck verifies structure, not semantics. Be aware of these boundaries:

- **Supported languages** — Python (`.py`), JavaScript (`.js`), TypeScript
  (`.ts`, `.tsx`), Rust (`.rs`), Go (`.go`), Java (`.java`), Kotlin
  (`.kt`, `.kts`), PHP (`.php`), and C++ (`.cpp`, `.cc`, `.cxx`, `.c++`,
  `.hpp`, `.hh`, `.hxx`, `.h++`, `.h`). Python uses the built-in `ast`
  module; the other eight use Tree-sitter with their respective grammars.
  `.h` files are parsed with the C++ grammar (plain C headers parse too);
  `.c` files are not discovered.
- **Per-language structural boundaries** — Java has no top-level
  functions (function claims always name a method); Kotlin extension
  functions are ordinary top-level functions; PHP traits map to CLASS and
  `TYPE_ALIAS` never fires there; C++ `INTERFACE` never fires. In C++, a
  declaration and its out-of-line definition are independent per-file
  facts — no `#include` resolution or cross-file symbol linking is
  performed, and a declaration-only member carries no body hash, so a
  declaration edit alone cannot fire `CHANGED_FUNCTION`.
- **Dynamic behavior cannot be reliably resolved** — `exec()`, `eval()`,
  dynamic imports, `getattr()` / `setattr()` with dynamic arguments,
  metaclasses, monkey-patching, and reflection fall outside the scanner's
  supported structural analysis and may be reported as `UNVERIFIABLE`.
- **`CALLS_FUNCTION` resolves member chains, not the full call graph** —
  direct calls (`sanitize_input()`) and member/attribute/field/selector
  calls (`obj.sanitize_input()`, `self.foo()`, `a.b.c()`, `pkg.Func()`,
  `s.foo()`) are captured with the final name as `called_name`; receivers
  that are themselves calls (`f().bar()`) and dunder-style names
  (`obj.__x__()`) are excluded. No semantic call-graph resolution is
  performed.
- **`CHANGED_*` claims verify body edits structurally** — `CHANGED_FUNCTION`
  / `CHANGED_CLASS` use a formatting-insensitive structural hash, so body
  edits confirm, and reformat-only / comment-only / quote-style edits do
  not. Python `async def` functions and methods are indexed (methods
  inside classes) like their sync counterparts.
- **No cross-file resolution** beyond direct name matching.
- **No semantic analysis** — NoWreck verifies structural facts, not intent,
  code quality, or correctness.
- **Prompt Mode requires a working repository** — it runs against the
  current working directory; without a real repository all claims come
  back UNVERIFIABLE.
- **Interfaces, enums, and type aliases** are captured as structural
  symbols in the languages that have them (TS/TSX, Rust, Go, Java, Kotlin,
  PHP, C++ — per-type availability in the claim table above) and verified
  for existence only (added/removed) — not for semantic correctness.
- **The verifier works from `DetectedChange` facts**, not by re-reading the
  repository. It is deterministic within its supported analysis model, not
  infallible.

---

## Comparison

| Tool | What it does | Relationship to NoWreck |
|------|-------------|------------------------|
| Cursor / Claude Code / Copilot | Generate and edit code | **Complementary** — NoWreck verifies claims about changes rather than generating them |
| CodeRabbit / Qodo / Greptile | AI review of a diff's quality | **Different focus** — AI-assisted review rather than deterministic claim verification |
| Agent Verifier (aurite-ai) | AI agent skill for code quality/security | **Different focus** — checks quality/security, not claim truthfulness |
| slopcheck / slop-scan | Check third-party package names against registries | **Different focus** — dependency-name checks, a different hallucination category |
| ESLint / Ruff / Black | Linting and formatting | **Different focus** — syntax/style enforcement, not structural verification |

NoWreck is designed specifically for deterministic structural verification
of claims about code changes.

---

## Troubleshooting

### "Error: No API key provided"

Configure your API key:

```bash
# Option A: store in config
nowreck config set api_key your_key_here

# Option B: set environment variable
export NOWRECK_API_KEY="your_key_here"
```

### "API returned 401"

Your API key is invalid or expired. Check the key and provider URL:

```bash
nowreck config show
# Verify api_key and base_url are correct
```

### "API returned 1010" (Cloudflare block)

This happens with some providers (notably Groq) when Python's `urllib`
doesn't send a realistic User-Agent. Try:

1. Upgrade NoWreck (the built-in fix sends a browser UA)
2. Switch to OpenRouter or another provider
3. Use a direct OpenAI API key

### JSON parsing errors

If the model returns malformed JSON, NoWreck automatically retries once by
sending the error details back to the model with a repair request. Failed
responses are saved to `.nowreck/failed/` for debugging.

### No changes detected

Make sure:

- Both `--pre` and `--post` paths exist and are directories
- The directories contain supported files (`.py`, `.js`, `.ts`, `.tsx`,
  `.rs`, `.go`, `.java`, `.kt`/`.kts`, `.php`, or `.cpp`/`.h`-family)
- The Tree-sitter packages are installed for the languages you scan
  (`tree-sitter-javascript`, `tree-sitter-typescript`,
  `tree-sitter-rust`, `tree-sitter-go`, `tree-sitter-java`,
  `tree-sitter-kotlin`, `tree-sitter-php`, `tree-sitter-cpp`)
- Files inside hidden directories (names starting with `.`) are skipped

---

## CI/CD Integration

NoWreck supports CI/CD pipelines with machine-readable output formats and
automated git comparison.

### Output Formats

```bash
# JSON (for scripting)
nowreck fix --compare HEAD~1 --format json > report.json

# SARIF (for GitHub Code Scanning)
nowreck fix --compare HEAD~1 --format sarif > nowreck.sarif

# JUnit XML (for Jenkins/GitLab CI test reports)
nowreck fix --compare HEAD~1 --format junit > nowreck-junit.xml
```

### Git Comparison

```bash
# Compare current state against previous commit
nowreck fix --compare HEAD~1

# Compare against a specific branch
nowreck fix --compare main

# Verify claims against a PR
nowreck fix --compare main --claims '{...}'
```

### GitHub Actions Example

```yaml
name: NoWreck Verification
on: [pull_request]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - run: pip install nowreck

      - name: Run NoWreck verification
        run: nowreck fix --compare HEAD~1 --format sarif > nowreck.sarif

      - name: Upload SARIF to GitHub Code Scanning
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: nowreck.sarif
```

---

## Roadmap

**v0.17.0 is the current release.** Items marked 🗓 are planned future work,
not present in the current release.

| Item | Status |
|------|--------|
| Interactive terminal picker | ✅ v0.2.0 |
| JavaScript support (Tree-sitter scanner + symbol index) | ✅ v0.3.0 |
| JavaScript polish (generators, export default, IIFEs) | ✅ v0.4.0 |
| TypeScript support (Tree-sitter scanner + symbol index + full pipeline) | ✅ v0.5.0 |
| `--verbose` mode showing full deterministic evidence per claim | ✅ v0.6.0 |
| TSX (`.tsx` files) support | ✅ v0.7.0 |
| Interfaces / enums / type aliases as claim types | ✅ v0.8.0 |
| Rust + Go language support | ✅ v0.9.0 |
| Independent verification architecture — make independent verification native and convenient: claims can come from any external AI/tool while NoWreck inspects the actual resulting repository state (Pre/Post + Claims already provides independent verification in v0.10.0) | ✅ done in v0.10.0 |
| Additional model providers (Anthropic, Gemini) via provider adapters with auto-detection from `base_url` | ✅ v0.11.0 |
| Provider consolidation — single `resolve_provider()` replaces split `_auth_header()` + `detect_adapter()` | ✅ v0.12.0 |
| Scan caching — file-level cache in `.nowreck/cache/` for faster repeated runs | ✅ v0.12.0 |
| CI/CD integration (SARIF, JUnit, --compare) | ✅ v0.13.0 |
| `--claims @file.json` — read claims from a file instead of inline JSON only | ✅ v0.14.0 |
| PyPI publishing — `pip install nowreck` | ✅ v0.15.0 |
| `CHANGED` claims (verifiable "I modified X") — function/class body edits | ✅ v0.16.0 |
| Method/attribute call detection (`obj.method()`, `self.foo()`) with strict class matching | ✅ v0.16.0 |
| Java, Kotlin, PHP + C++ language support (nine languages total) | ✅ v0.17.0 |
| Differential audit of the existing five parsers — regex checker + corpus, every divergence classified | ✅ v0.17.0 |

---

## License

**FSL-1.1-MIT** (Functional Source License, Version 1.1, MIT Future License)

Source is fully visible — read it, learn from it, use it internally, run it,
modify it for your own use. The one restriction: it can't be used to build a
competing commercial product or service while this version is under FSL.

Full terms are in [`LICENSE`](./LICENSE).

This version converts automatically to the plain **MIT license** in July
2028 (two years after initial release, per FSL's standard terms). No action
is required for the conversion.

*NoWreck v0.17.0 — October 2026*
