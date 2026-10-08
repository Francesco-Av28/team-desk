---
name: team-desk
description: Set up a team-desk agent team for the current project - interview the user, write team.json (lead + members, each with a work type, optional skill, owned paths, dependencies, budget) and generate the agents. Use when the user asks to create, edit or review an agent team, or says "team-desk".
---

# team-desk: team interview

You help the user define the agent team for THIS project and write `team.json`. You do not start the team: the user runs `team-desk up` from a Linux/WSL terminal.

## 1. Look before asking
- If `team.json` exists, read it and run `team-desk check`: you are editing an existing team.
- Otherwise run `team-desk -C . init --propose --yes --dry-run` if available, or read the project tree (top level only) and list the installed skills (`~/.claude/skills/*/SKILL.md` and `.claude/skills/*/SKILL.md`, name + description, skip skills switched off in `skillOverrides`).
- Spend at most 5 tool calls on this. Do not read large files.

## 2. Interview (AskUserQuestion, max 4 questions per call, clickable options)
Ask only what you cannot infer. Typical blocks:
1. Goal of the team and what "done" looks like.
2. Members: propose 2-4 members (recommend max 4). For each: name, work type (`research` haiku, `design`/`doc`/`review` sonnet, `code` opus), and either a free-text role, a skill from the list, or both.
3. Order: which member waits for which (`after`), and which paths each one owns (`owns`, globs like `web/**`).
4. Budget: total weighted tokens (default 5,000,000), max active at once (default 2), turns per member (default 25), web fetches (default 10, 0 for members that need no web).
Show the final team as a table and get an explicit ok before writing.

## 3. Write and generate
Write `team.json` (schema below), then run `team-desk gen` and show its output (warnings included).

```json
{
  "project": "name",
  "leader": {"model": "opus"},
  "budget": {"total_tokens": 5000000, "max_active": 2, "checkpoints": [0.5, 0.8], "max_turns": 25, "max_fetches": 10},
  "members": [
    {"name": "research", "work": "research", "role": "...", "owns": ["docs/research/**"]},
    {"name": "build", "work": "code", "skill": "some-skill", "role": "...", "after": ["research"], "owns": ["src/**"],
     "inputs": ["docs/research/brief.md"], "max_turns": 40}
  ]
}
```

Rules: names are lowercase-dashed; every member needs `role` or `skill`; `model` and `tools` default from `work` and are overridden only if the user asks.

## 4. Hand over
Tell the user, in their language:
- `team-desk up` starts the lead in tmux (Linux/WSL); the lead asks before spawning each member.
- `team-desk status`, `team-desk cost`, `team-desk dash`, `team-desk stop`.
