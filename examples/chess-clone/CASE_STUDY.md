# Case study: 36.6M tokens in one hour

The project: an original rebuild of a chess platform with the [Replica](https://github.com/Jakeschincariol/replica-skill)
skill pipeline (recon → architect → design → build → backend → test → …), run as a Claude Code agent team on tmux.
No code of the clone is published here: only the configuration and the measurements.

## Session 1: recon, two teammates (in-process)

| Member | Model | Turns | Tokens (raw) | Notes |
|---|---|---|---|---|
| ui-scout | Sonnet | 27 | 1.51M | screens, flows, components, data model |
| market-scout | Sonnet | 48 | 3.18M | feature matrix, pricing, review mining via scraping |

Raw tokens are **82–88% cache reads**: every turn re-reads the whole context, which started at ~40k tokens before
any work (system prompt, tool schemas, CLAUDE.md, memory index). Cost ≈ turns × context size. Five separate
`TaskUpdate` calls at the end cost ~350–450k tokens per member just to tick boxes.

## Session 2: architect → design → …, tmux, no rules

| Member | Model | Turns | Raw | Weighted | Share |
|---|---|---|---|---|---|
| lead (architect) | Opus | 120 | 16.11M | 3.07M | 41% |
| entrepreneur | Opus | 96 | 8.23M | 1.74M | 23% |
| design | Opus | 68 | 4.85M | 1.15M | 15% |
| brand (interrupted) | Opus | 51 | 3.44M | 0.64M | 8% |
| build (interrupted, no files) | Opus | 40 | 2.57M | 0.56M | 7% |
| 5 stages started too early | Opus | 32 | 1.41M | 0.40M | 5% |
| **Total** | | **407** | **36.61M** | **7.55M** | |

Weighted = input 1×, cache read 0.1×, cache write 1.25×, output 5×. Numbers from `team-desk cost --all` on the
real transcripts (they match a manual analysis done before team-desk existed).

### What went wrong

1. **Every teammate ran on Opus.** They were spawned as `general-purpose` agents, which inherit the lead's model.
2. **The lead wrote its own launcher** that opened all nine stages at once; backend, test, diff, launch and deploy
   polled for inputs that did not exist yet (≈11% of the spend, including the first idle runs of the others).
3. **The lead's context reached ~190k tokens** over 120 turns: it read and wrote large documents itself.
4. **A member repeated work the user had switched off** (review mining, 517 reviews in a CSV).
5. **Stages ran out of order**: build started in parallel with brand and produced nothing in 40 turns.
6. **Ctrl+Z suspended the lead** inside a pane with no shell, and arrow keys printed `^[[B` until it was resumed.

### What was still good

Architecture (25 KB), a tested SQL schema (39 KB), and a complete design system (tokens, ~40 component specs,
0 contrast failures on 120 pairs). The problem was cost and control, not quality.

## The same pipeline with team-desk

[`team.json`](team.json) encodes the rules decided after session 2:

| Rule | Addresses |
|---|---|
| recon Haiku · design/test Sonnet · build Opus, `general-purpose` forbidden | 1 |
| `after` chain recon → design → build → test, `max_active: 2`, nothing starts early | 2, 5 |
| lead coordinates only, keeps context lean, asks before each spawn | 3 |
| market stages not in the roster; skills switched off | 4 |
| 25 turns, 10 fetches (0 for design/test), no scraping | 4 |
| `owns` per member, enforced by hook; build owns the app folder outside the project | — |
| budget 5M weighted tokens, checkpoints at 50% and 80% | all |
| lead in a shell pane, optional tmux config maps Ctrl+Z to undo | 6 |

Measurements of the next sessions with team-desk will be added here.
