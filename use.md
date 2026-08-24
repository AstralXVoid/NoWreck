# NoWreck — Setup & Usage Guide

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
7. [Claim Types](#claim-types)
8. [Confidence System](#confidence-system)
9. [JSON Output for CI](#json-output-for-ci)
10. [Troubleshooting](#troubleshooting)

---

## Installation

Requires Python 3.11+.

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
# → nowreck 0.11.0

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

Since v0.11.0, Claude and Gemini work natively — the provider is
auto-detected from the base URL:

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

> **Note:** for Anthropic and Gemini, use the bare domain as the base URL —
> no `/v1` or `/v1beta` suffix (NoWreck appends the versioned path itself).
> If needed, force the format with `nowreck config set provider anthropic|gemini|openai`.

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
1. NoWreck captures the repository state (before)
2. NoWreck sends your prompt to the configured model
3. The model returns structured JSON with claims AND a unified diff patch
4. NoWreck applies the patch to the working tree
5. NoWreck captures the repository state (after)
6. NoWreck scans both states independently to detect real changes
7. The verifier matches each claim against the independently observed changes
8. A report is printed with CONFIRMED / CONTRADICTED / UNVERIFIABLE results

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
| `--verbose` | All modes | Show full deterministic evidence per claim (detail blocks instead of one-line summaries); no-op with `--json` |
| `--pre PATH` | Pre/Post, Claims | Path to pre-change snapshot |
| `--post PATH` | Pre/Post, Claims | Path to post-change snapshot |
| `--claims JSON` | Claims | JSON string of claims to verify |

> **Verbose example:** `nowreck fix --pre ./before --post ./after --claims '{"claims": [...]}' --verbose` renders each claim with its full identity fields, the complete matched change (including `line_number`), and full detail for unverifiable and unexplained changes. Without `--verbose`, each claim shows the same one-line summary as before — output is byte-identical to earlier versions.

---

## Command Reference

| Command | Description |
|---------|-------------|
| `nowreck` | Show ASCII banner + usage help |
| `nowreck --version` | Show version number |
| `nowreck --interactive` | Launch the interactive terminal picker (menu-driven) |
| `nowreck fix "<prompt>"` | **Prompt mode** — describe changes; NoWreck calls the model and verifies automatically |
| `nowreck fix --pre P --post P` | **Pre/Post mode** — scan two directory snapshots, detect changes |
| `nowreck fix --pre P --post P --claims JSON` | **Claims mode** — detect changes *and* verify claims against them |
| `nowreck fix --json` | JSON output (works with any mode) |
| `nowreck fix --no-colour` | Disable colour (works with any mode) |
| `nowreck fix --verbose` | Full evidence per claim (works with any mode) |
| `nowreck config show` | Display current configuration |
| `nowreck config set <key> <value>` | Set a config value. Keys: `api_key`, `model`, `base_url`, `temperature`, `max_retries`, `provider` |

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
| **CONTRADICTED** | Claims that contradict reality (e.g., claimed call doesn't exist) |
| **UNVERIFIABLE** | Claims with no matching detected change one way or the other |
| **UNEXPLAINED CHANGES** | Actual changes the AI didn't mention at all |

### Exit codes

| Exit code | Meaning |
|-----------|---------|
| `0` | Every claim confirmed (none contradicted or unverifiable), nothing unexplained |
| `1` | One or more contradicted, unverifiable, or unexplained changes |

---

## Claim Types

| Claim type | Fields | Meaning |
|------------|--------|---------|
| `ADD_FUNCTION` | `symbol_name`, `file_path` | A function was added |
| `REMOVE_FUNCTION` | `symbol_name`, `file_path` | A function was removed |
| `ADD_CLASS` | `symbol_name`, `file_path` | A class was added |
| `REMOVE_CLASS` | `symbol_name`, `file_path` | A class was removed |
| `ADD_INTERFACE` | `symbol_name`, `file_path` | An interface was added (TS/TSX/Rust/Go) |
| `REMOVE_INTERFACE` | `symbol_name`, `file_path` | An interface was removed |
| `ADD_ENUM` | `symbol_name`, `file_path` | An enum was added (TS/TSX/Rust) |
| `REMOVE_ENUM` | `symbol_name`, `file_path` | An enum was removed |
| `ADD_TYPE_ALIAS` | `symbol_name`, `file_path` | A type alias was added (TS/TSX/Rust/Go) |
| `REMOVE_TYPE_ALIAS` | `symbol_name`, `file_path` | A type alias was removed |
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

Prompt Mode emits a `prompt_v10` schema with an `evidence` block showing
whether claims were verified against independently observed repository
changes:

```json
{
  "version": "0.11.0",
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

Pre/Post and Claims Mode (`--pre`/`--post`) omit the `mode` and `evidence`
fields; everything else is identical. Claim objects contain exactly:
`type`, `symbol_name`, `file_path`, `parent_class`, `line_number`,
`caller_name`, `called_name`, `confidence` — the free-text `explanation`
is accepted on input but never rendered in NoWreck's reports.

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
- The directories contain `.py`, `.js`, `.ts`, `.tsx`, `.rs`, or `.go` files
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

---

*NoWreck v0.11.0 — August 2026*
