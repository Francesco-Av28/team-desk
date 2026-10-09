# Changelog

## 0.2.0 - 2026-10-09

Global regime for every subagent, in every project.

- `team-desk global init | status | on | off | remove`: one rules file (`~/.claude/team-desk/rules.json`), three governed agents in `~/.claude/agents/` (td-research on Haiku, td-doc on Sonnet, td-code on Opus) and a global `PreToolUse` hook, installed with a backup of `settings.json`.
- `hooks/td_guard.py`: refuses spawning non-`td-*` agents (e.g. `general-purpose`); per agent (by `agent_id`) enforces tool allowlist, 40 actions, 15 web calls for research, blocked domains (LinkedIn & co.), no network commands without web access, write scope (`tmp/` or project) and protected paths. Kill switch: `TEAMDESK_OFF=1` or `enabled: false`. Errors in the guard never block work.
- `team-desk cost --global`: turns and tokens of every subagent in every project, with alerts.
- Tested live with `claude -p` (Claude Code 2.1.295): general-purpose refused, LinkedIn blocked, web limit hit, writes outside `tmp/` blocked.

## 0.1.0 - 2026-10-08

First release.

- `team.json` roster: members with work type (model + tool profile), role and/or skill, `owns`, `after`, `inputs`, per-member limits; validation with dependency-cycle detection.
- `team-desk gen`: `.claude/agents/td-*.md`, lead rules block in `CLAUDE.md`, owns guard hook in `.claude/settings.json`.
- `team-desk up / down / stop / status / dash` on tmux; lead in a shell pane, 60% main pane, teammates on the right.
- `team-desk cost`: per-member turns and weighted tokens from Claude Code transcripts, budget checkpoints (exit code 2 past a checkpoint).
- `team-desk init --propose`: proposes a research → design → code → review team, binding the best-matching installed skills.
- `/team-desk` skill: interview inside Claude Code that writes `team.json`.
- Optional tmux config (Ctrl+Z mapped to undo, mouse, layout) installed with a backup.
