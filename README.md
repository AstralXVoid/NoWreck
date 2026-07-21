  +------------------------------------+
  |            NoWreck v0.1.0           |
  |    Deterministic AI Verifier        |
  +------------------------------------+

NoWreck is a **deterministic** verifier for AI coding assistants. When an AI
changes your code and explains what it did, NoWreck checks whether the
explanation matches reality — using structural AST analysis, not another
AI's opinion.

```
$ nowreck fix "Add email validation to auth.py"

  Summary
  ────────────────────
  ● 3 claims total
  ● 2 confirmed
  ● 1 contradicted

  CONFIRMED
  ✓ ADD_FUNCTION validate_email → auth.py
    Evidence: Function 'validate_email' was added in auth.py

  CONTRADICTED
  ✗ CALLS_FUNCTION validate_email → sanitize_input
    Evidence: No call to sanitize_input detected in validate_email's body
```

---

## What it catches

- **Hallucinated functions or classes** — the AI claims it added something
  that isn't there
- **Fake internal API calls** — the AI says it called a function it didn't
- **Explanation-vs-diff mismatches** — the AI describes a change that
  doesn't match the actual diff
- **Unexplained changes** — real modifications the AI never mentioned

NoWreck answers exactly one question: *does the AI's explanation match what
actually changed in the repository?* Nothing more, nothing less.

---

## Install

```bash
pipx install .
```

*(from a cloned copy of this repo — PyPI publishing coming later)*

Requires Python 3.10+. Installs `nowreck` as a system-wide command.

---

## Setup

NoWreck works with any **OpenAI-compatible** model endpoint — Groq,
DeepSeek, Ollama, LM Studio, OpenRouter, or OpenAI itself.

```bash
nowreck config set base_url https://api.groq.com/openai/v1
nowreck config set api_key        <your-api-key>
nowreck config set model          llama-3.3-70b-versatile
```

Or set the `NOWRECK_API_KEY` environment variable instead of storing it in
config.

---

## Quick start

```bash
# Prompt mode — NoWreck calls the model, gets claims, verifies them
nowreck fix "Add a rate-limiting decorator to api/client.py"

# Pre/Post mode — advanced: scan two snapshots manually
nowreck fix --pre ./repo-v1 --post ./repo-v2

# Pre/Post with claims — verify specific claims against a diff
nowreck fix --pre ./before --post ./after --claims '{"claims": [...]}'

# JSON output for CI pipelines
nowreck fix "Add validation to auth.py" --json

# View or change configuration
nowreck config show
nowreck config set base_url https://api.openai.com/v1
```

---

## Command reference

| Command | Description |
|---------|-------------|
| `nowreck` | Show help / usage |
| `nowreck --version` | Show version |
| `nowreck fix "<prompt>"` | **Prompt mode** — describe a change in natural language. NoWreck calls the configured model, gets a diff + claims, and verifies them automatically. |
| `nowreck fix --pre PATH --post PATH` | **Pre/Post mode** — scan two directory snapshots and detect structural changes. Add `--claims JSON` to verify specific claims against the detected changes. |
| `nowreck fix --json` | Output structured JSON instead of coloured terminal text (for CI). Works with both prompt and pre/post modes. |
| `nowreck fix --no-colour` | Disable coloured terminal output. |
| `nowreck config show` | Display current configuration. |
| `nowreck config set <key> <value>` | Set a configuration value. Keys: `api_key`, `model`, `base_url`, `temperature`, `max_retries`. |

---

## How it works

```
┌─────────────────────────────────────────────────────────┐
│                   Prompt mode                           │
│                                                         │
│  Your prompt ──► AI model ──► diff + claims             │
│                                   │                     │
│                                   ▼                     │
│  Pre-scan ──► Symbol index ──► Change Detector          │
│  Post-scan ──► Symbol index ────────┘                   │
│                                         │               │
│  Claims ──► Claim Verifier ◄────────────┘               │
│                  │     pure comparison — no AI judgment │
│                  ▼                                      │
│          Verification Report                            │
│   ✓ CONFIRMED  ✗ CONTRADICTED  ? UNVERIFIABLE           │
└─────────────────────────────────────────────────────────┘
```

NoWreck's verification pipeline has three stages:

1. **Scan** — recursively discovers all `.py` files in both snapshots,
   parses each with `ast.parse`, and builds a symbol index of every
   function, class, and method.

2. **Detect** — compares the pre and post symbol indices to find
   structural changes: added/removed functions, classes, files, and new
   function calls. This produces the **single source of truth** — a
   `list[DetectedChange]` that the verifier references exclusively.

3. **Verify** — for each claim from the AI model, the verifier looks for
   a matching `DetectedChange`. If one exists with the same type and
   identity fields → **CONFIRMED**. If a contradicting change exists
   (e.g., claim says "added" but detection shows "removed") →
   **CONTRADICTED**. If nothing matches → **UNVERIFIABLE**.

The verifier never parses AST, never queries the symbol index, and never
applies AI judgment. Its decisions are purely field-based comparison.

---

## Claim types (MVP)

| Claim type | What it means | Verified by |
|------------|---------------|-------------|
| `ADD_FUNCTION` | A function was added | Structural existence check |
| `REMOVE_FUNCTION` | A function was removed | Structural existence check |
| `ADD_CLASS` | A class was added | Structural existence check |
| `REMOVE_CLASS` | A class was removed | Structural existence check |
| `FILE_CREATED` | A new file appeared | File-list diff |
| `FILE_DELETED` | A file was removed | File-list diff |
| `CALLS_FUNCTION` | A function now calls another | AST call-site detection |

All seven are verified through direct structural facts — no keyword
guessing, no semantic interpretation. If NoWreck can't determine something
with certainty, it reports `UNVERIFIABLE` rather than guessing.

---

## On confidence

Every result includes a confidence score. This reflects NoWreck's certainty
in its deterministic check — not a claim that the underlying code is
bug-free.

- **CONFIRMED** at 100% — the structural fact was found and matched
- **CONTRADICTED** at 100% — the opposite structural fact was found
- **UNVERIFIABLE** at 50% — no matching fact exists either way

A `CALLS_FUNCTION` check that finds no matching call is just as certain as
one that finds a match. An absence, confirmed by direct inspection, is not a
weaker fact than a presence.

This does **not** mean NoWreck is infallible. Static analysis has real,
documented limits — see [Limitations](#limitations) below.

---

## Comparison

| Tool | What it does | Overlaps with NoWreck? |
|------|-------------|------------------------|
| Cursor / Claude Code / Copilot | Generate and edit code | **No** — NoWreck verifies, doesn't generate |
| CodeRabbit / Qodo / Greptile | AI review of a diff's quality | **No** — subjective AI judgment, not deterministic fact-checking |
| Agent Verifier (aurite-ai) | AI agent skill for code quality/security | **No** — checks code quality, not claim truthfulness |
| slopcheck / slop-scan | Check third-party package names against registries | **No** — different hallucination category |
| ESLint / Ruff / Black | Linting and formatting | **No** — syntax/code style, not structural verification |

NoWreck occupies a unique niche: **deterministic verification of AI claims
about code changes.** No other tool does this.

---

## Limitations

- **Python only** for now
- **Cannot see through dynamic behavior** — `exec()`, `eval()`, dynamic
  imports, `getattr()`/`setattr()` with dynamic arguments, metaclasses,
  monkey-patching, and reflection will all yield `UNVERIFIABLE`
- **Simple calls only** — detects `name()` calls, not `obj.method()` or
  chained calls
- **No cross-file resolution** beyond direct name matching
- **No semantic analysis** — it verifies structure, not intent

---

## Roadmap

- Interactive terminal picker for non-CLI users
- `--verbose` mode showing full deterministic evidence per claim
- Additional model providers (Anthropic, Gemini)
- Caching for large repositories
- CI/CD integration

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
