# CLAUDE.md

The repository guide for every coding agent is `AGENTS.md`; it is imported here so
Claude Code loads it in full. Edit conventions there, not in this file. This file
holds only what is specific to Claude Code.

@AGENTS.md

## Claude Code specifics

### Subagent models

Pick the subagent model for the task; never run everything on the largest
model. Pass `model` explicitly on every `Agent` call:

- `haiku`: search, file discovery, mechanical work (renames, checking docs
  against code, collecting test output).
- `sonnet`: routine implementation, functional and end-to-end testing,
  regression runs, convention surveys.
- `opus`: design, security and isolation reasoning, adversarial review, where a
  wrong answer is expensive.

### Codex as a subagent

The Codex CLI (`@openai/codex`) is installed and authenticated on some machines,
not on cloud sessions. Probe once per session with
`command -v codex && codex login status`; if it is missing or prints
`Not logged in`, use Claude subagents only, and do not install it, `npx` it or
retry. When it is authenticated, treat it as a first-class subagent and run it in
parallel with Claude subagents, each on its own slice, with the same brief
discipline and the same per-slice verification:

- Read-only slices (verification, surveys, review):
  `codex exec -s read-only "<brief>"`, and
  `codex exec -s read-only review --base main` (or `--uncommitted`) for a diff
  review. A second model's independent read is the main value here, so route
  review and fact-check slices to Codex first.
- Write slices (an isolated implementation or test-fixing task): give Codex
  its own checkout, never the one this session is editing:
  `git worktree add ../<repo>-codex-<slice> <branch>`, then
  `codex exec -s workspace-write -C ../<repo>-codex-<slice> "<brief>"`.
  Review its diff and run the repo checks before merging it into the branch.
- Never pass `danger-full-access`, `--approve-for-me` or
  `--dangerously-bypass-approvals-and-sandbox` here.
