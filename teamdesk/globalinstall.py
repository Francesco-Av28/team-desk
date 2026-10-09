"""`team-desk global ...`: install the global regime (rules, governed agents, guard hook) for every project."""

import json
import os
import shutil
import time

from . import globalrules as GR

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(HERE, "hooks", "td_guard.py")
HOOK_MARK = "td_guard.py"


def claude_dir():
    return os.environ.get("TEAMDESK_CLAUDE_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def hook_command():
    py = "python" if os.name == "nt" else "python3"
    return f'{py} "{HOOK.replace(os.sep, "/")}"'


def agent_markdown(name, prof, rules):
    tmp = rules.get("tmp_dir", "tmp")
    where = {"tmp": f"only inside `{tmp}/` of the current project (create it if needed)",
             "project": "only inside the current project, never in .claude/, .git/ or secret files",
             "none": "nowhere: return your result in the final message"}[prof.get("write", "tmp")]
    web = (f"Max {prof['max_web']} WebSearch/WebFetch calls in total. No scraping, no scripts that fetch pages."
           if prof.get("max_web") else "No web access of any kind (no WebFetch/WebSearch, no curl/wget).")
    return "\n".join([
        "---",
        f"name: td-{name}",
        f"description: Governed '{name}' agent (team-desk global regime). {prof.get('description', '')} "
        f"Max {prof['max_actions']} tool calls{', ' + str(prof['max_web']) + ' web calls' if prof.get('max_web') else ''}.",
        f"tools: {', '.join(prof['tools'])}",
        f"model: {prof['model']}",
        f"maxTurns: {prof.get('max_turns', 25)}",
        "---",
        "",
        f"You are a governed `{name}` subagent. A global guard enforces these limits: when it blocks you, "
        "do not retry or work around it.",
        "",
        "## Hard limits",
        f"- Max {prof['max_actions']} tool calls, {prof.get('max_turns', 25)} turns. Plan first, batch independent calls.",
        f"- {web}",
        f"- Write files {where}.",
        "- Never start agents, terminals or `claude` processes; never publish, pay, email or delete.",
        "- Blocked domains: " + ", ".join(rules["blocked_domains"]) + ".",
        "",
        "## Work style",
        "- Small scope: if the task has more than ~8 items, do the first 8 and say what is left.",
        "- Write partial results early (one file), then refine. If you hit a limit: stop, keep what you have, list gaps.",
        "- Final message: max 15 lines, with the path of what you wrote, sources used and open gaps.",
        "",
    ])


def write_agents(rules):
    d = os.path.join(claude_dir(), "agents")
    os.makedirs(d, exist_ok=True)
    out = []
    for name, prof in rules["profiles"].items():
        p = os.path.join(d, f"td-{name}.md")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(agent_markdown(name, prof, rules))
        out.append(p)
    return out


def settings_path():
    return os.path.join(claude_dir(), "settings.json")


def read_settings():
    p = settings_path()
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_settings(data, backup=True):
    p = settings_path()
    if backup and os.path.exists(p):
        shutil.copy2(p, f"{p}.bak-teamdesk-{time.strftime('%Y%m%d-%H%M%S')}")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return p


def hook_installed(data=None):
    data = read_settings() if data is None else data
    return any(HOOK_MARK in h.get("command", "")
               for e in data.get("hooks", {}).get("PreToolUse", []) for h in e.get("hooks", []))


def install_hook():
    data = read_settings()
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    for e in pre:
        e["hooks"] = [h for h in e.get("hooks", []) if HOOK_MARK not in h.get("command", "")]
    pre[:] = [e for e in pre if e.get("hooks")]
    pre.append({"matcher": "*", "hooks": [{"type": "command", "command": hook_command(), "timeout": 10}]})
    return write_settings(data)


def remove_hook():
    data = read_settings()
    if not hook_installed(data):
        return None
    pre = data.get("hooks", {}).get("PreToolUse", [])
    for e in pre:
        e["hooks"] = [h for h in e.get("hooks", []) if HOOK_MARK not in h.get("command", "")]
    pre[:] = [e for e in pre if e.get("hooks")]
    return write_settings(data)


def init():
    rules = GR.load()  # existing user rules win over defaults
    lines = [f"rules: {GR.save(rules)}"]
    lines += [f"agent: {p}" for p in write_agents(rules)]
    lines.append(f"hook:  {install_hook()} (PreToolUse * -> {HOOK}; backup kept next to it)")
    lines.append("Restart open Claude Code sessions: hooks are read at startup.")
    return "\n".join(lines)


def set_enabled(flag):
    rules = GR.load()
    rules["enabled"] = flag
    GR.save(rules)
    return f"global regime {'ON' if flag else 'OFF'} ({GR.rules_path()})"


def status():
    rules = GR.load()
    lines = [f"global regime: {'ON' if rules.get('enabled', True) else 'OFF'}   rules: {GR.rules_path()}",
             f"hook installed: {'yes' if hook_installed() else 'NO'} ({settings_path()})",
             "allowed agent types: " + ", ".join(rules["allowed_agent_types"]),
             "blocked domains: " + ", ".join(rules["blocked_domains"]), "profiles:"]
    for n, p in rules["profiles"].items():
        agent = os.path.join(claude_dir(), "agents", f"td-{n}.md")
        lines.append(f"  td-{n:9} {p['model']:6} actions {p['max_actions']:>3}  web {p.get('max_web', 0):>2}  "
                     f"write {p.get('write', 'tmp'):7} {'' if os.path.exists(agent) else '(agent file missing)'}")
    log = os.path.join(GR.home(), "log.jsonl")
    if os.path.exists(log):
        today = time.strftime("%Y-%m-%d")
        recs = []
        with open(log, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("ts", "").startswith(today):
                    recs.append(r)
        blocks = [r for r in recs if r.get("decision") == "block"]
        lines.append(f"today: {len(recs)} checked calls, {len(blocks)} blocked")
        lines += [f"  blocked {r.get('agent_type') or 'main'} {r.get('tool')}: {r.get('reason', '')[:90]}" for r in blocks[-5:]]
    return "\n".join(lines)
