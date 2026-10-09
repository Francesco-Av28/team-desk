#!/usr/bin/env python3
"""Global PreToolUse hook: one strict regime for every subagent, in every project.

Installed by `team-desk global init` in ~/.claude/settings.json. Rules: ~/.claude/team-desk/rules.json.
- Main session: may spawn only allowed agent types (td-* by default); general-purpose & co. are refused.
- Subagents (events carrying "agent_type"): tool allowlist per profile, max actions, max web calls,
  blocked domains, write scope (tmp/ or project), protected paths.
Exit 0 = allow, exit 2 = block (stderr is shown to the agent). Kill switch: TEAMDESK_OFF=1 or
"enabled": false in rules.json (`team-desk global off`). Never blocks on its own errors.
"""

import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from teamdesk import globalrules as GR  # noqa: E402

META_TOOLS = {"ToolSearch", "SendMessage", "Skill", "TodoWrite"}
NET_CMD = re.compile(r"\b(curl|wget|Invoke-WebRequest|iwr|Invoke-RestMethod|irm)\b|urllib\.request|requests\.(get|post)|httpx\.", re.I)


def state_file(key):
    d = os.path.join(GR.home(), "state")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".json")


def prune_state(max_age_h=48):
    d = os.path.join(GR.home(), "state")
    if not os.path.isdir(d):
        return
    now = time.time()
    for fn in os.listdir(d):
        p = os.path.join(d, fn)
        try:
            if now - os.path.getmtime(p) > max_age_h * 3600:
                os.remove(p)
        except OSError:
            pass


def log(rec):
    try:
        os.makedirs(GR.home(), exist_ok=True)
        with open(os.path.join(GR.home(), "log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **rec}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def project_member(project_dir, agent_type):
    if not agent_type.startswith(GR.AGENT_PREFIX):
        return None
    try:
        with open(os.path.join(project_dir, "team.json"), encoding="utf-8") as f:
            members = json.load(f).get("members", [])
    except (OSError, ValueError):
        return None
    name = agent_type[len(GR.AGENT_PREFIX):]
    return next((m for m in members if m.get("name") == name), None)


def block(msg, rec):
    log({**rec, "decision": "block", "reason": msg})
    sys.stderr.write("team-desk: " + msg + "\n")
    return 2


def decide(event, rules):
    tool = event.get("tool_name") or ""
    ti = event.get("tool_input") or {}
    agent_type = event.get("agent_type") or ""
    project = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    rec = {"session": event.get("session_id"), "agent_id": event.get("agent_id"), "agent_type": agent_type, "tool": tool}
    if os.environ.get("TEAMDESK_DEBUG"):
        rec["event_keys"] = sorted(event.keys())

    # 1) Spawning agents (main session or subagent): only allowed types.
    if tool in SPAWN_TOOLS_SET:
        wanted = ti.get("subagent_type") or "general-purpose"
        rec["spawn"] = wanted
        if agent_type:
            return block("subagents may not start other agents. Report back to the lead instead.", rec)
        if not GR.agent_allowed(rules, wanted):
            allowed = ", ".join(sorted(p for p in rules["profiles"]))
            return block(f"agent type '{wanted}' is not allowed by the global regime. Use a governed agent: "
                         f"td-{allowed.replace(', ', ', td-')} (or a project member td-<name>). "
                         "Rules: ~/.claude/team-desk/rules.json", rec)
        log({**rec, "decision": "allow"})
        return 0

    if not agent_type:
        return 0  # main session: untouched

    # 2) Subagent regime.
    member = project_member(project, agent_type)
    pname, prof = GR.profile_for(rules, agent_type, member)
    rec["profile"] = pname
    tools = set(member.get("tools") or []) if member and member.get("tools") else set(prof["tools"])
    if tool not in tools and tool not in META_TOOLS and not tool.startswith("mcp__"):
        return block(f"tool '{tool}' is not in the '{pname}' profile ({', '.join(sorted(tools))}).", rec)

    max_actions = int(prof.get("max_actions", 40))
    max_web = int(member.get("max_fetches", prof.get("max_web", 0)) if member else prof.get("max_web", 0))
    key = event.get("agent_id") or f"{event.get('session_id')}|{agent_type}"
    path = state_file(key)
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {"actions": 0, "web": 0}
    if st["actions"] >= max_actions:
        return block(f"action limit reached ({max_actions}). Stop now: write what you have, list the gaps, "
                     "send one final message.", rec)
    is_web = tool in GR.WEB_TOOLS
    if is_web and st["web"] >= max_web:
        return block(f"web limit reached ({max_web} searches/pages for profile '{pname}'). "
                     "Work with what you have and list the gaps.", rec)

    text = " ".join(str(ti.get(k, "")) for k in ("url", "query", "command", "prompt"))
    dom = GR.blocked_domain(rules, text)
    if dom and (is_web or tool == "Bash"):
        return block(f"{dom} is a blocked domain (no scraping or automated access).", rec)
    if tool == "Bash" and max_web == 0 and NET_CMD.search(ti.get("command", "")):
        return block(f"network commands are not allowed for profile '{pname}' (no web access).", rec)

    if tool in GR.WRITE_TOOLS:
        target = ti.get("file_path") or ti.get("notebook_path") or ""
        ok, why = GR.write_allowed(rules, prof, project, target)
        if not ok:
            return block(f"write blocked ({why}): {target}. Profile '{pname}' writes only "
                         f"{'inside ' + rules.get('tmp_dir', 'tmp') + '/' if prof.get('write', 'tmp') == 'tmp' else 'inside the project'}.", rec)

    st["actions"] += 1
    st["web"] += 1 if is_web else 0
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(st, f)
    except OSError:
        pass
    log({**rec, "decision": "allow", "actions": st["actions"], "web": st["web"]})
    return 0


SPAWN_TOOLS_SET = GR.SPAWN_TOOLS


def main(stdin=sys.stdin):
    if os.environ.get("TEAMDESK_OFF") == "1":
        return 0
    try:
        event = json.load(stdin)
    except ValueError:
        return 0
    try:
        rules = GR.load()
        if not rules.get("enabled", True):
            return 0
        if time.time() % 50 < 1:
            prune_state()
        return decide(event, rules)
    except Exception as e:  # a broken guard must never block work
        log({"decision": "error", "error": repr(e)})
        return 0


if __name__ == "__main__":
    sys.exit(main())
