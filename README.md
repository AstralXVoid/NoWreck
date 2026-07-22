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

## License

**FSL-1.1-MIT** (Functional Source License, Version 1.1, MIT Future License)

Source is fully visible — read it, learn from it, use it internally, run it, modify it for your own use. The one restriction: it can't be used to build a competing commercial product or service while this version is under FSL. Full terms are in [`LICENSE`](./LICENSE).

This version converts automatically to the plain **MIT license** two years after its initial release date (per FSL's standard terms — see the license file for the exact grant). No action is required for the conversion to take effect; it's automatic under the license terms.
