# team-desk

[![CI](https://github.com/Francesco-Av28/team-desk/actions/workflows/ci.yml/badge.svg)](https://github.com/Francesco-Av28/team-desk/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

**Run Claude Code agent teams on tmux, with rules and a budget.** One lead coordinates; each member does one job,
on the model that fits it, inside the files it owns, after the members it depends on.

*[Leggi in italiano](README.it.md)*

![team-desk demo](docs/demo.gif)

## Why

My first agent-team session burned **36.6M tokens in one hour**. Every teammate ran on the lead's model (Opus),
the lead pre-launched nine pipeline stages that sat waiting, and a "market research" member scraped 517 reviews
with no limit. The [case study](examples/chess-clone/CASE_STUDY.md) has the numbers.

team-desk turns the lessons into defaults:

| Problem seen | team-desk default |
|---|---|
| Teammates inherit the lead's expensive model | Model per **work type**: `research` Haiku, `design`/`doc`/`review` Sonnet, `code` Opus. `general-purpose` teammates forbidden |
| Stages launched before their inputs exist | `after` dependencies; a member starts only when its upstream `.done` marker exists |
| Too many members at once | `max_active` (default 2) |
| Unbounded research and scraping | 25 turns and 10 web fetches per member, no scraping |
| Members overwriting each other | `owns` globs per member, enforced by a PreToolUse hook |
| Nobody knows the spend until it's too late | `team-desk cost` per member, checkpoints at 50% / 80% of the budget |
| Ctrl+Z (Windows "undo") suspends Claude in a pane | optional tmux config maps it to undo |

## Requirements

Linux, WSL2 or macOS · `python3` (stdlib only) · `tmux` · [Claude Code](https://docs.claude.com/en/docs/claude-code) with
agent teams (team-desk sets `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` for its own session).

## Install

```bash
git clone https://github.com/Francesco-Av28/team-desk.git
cd team-desk && ./install.sh            # links ~/.local/bin/team-desk and ~/.claude/skills/team-desk
team-desk tmux-conf                     # optional: shows the tmux config; -y installs it (with a backup)
```

## Quick start

```bash
cd my-project
team-desk init --propose     # scans the project and your skills, proposes a team, writes team.json
# or, inside Claude Code: /team-desk   (interview with clickable options)
team-desk up                 # tmux session: lead on the left (60%), members appear on the right
```

The lead asks you before spawning each member. Meanwhile, from another terminal:

```bash
team-desk status    # waiting / ready / working / blocked / done, and who is next
team-desk cost      # turns and tokens per member, share of the budget
team-desk dash      # a separate tmux session refreshing status + cost every 30 s
team-desk stop      # Escape in every pane (lead first): stops work, closes nothing
team-desk down      # kill the team and dashboard sessions
```

## team.json

```json
{
  "project": "landing",
  "leader": {"model": "opus"},
  "budget": {"total_tokens": 5000000, "max_active": 2, "checkpoints": [0.5, 0.8], "max_turns": 25, "max_fetches": 10},
  "members": [
    {"name": "research", "work": "research", "role": "Brief on 3 competitor landing pages.", "owns": ["docs/research/**"]},
    {"name": "design", "work": "design", "skill": "my-design-skill", "after": ["research"], "owns": ["docs/design/**"]},
    {"name": "build", "work": "code", "role": "Build the page.", "after": ["design"], "owns": ["src/**"], "max_turns": 40}
  ]
}
```

| Field | Meaning |
|---|---|
| `work` | `research`, `design`, `doc`, `code` or `review`: sets the default model and tool allowlist |
| `role` / `skill` | a free-text job, a skill to follow (from `~/.claude/skills` or `.claude/skills`), or both |
| `owns` | globs the member may write (relative to the project, or absolute for code kept elsewhere) |
| `after` | members that must be `.done` first |
| `inputs` | files the member should read first |
| `model`, `tools`, `max_turns`, `max_fetches` | per-member overrides |

`total_tokens` is in **weighted tokens**: input 1×, cache read 0.1×, cache write 1.25×, output 5× (Anthropic's price
ratios). It measures relative spend for API and subscription users alike; it is not a currency amount.

## What gets generated

`team-desk gen` (also run by `init` and `up`) writes:

- `.claude/agents/td-<member>.md`: one agent per member (model, tools, `maxTurns`, job, owned files, limits, how to report);
- a rules block for the lead in `CLAUDE.md` (between `team-desk` markers, the rest of the file is untouched);
- a PreToolUse hook in `.claude/settings.json` that blocks a member's writes outside `owns` (other settings are kept);
- `.team-desk/status/`, where members write `<name>.done` (summary, files, verification output) or `<name>.blocked`.

## How it works

```
team-desk up
  └─ tmux session td-<project>  (CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1)
       ├─ pane 0: shell → claude --model <lead> --settings {"teammateMode":"tmux"}
       │            reads CLAUDE.md rules: spawn only td-* agents, max_active, after, checkpoints
       └─ panes 1..n: teammates (td-<member>), each with its own model, tools and maxTurns
            └─ PreToolUse hook → hooks/guard_owns.py: member from agent_type, block writes outside owns
```

The lead runs inside a shell, not as the pane's command: if Claude exits or is suspended, the shell is still there.

## Limits (v0.1)

- Turn limits rely on the agent `maxTurns` field; fetch limits and "no scraping" are instructions, not enforced.
- The `owns` hook checks file-writing tools (Write, Edit, MultiEdit, NotebookEdit), not shell commands.
- Hooks declared inside an agent file were not run in tests with Claude Code 2.1.293, so the guard is a project-level hook.
- Agent teams are an experimental Claude Code feature; behaviour may change between versions.

## Development

```bash
python3 -m unittest discover -s tests -v
```

## License and name

Code: [Apache License 2.0](LICENSE). The name "team-desk" and its logo are not covered by the license (see [NOTICE](NOTICE)).
