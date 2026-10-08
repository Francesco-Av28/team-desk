"""Member states from .team-desk/status markers, running teammate processes and the dependency graph."""

import os
import subprocess

from . import roster as R

WAITING, READY, WORKING, BLOCKED, DONE = "waiting", "ready", "working", "blocked", "done"
ICONS = {WAITING: "·", READY: "▶", WORKING: "⚙", BLOCKED: "⛔", DONE: "✔"}


def running_agent_names():
    """Names passed as --agent-name to running Claude Code teammate processes."""
    try:
        out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if "--agent-name" in parts:
            i = parts.index("--agent-name")
            if i + 1 < len(parts):
                names.add(parts[i + 1])
    return names


def member_states(roster, project_dir=".", running=None):
    status_dir = os.path.join(project_dir, R.STATE_DIR, "status")
    running = running_agent_names() if running is None else running
    exists = lambda n, kind: os.path.exists(os.path.join(status_dir, f"{n}.{kind}"))
    done = {m["name"] for m in roster["members"] if exists(m["name"], "done")}
    states = {}
    for name in R.order(roster):
        m = next(x for x in roster["members"] if x["name"] == name)
        if name in done:
            states[name] = DONE
        elif exists(name, "blocked"):
            states[name] = BLOCKED
        elif name in running or ("td-" + name) in running:
            states[name] = WORKING
        elif set(m["after"]) <= done:
            states[name] = READY
        else:
            states[name] = WAITING
    return states


def summary(path, lines=3):
    try:
        with open(path, encoding="utf-8") as f:
            body = [l.rstrip() for l in f if l.strip()]
    except OSError:
        return []
    return body[:lines]


def render(roster, project_dir=".", running=None):
    states = member_states(roster, project_dir, running)
    by_name = {m["name"]: m for m in roster["members"]}
    active = sum(1 for s in states.values() if s == WORKING)
    out = [f"team-desk · {roster['project']} · active {active}/{roster['budget']['max_active']}", ""]
    for name, st in states.items():
        m = by_name[name]
        after = f" after {', '.join(m['after'])}" if m["after"] else ""
        out.append(f" {ICONS[st]} {name:<14} {st:<8} {m['model']:<7} {m['work']:<9}{after}")
        if st in (DONE, BLOCKED):
            marker = os.path.join(project_dir, R.STATE_DIR, "status", f"{name}.{st if st == BLOCKED else 'done'}")
            out += [f"     {l[:90]}" for l in summary(marker, 2)]
    ready = [n for n, s in states.items() if s == READY]
    if ready:
        slots = roster["budget"]["max_active"] - active
        out += ["", f"next: {', '.join(ready[:max(slots, 0)]) or '(no free slot)'}"]
    elif all(s == DONE for s in states.values()):
        out += ["", "all members done"]
    return "\n".join(out)
