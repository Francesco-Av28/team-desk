# Changelog

## 0.1.0 - 2026-10-08

First release.

- `team.json` roster: members with work type (model + tool profile), role and/or skill, `owns`, `after`, `inputs`, per-member limits; validation with dependency-cycle detection.
- `team-desk gen`: `.claude/agents/td-*.md`, lead rules block in `CLAUDE.md`, owns guard hook in `.claude/settings.json`.
- `team-desk up / down / stop / status / dash` on tmux; lead in a shell pane, 60% main pane, teammates on the right.
- `team-desk cost`: per-member turns and weighted tokens from Claude Code transcripts, budget checkpoints (exit code 2 past a checkpoint).
- `team-desk init --propose`: proposes a research → design → code → review team, binding the best-matching installed skills.
- `/team-desk` skill: interview inside Claude Code that writes `team.json`.
- Optional tmux config (Ctrl+Z mapped to undo, mouse, layout) installed with a backup.
