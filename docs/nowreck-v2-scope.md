# NoWreck — v2 Scope (Terminal Picker Only)

**Status:** Draft. Local development only — not published, not merged into the public repo, until proven and deliberately released.

## Principle

Same discipline as v1: one small thing at a time, proven before expanding. This document exists specifically to prevent v2 from sprawling the way v1 almost did (remember the JSON flag, the multi-provider suggestion, the "reasoning mode" idea — all caught and deferred). v2 starts with exactly one feature. Nothing else gets added to this scope without a deliberate decision, the same way nothing got added to v1 without one.

## What's in scope for this v2 increment

**One feature only: an interactive terminal picker, accessed via `nowreck --interactive`.**

Not a replacement for the existing CLI — an additional, optional entry point for people less comfortable typing full commands and flags. The expert CLI (`nowreck fix "<prompt>"`, `nowreck config set/show`) stays exactly as it is, unchanged, always available.

### Design (based on researched CLI UX principles, not guesswork)

```
nowreck --interactive

? What would you like to do?
  > Verify an AI code change
    Set up or change your API key
    View last report
    Exit

? Describe the change you want the AI to make:
  > [text input]

  ✓ Endpoint configured (confirmed reachable)
  Running verification...
```

Core rules for this feature:
- **Never replaces non-interactive mode** — both exist side by side permanently, per standard CLI UX guidance: people who learn the tool tend to move to direct commands, and scripting/automation needs the non-interactive path regardless.
- **Validates input as it's entered, not after submission** — e.g., if an endpoint or file path is entered, check it immediately rather than letting someone complete the whole flow and fail at the end.
- **Doubles as onboarding** — the menu itself teaches a new user what the tool can do, rather than requiring them to discover flags on their own.
- **Under the hood, calls the exact same verification pipeline as the CLI path** — the picker is only a different way of collecting input and displaying output. It must not duplicate or reimplement any part of scanning, detection, claim parsing, or verification. Same source of truth, same code path, just a friendlier front door.

## What this inherits from v1, unconditionally

Every core constraint from the frozen spec's §2 applies here without exception:
- Python only, CLI-first
- No code execution, no test execution, no sandboxing
- No autonomous agent behavior
- No second AI judging the first AI's correctness
- Deterministic verification only — the picker doesn't change what gets verified or how, only how input/output is presented
- Human remains final authority — nothing is auto-applied or auto-merged through the picker any more than through the direct CLI

## Do Not Build Yet (v2 edition)

Same spirit as the frozen spec's §12 — these are real ideas, discussed, deliberately deferred, not forgotten:

- JS/TypeScript or any other language support
- Multi-provider support beyond OpenAI-compatible endpoints (Anthropic, Gemini directly)
- Caching, CI/CD integration, JSON output mode
- Any AI-generated "reasoning" or self-explanation — deterministic evidence display only, if that's ever added
- Any GUI, web dashboard, or separate application — terminal only
- Advanced rename detection, deep import resolution, semantic analysis
- Publishing/merging this into the public repo before it's actually tested and proven, the same way v1 wasn't published until it was verified end-to-end

## Implementation notes

- Likely library: `questionary` or `InquirerPy` for the interactive prompts (Python ecosystem, well-established for exactly this use case)
- Build and test entirely in the local `nowreck-v1-backup`-adjacent development copy, per the established local workflow — no git remote pushes until this is deliberately ready to share
- Definition of done: the picker successfully walks a first-time, non-technical-feeling user through setting up config and running one real verification, with no need to read documentation first

## Explicitly not a roadmap

This document is not "NoWreck v2" as a big-picture plan. It covers exactly one feature. When this is done and proven, the next v2 increment (if any) gets its own equally narrow scoping conversation — not an expansion of this document into a wishlist.
