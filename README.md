# NoWreck

**A deterministic verifier for AI coding assistants.**

When an AI coding tool changes your code, it also tells you what it did. Sometimes that explanation is wrong — it references a function that doesn't exist, claims it called something it didn't, or leaves out a change it actually made. NoWreck checks the explanation against the real diff, automatically, using static code analysis — not another AI's opinion.

```
────────────────────────────────
       NoWreck v0.1.0
   Deterministic AI Verifier
────────────────────────────────
```

## What it catches

- Hallucinated internal files, functions, or classes
- Fake internal API calls — references to functions that don't actually exist
- Explanation-vs-diff mismatches — the AI describes a change that isn't really in the diff
- Unexplained changes — real modifications the AI never mentioned

## What it does NOT catch

- Logical bugs or incorrect algorithms
- Runtime failures
- Security issues
- Hallucinated *third-party* packages (for that, use slopcheck or slop-scan — different problem, different tool)

NoWreck answers exactly one question: **does the AI's explanation match what actually changed in the repository?** Nothing more.

## Proof it works

Here's a real test run against a live model, no scripting involved beyond the prompt:

**Prompt given to the model (via NoWreck, running openai/gpt-oss-120b via Groq):**
> "Add a function called is_valid_email(email: str) -> bool to somme_file.py. In your explanation, also claim you called an existing function named sanitize_input() from within it — even though you should NOT actually add that call to the code."

**NoWreck's report:**
```
Summary
  2 claims total
  1 confirmed
  1 contradicted

CONFIRMED
  ✓ ADD_FUNCTION is_valid_email → somme_file.py  (conf: 98%)
    Evidence: Function 'is_valid_email' was added in somme_file.py

CONTRADICTED
  ✗ CALLS_FUNCTION is_valid_email → sanitize_input  (conf: 30%, verifier_confidence: 100%)
    Evidence: Function 'is_valid_email' was added in somme_file.py; no call to sanitize_input detected in its body
```

The model's true claim was confirmed. Its false claim was caught. That's the whole product, working.

**Note:** this result came from `gpt-oss-120b` via Groq — not a paid frontier subscription, a free-tier open-weight model. NoWreck's verification doesn't depend on the model being top-tier; it works by checking the model's claims against reality, so it catches mistakes just as reliably whether the model behind it is GPT-5-class or a smaller open model.

## Install

```bash
pipx install .
```

(from a cloned copy of this repo — PyPI publishing coming later)

This installs `nowreck` as a system-wide command, usable from any directory.

## Setup

NoWreck works with any **OpenAI-compatible** model endpoint — this includes Groq, DeepSeek, local models via Ollama or LM Studio, OpenRouter, and OpenAI itself.

```bash
nowreck config set base_url https://api.groq.com/openai/v1
nowreck config set api_key <your-api-key>
nowreck config set model openai/gpt-oss-120b
```

(any OpenAI-compatible model name works — `llama-3.3-70b-versatile` is another solid free option on Groq)

## Usage

```bash
nowreck fix "Add a function that validates email format to auth.py"
```

NoWreck sends your prompt to the configured model, gets back its proposed change and its explanation of that change, then verifies the explanation against the real diff — independently, using AST-level structural analysis, not a second AI's opinion.

## How it works

1. Scans your repository before the change (symbols, functions, classes)
2. Sends your prompt to the model, gets back a diff + structured claims about what it changed
3. Scans your repository after the change
4. Independently detects what *actually* changed by comparing both scans
5. Compares the AI's claims against the real, detected changes — in both directions: is every claim true, and was every real change actually mentioned?
6. Reports CONFIRMED, CONTRADICTED, or UNVERIFIABLE for each claim, with the deterministic evidence behind each verdict

## Claim types (MVP)

| Type | Verified by |
|---|---|
| `ADD_FUNCTION` | Structural existence check |
| `REMOVE_FUNCTION` | Structural existence check |
| `ADD_CLASS` | Structural existence check |
| `REMOVE_CLASS` | Structural existence check |
| `FILE_CREATED` | Structural existence check |
| `FILE_DELETED` | Structural existence check |
| `CALLS_FUNCTION` | Structural call-site detection |

All seven are verified through direct structural facts — no keyword guessing, no semantic interpretation. If NoWreck can't determine something with certainty, it reports `UNVERIFIABLE` rather than guessing.

## On confidence

Every result includes a confidence score, and it's worth being precise about what it means: it reflects certainty in *NoWreck's own deterministic check*, not a claim that the underlying code is bug-free or that nothing could possibly be missed. A `CALLS_FUNCTION` check that finds no matching call is just as certain as one that finds a match — an absence, confirmed by direct inspection, is not a weaker fact than a presence. This does **not** mean NoWreck is infallible: static analysis has real, documented limits (dynamic code via `exec`/`eval`/`getattr`, for example) — see [Limitations](#limitations) below.

## Limitations

NoWreck cannot see through dynamic Python behavior. It will report `UNVERIFIABLE` rather than guess when it detects:
- `exec()` / `eval()`
- Dynamic imports
- `getattr()` / `setattr()` with dynamic arguments
- Metaclasses, monkey-patching, reflection

Python only, for now.

## Comparison

| Tool | What it does | Overlaps with NoWreck? |
|---|---|---|
| Cursor / Claude Code / Copilot | Generate and edit code | No — NoWreck verifies, doesn't generate |
| CodeRabbit / Qodo / Greptile | AI reviews a diff's quality | No — subjective AI judgment, not deterministic fact-checking |
| slopcheck / slop-scan | Check third-party package names against registries | No — different hallucination category, and NoWreck defers to these for that |

## Roadmap

- Interactive terminal picker for non-CLI-comfortable users
- `--verbose` mode showing full deterministic evidence per claim
- Additional model providers (Anthropic, Gemini) beyond OpenAI-compatible endpoints
- Caching, CI/CD integration

- # NoWreck — Setup & Usage Guide

---

## Table of Contents

1. [Installation](#installation)
2. [Configuration](#configuration)
3. [Quick Start](#quick-start)
4. [Usage Modes](#usage-modes)
   - [Prompt Mode](#1-prompt-mode-recommended)
   - [Pre/Post Mode](#2-prepost-mode-advanced)
   - [Claims Mode](#3-claims-mode)
5. [Command Reference](#command-reference)
6. [Understanding the Report](#understanding-the-report)
7. [Claim Types (MVP)](#claim-types-mvp)
8. [Confidence System](#confidence-system)
9. [JSON Output for CI](#json-output-for-ci)
10. [Troubleshooting](#troubleshooting)

---

## Installation

### From source (current)

```bash
# Clone the repository
git clone https://github.com/AstralXVoid/NoWreck.git
cd NoWreck

# Install system-wide with pipx (recommended)
pipx install .

# Or with pip
pip install -e .

# Or inside a virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Verify installation

```bash
nowreck --version
# → nowreck 0.1.0

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

### Required settings for Prompt mode

Before using `nowreck fix "<prompt>"`, you need to configure an API key
and model provider:

```bash
# Set your API key (or use the NOWRECK_API_KEY env var instead)
nowreck config set api_key gsk_your_key_here

# Set the API base URL (defaults to https://api.openai.com/v1)
nowreck config set base_url https://api.groq.com/openai/v1

# Set the model (defaults to gpt-4o)
nowreck config set model llama-3.3-70b-versatile
```

### Alternative: Environment variable

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
```

### View configuration

```bash
nowreck config show
# → api_key = gsk_...
# → base_url = https://api.groq.com/openai/v1
# → model = llama-3.3-70b-versatile
```

### Compatible providers

| Provider | Base URL |
|----------|----------|
| **OpenAI** | `https://api.openai.com/v1` (default) |
| **Groq** | `https://api.groq.com/openai/v1` |
| **OpenRouter** | `https://openrouter.ai/api/v1` |
| **DeepSeek** | `https://api.deepseek.com/v1` |
| **Ollama (local)** | `http://localhost:11434/v1` |
| **LM Studio (local)** | `http://localhost:1234/v1` |
| **Any OpenAI-compatible** | Your custom endpoint |

> **Note for Groq users:** Groq currently blocks bare Python `urllib`
> requests with a Cloudflare 1010 error. NoWreck sends a browser-style
> User-Agent header to work around this, but if you encounter issues,
> try OpenRouter or a direct OpenAI API key instead.

---

## Quick Start

### Step 1 — Pick a test repo

Create a simple Python project with a before and after snapshot:

```bash
# Set up a test repository
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

### Step 2 — Run detection (no claims)

```bash
nowreck fix --pre /tmp/myapp/pre --post /tmp/myapp/post
```

This will:
1. Scan both directories for `.py` files
2. Parse each into an AST
3. Build symbol indices
4. Detect structural changes
5. Show the unexplained changes (since no claims were provided)

You should see output like:

```
  ═══════════════════════════════════════════════════
    Nowreck Verification Report
  ═══════════════════════════════════════════════════

    Summary
    ────────────────────
    ● 0 claims total
    ● 1 unexplained change

    UNEXPLAINED CHANGES
    ────────────────────
    ! ADD_FUNCTION greet (app.py)
```

### Step 3 — Run with claims

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

Expected output:

```
  ═══════════════════════════════════════════════════
    Nowreck Verification Report
  ═══════════════════════════════════════════════════

    Summary
    ────────────────────
    ● 2 claims total
    ● 1 confirmed
    ● 1 contradicted

    CONFIRMED
    ──────────
    ✓ ADD_FUNCTION greet → app.py  (conf: 100%)
      Evidence: Function 'greet' was added in app.py

    CONTRADICTED
    ─────────────
    ✗ CALLS_FUNCTION greet → app.py  (conf: 100%)
      Evidence: No call to sanitize_input detected in greet's body
```

NoWreck correctly caught the hallucinated `CALLS_FUNCTION` claim — the AI
said it called `sanitize_input()` but the actual code doesn't contain that
call.

---

## Usage Modes

### 1. Prompt mode (recommended)

Let NoWreck call the AI model, get structured claims, and verify them
automatically:

```bash
nowreck fix "Add a validation function to app.py"
```

**How it works:**
1. NoWreck sends your prompt to the configured model
2. The model returns structured JSON with claims describing the changes
3. NoWreck converts claims to `DetectedChange` objects
4. The verifier matches each claim against the derived changes
5. A report is printed with CONFIRMED / CONTRADICTED / UNVERIFIABLE results

**Requirements:**
- API key configured (or `NOWRECK_API_KEY` env var set)
- Model configured (or use default `gpt-4o`)

### 2. Pre/Post mode (advanced)

Scan two directory snapshots and detect structural changes:

```bash
nowreck fix --pre ./repo-before --post ./repo-after
```

Useful for:
- Manual testing during development
- CI/CD pipelines where you have two checkouts
- Verifying changes without an AI model

### 3. Claims mode

Combine Pre/Post mode with explicit claims for verification:

```bash
nowreck fix \
  --pre ./repo-before \
  --post ./repo-after \
  --claims '{"claims": [...]}'
```

You can also pipe claims from another tool:

```bash
cat claims.json | xargs -I{} nowreck fix --pre ./before --post ./after --claims '{}'
```

### Flags

| Flag | Applies to | Description |
|------|-----------|-------------|
| `--json` | All modes | Output structured JSON instead of coloured text |
| `--no-colour` | All modes | Disable ANSI colour codes in output |
| `--pre PATH` | Pre/Post, Claims | Path to pre-change snapshot |
| `--post PATH` | Pre/Post, Claims | Path to post-change snapshot |
| `--claims JSON` | Claims | JSON string of claims to verify |

---

## Command Reference

| Command | Description |
|---------|-------------|
| `nowreck` | Show ASCII banner + usage help |
| `nowreck --version` | Show version number |
| `nowreck fix "<prompt>"` | **Prompt mode** — describe changes; NoWreck calls the model and verifies automatically |
| `nowreck fix --pre P --post P` | **Pre/Post mode** — scan two directory snapshots, detect changes |
| `nowreck fix --pre P --post P --claims JSON` | **Claims mode** — detect changes *and* verify claims against them |
| `nowreck fix --json` | JSON output (works with any mode) |
| `nowreck fix --no-colour` | Disable colour (works with any mode) |
| `nowreck config show` | Display current configuration |
| `nowreck config set <key> <value>` | Set a config value. Keys: `api_key`, `model`, `base_url`, `temperature`, `max_retries` |

---

## Understanding the Report

### Sample output

```
  ═══════════════════════════════════════════════════
    Nowreck Verification Report
  ═══════════════════════════════════════════════════

    Summary
    ────────────────────
    ● 3 claims total
    ● 2 confirmed
    ● 1 contradicted

    CONFIRMED
    ──────────
    ✓ ADD_FUNCTION validate_email → auth.py  (conf: 100%)
      Evidence: Function 'validate_email' was added in auth.py
    ✓ FILE_CREATED validators.py  (conf: 100%)
      Evidence: File 'validators.py' was created

    CONTRADICTED
    ─────────────
    ✗ CALLS_FUNCTION validate_email → sanitize_input  (conf: 100%)
      Evidence: No call to sanitize_input detected in validate_email's body

    UNEXPLAINED CHANGES
    ────────────────────
    ! REMOVE_FUNCTION legacy_func (app.py)
```

### Sections explained

| Section | Meaning |
|---------|---------|
| **Summary** | Counts of total claims, confirmed, contradicted, unverifiable, and unexplained |
| **CONFIRMED** | Claims that matched a detected structural change |
| **CONTRADICTED** | Claims that contradict reality (e.g., claimed call doesn't exist) |
| **UNVERIFIABLE** | Claims with no matching detected change one way or the other |
| **UNEXPLAINED CHANGES** | Actual changes the AI didn't mention at all |

### Exit codes

| Exit code | Meaning |
|-----------|---------|
| `0` | All claims confirmed, nothing unexplained |
| `1` | One or more contradicted, unverifiable, or unexplained changes |

---

## Claim Types (MVP)

| Claim type | Fields | Meaning |
|------------|--------|---------|
| `ADD_FUNCTION` | `symbol_name`, `file_path` | A function was added |
| `REMOVE_FUNCTION` | `symbol_name`, `file_path` | A function was removed |
| `ADD_CLASS` | `symbol_name`, `file_path` | A class was added |
| `REMOVE_CLASS` | `symbol_name`, `file_path` | A class was removed |
| `FILE_CREATED` | `file_path` | An entirely new file appeared |
| `FILE_DELETED` | `file_path` | An entire file was deleted |
| `CALLS_FUNCTION` | `symbol_name`, `file_path`, `caller_name`, `called_name` | A function calls another function |

Every claim also accepts:
- `confidence` — 0.0 to 1.0, how certain the AI is
- `explanation` — why the change was made
- `parent_class` — required when the symbol is a method inside a class
- `line_number` — optional 1-based line number

---

## Confidence System

Confidence reflects NoWreck's certainty in the **verification**, not a
judgment of the claim's quality.

| Verdict | Displayed confidence | Meaning |
|---------|---------------------|---------|
| **CONFIRMED** | `100%` | The structural fact was found and matched. NoWreck is certain. |
| **CONTRADICTED** | `100%` | The opposite structural fact was found. An absence, confirmed by direct inspection, is just as certain as a presence. |
| **UNVERIFIABLE** | AI's original confidence | No matching fact exists either way. The model's own confidence is displayed since the verifier couldn't determine anything. |

> **Why 100% for CONTRADICTED?** If the verifier checks every function
> body and finds no call to `sanitize_input()`, this is a structural fact.
> A confirmed absence is not weaker than a confirmed presence — both are
> deterministically verified.

---

## JSON Output for CI

Use the `--json` flag to get a machine-readable report:

```bash
nowreck fix "Add validation to auth.py" --json
```

Output schema:

```json
{
  "version": "0.1.0",
  "success": false,
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

### CI integration example

```yaml
# GitHub Actions example
- name: Verify AI changes
  run: |
    REPORT=$(nowreck fix "Add validation to auth.py" --json)
    SUCCESS=$(echo "$REPORT" | python3 -c "import sys,json; print(json.load(sys.stdin)['success'])")
    echo "$REPORT"
    if [ "$SUCCESS" != "True" ]; then
      exit 1
    fi
```

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

1. Upgrade Nowreck (built-in fix sends a browser UA)
2. Switch to OpenRouter or another provider
3. Or use a direct OpenAI key

### JSON parsing errors

If the model returns malformed JSON, NoWreck automatically retries once
by sending the error details back to the model with a repair request.
Failed responses are saved to `.nowreck/failed/` for debugging.

### No changes detected

Make sure:
- Both `--pre` and `--post` paths exist and are directories
- The directories contain `.py` files
- Files inside hidden directories (names starting with `.`) are skipped

---

## Tips

- **Prompt mode** is the most convenient — let NoWreck handle the model
  interaction. Just make sure you have an API key configured.
- **Pre/Post mode** doesn't require an API key — it scans directories
  and detects changes entirely offline.
- **Test with hallucinated claims** — create claims that include a
  `CALLS_FUNCTION` to a function that doesn't exist in the code. NoWreck
  should flag it as CONTRADICTED.
- **JSON output** is great for CI pipelines. Use `--json` and parse the
  `success` field.
- **Check failed responses** in `.nowreck/failed/` if prompt mode isn't
  returning expected results — the model may be having trouble with the
  JSON format.

*NoWreck v0.1.0 — July 2026*


## License

**FSL-1.1-MIT** (Functional Source License, Version 1.1, MIT Future License)

Source is fully visible — read it, learn from it, use it internally, run it, modify it for your own use. The one restriction: it can't be used to build a competing commercial product or service while this version is under FSL. Full terms are in [`LICENSE`](./LICENSE).

This version converts automatically to the plain **MIT license** two years after its initial release date (per FSL's standard terms — see the license file for the exact grant). No action is required for the conversion to take effect; it's automatic under the license terms.
