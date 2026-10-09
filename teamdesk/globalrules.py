"""Global regime for every subagent: one rules file, three profiles, hard limits.

The rules live in ~/.claude/team-desk/rules.json (override with TEAMDESK_HOME). Missing keys fall back to
DEFAULT_RULES, so an empty or partial file is valid. The guard hook (hooks/td_guard.py) reads them on every
tool call; `team-desk global init` writes the file and the global agents.
"""

import copy
import fnmatch
import json
import os
import re

AGENT_PREFIX = "td-"

DEFAULT_RULES = {
    "enabled": True,
    # Agent types the main session may spawn. Anything else (general-purpose, Explore, ...) is refused.
    "allowed_agent_types": ["td-*"],
    # Domains no subagent may fetch or touch from the shell (bulk scraping risks the user's own accounts/IP).
    "blocked_domains": ["linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com", "tiktok.com"],
    # Default profile for td-* agents whose profile can't be resolved.
    "default_profile": "research",
    "profiles": {
        "research": {
            "description": "Web research: searches, reads pages, writes findings to tmp/.",
            "model": "haiku",
            "tools": ["Read", "Glob", "Grep", "Write", "WebFetch", "WebSearch"],
            "max_actions": 40, "max_web": 15, "max_turns": 25,
            "write": "tmp",
        },
        "doc": {
            "description": "Writing and documents: drafts, summaries, reports in tmp/.",
            "model": "sonnet",
            "tools": ["Read", "Glob", "Grep", "Write", "Edit"],
            "max_actions": 40, "max_web": 0, "max_turns": 25,
            "write": "tmp",
        },
        "code": {
            "description": "Code: edits project files, runs builds and tests, no web access.",
            "model": "opus",
            "tools": ["Read", "Glob", "Grep", "Write", "Edit", "Bash"],
            "max_actions": 40, "max_web": 0, "max_turns": 25,
            "write": "project",
        },
    },
    # Paths never writable by any subagent (relative to the project or absolute, glob).
    "protected_paths": [".claude/**", ".git/**", "**/.env", "**/*.pem", "~/.claude/**"],
    # Folder inside the project used by profiles with write = "tmp".
    "tmp_dir": "tmp",
}

WEB_TOOLS = {"WebFetch", "WebSearch"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SPAWN_TOOLS = {"Agent", "Task"}


def home():
    return os.environ.get("TEAMDESK_HOME") or os.path.join(os.path.expanduser("~"), ".claude", "team-desk")


def rules_path():
    return os.path.join(home(), "rules.json")


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path=None):
    path = path or rules_path()
    try:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
    except (OSError, ValueError):
        user = {}
    return merge(DEFAULT_RULES, user)


def save(rules, path=None):
    path = path or rules_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return path


def agent_allowed(rules, agent_type):
    agent_type = agent_type or "general-purpose"
    return any(fnmatch.fnmatchcase(agent_type, pat) for pat in rules["allowed_agent_types"])


def profile_for(rules, agent_type, member=None):
    """Profile of a td-* agent: global agents are td-<profile>; project members carry their work type."""
    name = (agent_type or "")[len(AGENT_PREFIX):] if (agent_type or "").startswith(AGENT_PREFIX) else ""
    profiles = rules["profiles"]
    if name in profiles:
        return name, profiles[name]
    if member:
        work = member.get("work")
        mapped = {"research": "research", "doc": "doc", "design": "doc", "code": "code", "review": "code"}.get(work)
        if mapped in profiles:
            return mapped, profiles[mapped]
    key = rules.get("default_profile", "research")
    return key, profiles[key]


DOMAIN_RE = re.compile(r"(?:https?://)?(?:[a-z0-9-]+\.)*([a-z0-9-]+\.[a-z]{2,})(?:[/:?#\s]|$)", re.I)


def blocked_domain(rules, text):
    """Return the blocked domain mentioned in a URL/command/query, or None."""
    low = (text or "").lower()
    for d in rules["blocked_domains"]:
        d = d.lower().lstrip(".")
        if re.search(rf"(?:^|[^a-z0-9-])(?:[a-z0-9-]+\.)*{re.escape(d)}(?:[^a-z0-9-]|$)", low):
            return d
    return None


def expand(path):
    return os.path.normpath(os.path.expanduser(path)).replace(os.sep, "/")


def write_allowed(rules, profile, project_dir, target):
    """(ok, reason) for a write by a subagent with the given profile."""
    root = expand(os.path.abspath(project_dir))
    absolute = expand(os.path.abspath(os.path.join(project_dir, os.path.expanduser(target))))
    rel = os.path.relpath(absolute, root).replace(os.sep, "/") if absolute.lower().startswith(root.lower()) else None
    for pat in rules["protected_paths"]:
        p = expand(pat) if pat.startswith("~") else pat
        if fnmatch.fnmatch(absolute, p) or (rel is not None and fnmatch.fnmatch(rel, p)) \
                or (pat.startswith("**/") and fnmatch.fnmatch(os.path.basename(absolute), pat[3:])):
            return False, f"protected path ({pat})"
    mode = profile.get("write", "tmp")
    if mode == "project":
        return (rel is not None and not rel.startswith("..")), "outside the project"
    if mode == "none":
        return False, "this profile may not write files"
    tmp = rules.get("tmp_dir", "tmp").strip("/")
    ok = rel is not None and (rel == tmp or rel.startswith(tmp + "/"))
    return ok, f"outside {tmp}/ of the project"
