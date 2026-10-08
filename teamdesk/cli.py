"""team-desk command line."""

import argparse
import os
import sys

from . import __version__
from . import generate as G
from . import roster as R
from . import status as S
from . import tmux as T


def cmd_check(a):
    r = R.load(a.dir)
    for w in R.warnings(r, a.dir):
        print(f"warning: {w}")
    print(f"ok: {len(r['members'])} members, order: {' -> '.join(R.order(r))}")
    return r


def cmd_gen(a):
    r = cmd_check(a)
    for p in G.generate(r, a.dir):
        print(f"wrote {os.path.relpath(p, a.dir)}")


def cmd_init(a):
    path = os.path.join(a.dir, R.ROSTER_FILE)
    if os.path.exists(path):
        return cmd_gen(a)
    if a.propose:
        from . import propose
        data = propose.propose(a.dir)
        print(propose.describe(data))
        if not a.yes and input("\nWrite team.json with this team? [y/N] ").strip().lower() != "y":
            print("nothing written. Edit the proposal with /team-desk inside Claude Code, or rerun.")
            return
        R.save(data, a.dir)
        print(f"wrote {R.ROSTER_FILE}")
        return cmd_gen(a)
    print(f"no {R.ROSTER_FILE} here. Options:\n"
          "  team-desk init --propose   scan the project and skills, propose a team\n"
          "  /team-desk                 interview inside Claude Code (writes team.json)\n"
          "  copy examples/*/team.json  start from an example")
    return 1


def cmd_up(a):
    r = R.load(a.dir)
    G.generate(r, a.dir)
    name, created = T.up(a.dir, r["leader"]["model"])
    if created:
        from . import cost
        cost.mark_run_start(a.dir)
    print(("started" if created else "already running") + f": {name} (lead: {r['leader']['model']})")
    if a.no_attach:
        print(f"attach with: {T.attach_hint(name)}")
        return
    os.execvp("tmux", ["tmux", *T.attach_hint(name).split()[1:]])


def cmd_down(a):
    name = T.session_name(a.dir)
    if not a.yes and input(f"Kill session {name} and every teammate in it? [y/N] ").strip().lower() != "y":
        return 1
    for n in (name, T.session_name(a.dir, dash=True)):
        if T.down(n):
            print(f"killed {n}")


def cmd_stop(a):
    ids = T.stop(T.session_name(a.dir))
    print(f"sent Escape to {len(ids)} panes (lead first). Nothing was closed; check with: team-desk status")


def cmd_status(a):
    print(S.render(R.load(a.dir), a.dir))


def cmd_cost(a):
    from . import cost
    try:
        budget = R.load(a.dir)["budget"]
    except R.RosterError:
        budget = dict(R.DEFAULT_BUDGET)  # cost works on any project, even without team.json
    rep = cost.report(a.dir, since_hours=a.hours, all_sessions=a.all)
    print(cost.render(rep, budget, short=a.short))
    level = cost.threshold_hit(rep, budget)
    return 2 if level is not None else 0


def cmd_dash(a):
    name = T.dash(a.dir, a.interval)
    if a.no_attach:
        print(f"dashboard: {name}; attach with: {T.attach_hint(name)}")
        return
    os.execvp("tmux", ["tmux", *T.attach_hint(name).split()[1:]])


def cmd_tmux_conf(a):
    from . import install
    print(install.tmux_conf(apply=a.yes))


def main(argv=None):
    p = argparse.ArgumentParser(prog="team-desk", description="Claude Code agent teams on tmux, with rules and budgets.")
    p.add_argument("-C", "--dir", default=".", help="project directory (default: current)")
    p.add_argument("--version", action="version", version=f"team-desk {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create team.json (with --propose) and generate agents + lead rules")
    s.add_argument("--propose", action="store_true", help="scan project and skills, propose a team")
    s.add_argument("-y", "--yes", action="store_true")
    s.set_defaults(fn=cmd_init)
    sub.add_parser("check", help="validate team.json").set_defaults(fn=cmd_check)
    sub.add_parser("gen", help="regenerate .claude/agents/td-*.md and the CLAUDE.md block").set_defaults(fn=cmd_gen)

    s = sub.add_parser("up", help="start the team session (lead in pane 0) and attach")
    s.add_argument("--no-attach", action="store_true")
    s.set_defaults(fn=cmd_up)
    s = sub.add_parser("down", help="kill the team and dashboard sessions")
    s.add_argument("-y", "--yes", action="store_true")
    s.set_defaults(fn=cmd_down)
    sub.add_parser("stop", help="interrupt every Claude in the team session (Escape), close nothing").set_defaults(fn=cmd_stop)
    sub.add_parser("status", help="member states: waiting / ready / working / blocked / done").set_defaults(fn=cmd_status)

    s = sub.add_parser("cost", help="tokens per member and budget used (exit 2 past a checkpoint)")
    s.add_argument("--hours", type=float, default=None, help="only sessions active in the last N hours")
    s.add_argument("--all", action="store_true", help="every session of the project, not just since the last up")
    s.add_argument("--short", action="store_true")
    s.set_defaults(fn=cmd_cost)
    s = sub.add_parser("dash", help="separate tmux session with live status + cost")
    s.add_argument("--interval", type=int, default=30)
    s.add_argument("--no-attach", action="store_true")
    s.set_defaults(fn=cmd_dash)
    s = sub.add_parser("tmux-conf", help="show (or with -y install, with backup) the recommended tmux config")
    s.add_argument("-y", "--yes", action="store_true")
    s.set_defaults(fn=cmd_tmux_conf)

    a = p.parse_args(argv)
    try:
        rc = a.fn(a)
    except (R.RosterError, T.TmuxError) as e:
        print(f"team-desk: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return rc if isinstance(rc, int) else 0


if __name__ == "__main__":
    sys.exit(main())
