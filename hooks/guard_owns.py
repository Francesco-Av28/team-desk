#!/usr/bin/env python3
"""PreToolUse hook: block a team member's file writes outside the paths it owns.

Installed by `team-desk gen` as a project-level hook in .claude/settings.json (hooks declared in an
agent's frontmatter are not run by Claude Code). The member is identified from the event's
"agent_type" (td-<name>); events without it come from the lead and are allowed.
Optional argv[1] forces the member name (used in tests).
Exit 0 = allow, exit 2 = block (stderr is shown to the member as the reason).
Only file-writing tools are checked; Bash commands are not parsed.
"""

import json
import os
import re
import sys

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def glob_to_regex(pattern):
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def allowed(rel_path, member, owns):
    rel_path = rel_path.replace(os.sep, "/")
    if re.fullmatch(rf"\.team-desk/status/{re.escape(member)}\.(done|blocked)", rel_path):
        return True
    for pattern in owns:
        p = pattern.rstrip("/")
        if glob_to_regex(p).match(rel_path) or (p.endswith("/**") and rel_path == p[:-3]):
            return True
    return False


def log(event, member, decision):
    """Optional audit trail: set TEAMDESK_GUARD_LOG=/path/to/file."""
    path = os.environ.get("TEAMDESK_GUARD_LOG")
    if path:
        target = (event.get("tool_input") or {}).get("file_path", "")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"agent_type": event.get("agent_type"), "member": member,
                                "tool": event.get("tool_name"), "path": target, "decision": decision}) + "\n")


def main(argv, stdin):
    try:
        event = json.load(stdin)
    except ValueError:
        return 0
    agent_type = event.get("agent_type") or ""
    member = argv[1] if len(argv) > 1 else (agent_type[3:] if agent_type.startswith("td-") else "")
    code = decide(event, member)
    if event.get("tool_name") in WRITE_TOOLS:
        log(event, member, "block" if code == 2 else "allow")
    return code


def decide(event, member):
    if not member:
        return 0
    if event.get("tool_name") not in WRITE_TOOLS:
        return 0
    tool_input = event.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target:
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    try:
        with open(os.path.join(root, "team.json"), encoding="utf-8") as f:
            members = json.load(f).get("members", [])
    except (OSError, ValueError):
        return 0  # no roster: nothing to enforce
    owns = next((m.get("owns", []) for m in members if m.get("name") == member), None)
    if not owns:
        return 0
    absolute = os.path.abspath(os.path.join(root, target)).replace(os.sep, "/")
    rel = os.path.relpath(absolute, os.path.abspath(root)).replace(os.sep, "/")
    relative_owns = [p for p in owns if not os.path.isabs(p)]
    absolute_owns = [p for p in owns if os.path.isabs(p)]  # e.g. app code kept outside the project
    if not rel.startswith("..") and allowed(rel, member, relative_owns):
        return 0
    if any(glob_to_regex(p.rstrip("/")).match(absolute) or absolute == p.rstrip("/")[:-3]
           for p in absolute_owns):
        return 0
    sys.stderr.write(
        f"team-desk: '{member}' may only write inside {', '.join(owns)} "
        f"(and .team-desk/status/{member}.done). Blocked: {rel}. "
        "If this file is needed, report it to the lead instead of writing it.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv, sys.stdin))
