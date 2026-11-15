# Refresh agent docs: plan

Design: `docs/superpowers/specs/2026-11-15-refresh-agent-docs-design.md`.

| # | Task | Files | Done check | Parallel |
|---|---|---|---|---|
| T1 | Demo GIF recorder + recording | `scripts/record_readme_demo.py`, `docs/assets/readme-demo.gif` | script runs end to end against a live SQLite stack; GIF ≤ 5 MB; frames reviewed | independent (subagent) |
| T2 | AGENTS.md from CLAUDE.md, with the fact-check fixes and trims; CLAUDE.md becomes `@AGENTS.md` + Claude specifics | `AGENTS.md`, `CLAUDE.md` | every rule from the old file is in one of the two; `make ci-doc-paths` | independent of T1 |
| T3 | Doc-path checker scans AGENTS.md; comments citing CLAUDE.md sections | `scripts/check_doc_paths.py`, cited tests/comments, `docs/framework/invalidation.md` | `make ci-doc-paths`; a broken path in AGENTS.md fails it | after T2 |
| T4 | README restructure (embeds the GIF) | `README.md` | every fact-check item addressed; `make ci-doc-paths` | after T1 for the GIF path |
| T5 | CHANGELOG `[Unreleased]` docs entry; `make lint` | `CHANGELOG.md` | `make lint` green | last |

TDD note: this is a docs change. The executable checks are the doc-path checker (T3 adds AGENTS.md
to it and is proven by a deliberately broken path) and the recorder script's own run (T1).
