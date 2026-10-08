"""Load, validate and normalise a team.json roster."""

import json
import os
import re

ROSTER_FILE = "team.json"
STATE_DIR = ".team-desk"
MODELS = ("haiku", "sonnet", "opus")
RECOMMENDED_MAX_MEMBERS = 4

# Work type -> default model and tool profile. A member can override both.
PROFILES = {
    "research": {
        "model": "haiku",
        "tools": ["Read", "Glob", "Grep", "Write", "WebFetch", "WebSearch", "Skill", "SendMessage"],
    },
    "design": {
        "model": "sonnet",
        "tools": ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill", "SendMessage"],
    },
    "doc": {
        "model": "sonnet",
        "tools": ["Read", "Write", "Edit", "Glob", "Grep", "Skill", "SendMessage"],
    },
    "code": {
        "model": "opus",
        "tools": ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill", "SendMessage"],
    },
    "review": {
        "model": "sonnet",
        "tools": ["Read", "Glob", "Grep", "Bash", "Write", "SendMessage"],
    },
}

DEFAULT_BUDGET = {
    "total_tokens": 5_000_000,  # weighted tokens, see cost.py
    "max_active": 2,
    "checkpoints": [0.5, 0.8],
    "max_turns": 25,
    "max_fetches": 10,
}

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")


class RosterError(ValueError):
    pass


def load(project_dir="."):
    path = os.path.join(project_dir, ROSTER_FILE)
    if not os.path.exists(path):
        raise RosterError(f"{ROSTER_FILE} not found in {os.path.abspath(project_dir)} (run: team-desk init)")
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise RosterError(f"{ROSTER_FILE}: invalid JSON ({e})") from e
    return normalise(data)


def save(data, project_dir="."):
    path = os.path.join(project_dir, ROSTER_FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return path


def normalise(data):
    """Validate the roster and fill defaults. Returns a new dict; raises RosterError."""
    if not isinstance(data, dict):
        raise RosterError("roster must be a JSON object")
    out = {
        "project": data.get("project") or "project",
        "leader": {"model": "opus", **(data.get("leader") or {})},
        "budget": {**DEFAULT_BUDGET, **(data.get("budget") or {})},
        "members": [],
    }
    if out["leader"]["model"] not in MODELS:
        raise RosterError(f"leader.model must be one of {MODELS}")
    b = out["budget"]
    if not (isinstance(b["max_active"], int) and b["max_active"] >= 1):
        raise RosterError("budget.max_active must be an integer >= 1")
    if any(not (0 < c < 1) for c in b["checkpoints"]):
        raise RosterError("budget.checkpoints must be fractions between 0 and 1")

    members = data.get("members") or []
    if not members:
        raise RosterError("roster needs at least one member")
    names = set()
    for i, m in enumerate(members):
        where = f"members[{i}]"
        name = m.get("name", "")
        if not NAME_RE.match(name):
            raise RosterError(f"{where}.name '{name}' must be lowercase letters, digits, dashes (max 31)")
        if name in names:
            raise RosterError(f"duplicate member name '{name}'")
        names.add(name)
        work = m.get("work")
        if work not in PROFILES:
            raise RosterError(f"{where}.work must be one of {sorted(PROFILES)}")
        if not (m.get("role") or m.get("skill")):
            raise RosterError(f"{where} needs a 'role' description, a 'skill', or both")
        prof = PROFILES[work]
        model = m.get("model", prof["model"])
        if model not in MODELS:
            raise RosterError(f"{where}.model must be one of {MODELS}")
        out["members"].append({
            "name": name,
            "work": work,
            "role": m.get("role", ""),
            "skill": m.get("skill"),
            "model": model,
            "tools": m.get("tools", prof["tools"]),
            "owns": m.get("owns", []),
            "after": m.get("after", []),
            "inputs": m.get("inputs", []),
            "max_turns": m.get("max_turns", b["max_turns"]),
            "max_fetches": m.get("max_fetches", b["max_fetches"]),
        })

    for m in out["members"]:
        for dep in m["after"]:
            if dep not in names:
                raise RosterError(f"member '{m['name']}' depends on unknown member '{dep}'")
            if dep == m["name"]:
                raise RosterError(f"member '{m['name']}' depends on itself")
    order(out)  # raises on cycles
    return out


def order(roster):
    """Topological order of member names; raises RosterError on a dependency cycle."""
    deps = {m["name"]: set(m["after"]) for m in roster["members"]}
    result, done = [], set()
    while deps:
        ready = sorted(n for n, d in deps.items() if d <= done)
        if not ready:
            raise RosterError(f"dependency cycle among: {', '.join(sorted(deps))}")
        for n in ready:
            result.append(n)
            done.add(n)
            del deps[n]
    return result


def skill_dirs(project_dir="."):
    """Where skills can live: the user's skills first, then the project's."""
    return [os.path.expanduser("~/.claude/skills"), os.path.join(project_dir, ".claude", "skills")]


def warnings(roster, project_dir=".", dirs=None):
    """Non-fatal advice: missing skills, large rosters."""
    dirs = dirs or skill_dirs(project_dir)
    out = []
    if len(roster["members"]) > RECOMMENDED_MAX_MEMBERS:
        out.append(f"{len(roster['members'])} members: recommended max is {RECOMMENDED_MAX_MEMBERS}")
    for m in roster["members"]:
        if m["skill"] and not any(os.path.isdir(os.path.join(d, m["skill"])) for d in dirs):
            out.append(f"member '{m['name']}': skill '{m['skill']}' not found in {' or '.join(dirs)}")
        if not m["owns"]:
            out.append(f"member '{m['name']}': no 'owns' paths, it may write anywhere")
    return out
