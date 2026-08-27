# NoWreck

**Deterministic AI Verifier** — v0.11.1

NoWreck is a deterministic structural verifier for AI-generated code-change
claims. When an AI describes a code change, NoWreck compares the claims
against structural evidence derived by its own scanners — the verifier never
asks another AI for an opinion. Where the evidence comes from depends on the
mode: in Pre/Post and Claims modes, from actual before/after repository
snapshots; in Prompt Mode, from the model's own proposed diff.

<img width="1536" height="1024" alt="NoWreck CLI output showing confirmed and contradicted claims" src="https://github.com/user-attachments/assets/bcc62fa1-9605-498c-b22c-5328556b19d0" />

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
# Clone the repository
git clone https://github.com/AstralXVoid/NoWreck.git
cd NoWreck

# Install with pipx (recommended)
pipx install .

# Or with pip
pip install -e .

# Or inside a virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

`pipx install .` installs `nowreck` as a globally available command in your
user environment (PyPI publishing is coming later).

### Verify installation

```bash
nowreck --version
# → nowreck 0.11.1

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

Claims must be passed inline via `--claims`; the CLI does not currently
read claims from stdin. If you keep claims in a file, pass its JSON content
directly as the `--claims` argument.

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
| `ADD_INTERFACE` | An interface was added (TS/TSX, Rust, Go) | Structural existence check |
| `REMOVE_INTERFACE` | An interface was removed (TS/TSX, Rust, Go) | Structural existence check |
| `ADD_ENUM` | An enum was added (TS/TSX, Rust) | Structural existence check |
| `REMOVE_ENUM` | An enum was removed (TS/TSX, Rust) | Structural existence check |
| `ADD_TYPE_ALIAS` | A type alias was added (TS/TSX, Rust, Go) | Structural existence check |
| `REMOVE_TYPE_ALIAS` | A type alias was removed (TS/TSX, Rust, Go) | Structural existence check |
| `FILE_CREATED` | A new file appeared | File-list diff |
| `FILE_DELETED` | A file was removed | File-list diff |
| `CALLS_FUNCTION` | A function now calls another | Structural call-site detection |

All thirteen are evaluated using deterministic structural evidence. Note
that the mechanisms differ: `CALLS_FUNCTION` uses call-site analysis, while
the existence-based claim types use symbol-existence comparison.

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
makes the call) and `called_name` (the function being called).

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
  "version": "0.11.1",
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
  "version": "0.11.1",
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
  (`.ts`, `.tsx`), Rust (`.rs`), and Go (`.go`). Python uses the built-in
  `ast` module; JavaScript, TypeScript, Rust, and Go use Tree-sitter with
  their respective grammars.
- **Dynamic behavior cannot be reliably resolved** — `exec()`, `eval()`,
  dynamic imports, `getattr()` / `setattr()` with dynamic arguments,
  metaclasses, monkey-patching, and reflection fall outside the scanner's
  supported structural analysis and may be reported as `UNVERIFIABLE`.
- **`CALLS_FUNCTION` checks direct identifier calls only** — it verifies
  calls of the form `sanitize_input()`. It does **not** resolve
  `obj.sanitize_input()` or chained expressions, and it does not perform
  full semantic call-graph resolution.
- **No cross-file resolution** beyond direct name matching.
- **No semantic analysis** — NoWreck verifies structural facts, not intent,
  code quality, or correctness.
- **Prompt Mode requires a working repository** — it runs against the
  current working directory; without a real repository all claims come
  back UNVERIFIABLE.
- **Interfaces, enums, and type aliases** (TS/TSX, Rust, Go) are captured
  as structural symbols and verified for existence only (added/removed) —
  not for semantic correctness.
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
  `.rs`, or `.go`)
- The Tree-sitter packages are installed for the languages you scan
  (`tree-sitter-javascript`, `tree-sitter-typescript`,
  `tree-sitter-rust`, `tree-sitter-go`)
- Files inside hidden directories (names starting with `.`) are skipped

---

## Roadmap

**v0.11.1 is the current release.** Items marked 🗓 are planned future work,
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
| Caching for large repositories | 🗓 planned |
| CI/CD integration | 🗓 planned |

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

*NoWreck v0.11.1 — August 2026*
