"""Turn a normalised roster into Claude Code files: agents, lead rules, state dirs."""

import os

from . import roster as R

AGENT_PREFIX = "td-"
BLOCK_START = "<!-- team-desk:start (generated, edit team.json instead) -->"
BLOCK_END = "<!-- team-desk:end -->"


def agent_name(member):
    return AGENT_PREFIX + member["name"]


def status_path(name, kind="done"):
    return f"{R.STATE_DIR}/status/{name}.{kind}"


def agent_markdown(member, roster):
    lines = [
        "---",
        f"name: {agent_name(member)}",
        f"description: team-desk member '{member['name']}' ({member['work']}). {first_line(member['role']) or 'Runs skill ' + member['skill']}",
        f"tools: {', '.join(member['tools'])}",
        f"model: {member['model']}",
        f"maxTurns: {member['max_turns']}",
        "---",
        "",
        f"You are \"{member['name']}\", a member of the team-desk team for project \"{roster['project']}\". "
        "The team lead coordinates; you do one job and report.",
        "",
        "## Your job",
    ]
    if member["role"]:
        lines.append(member["role"].strip())
    if member["skill"]:
        lines.append(f"Invoke the `{member['skill']}` skill with the Skill tool first and follow its method, "
                     "limited to the job above and to the files you own.")
    if member["inputs"]:
        lines += ["", "## Inputs", *[f"- `{p}`" for p in member["inputs"]]]
    if member["after"]:
        lines += ["", "Upstream work you build on: " + ", ".join(
            f"`{status_path(d)}`" for d in member["after"]) + " (read the summaries there first)."]
    lines += ["", "## Files you own"]
    if member["owns"]:
        lines += [f"- `{p}`" for p in member["owns"]]
        lines.append("Write ONLY inside these paths (plus your status marker). Writes elsewhere are blocked.")
    else:
        lines.append("No paths assigned: write only what your job strictly needs.")
    fetch_rule = (f"- Max {member['max_fetches']} WebFetch/WebSearch calls in total."
                  if member["max_fetches"] else "- No web access.")
    lines += [
        "",
        "## Hard limits",
        f"- Max {member['max_turns']} turns. Plan first; batch independent tool calls in one turn.",
        fetch_rule,
        "- No scraping: never fetch web pages with curl, wget or scripts; no bulk data collection.",
        "- Never start agents, teammates, terminals, tmux panes or `claude` processes.",
        "- Do not call TaskUpdate or edit the task list: the lead owns it.",
        "- If you hit a limit: stop, write what you have, list the gaps.",
        "- Never do outward-facing or irreversible actions (deploy, publish, pay, email, delete) without the lead "
        "getting the user's confirmation.",
        "",
        "## When you finish",
        "1. Verify for real (run the build/tests/script you produced) when your work is executable.",
        f"2. Write `{status_path(member['name'])}`: date, 3-line summary, files changed, verification output, "
        "turns and fetches used. If blocked, write "
        f"`{status_path(member['name'], 'blocked')}` with the reason instead.",
        "3. Send ONE message to the lead (max 15 lines) and stop.",
        "",
    ]
    return "\n".join(lines)


def first_line(text):
    return (text or "").strip().splitlines()[0][:120] if (text or "").strip() else ""


def lead_rules(roster):
    order = R.order(roster)
    by_name = {m["name"]: m for m in roster["members"]}
    b = roster["budget"]
    rows = ["| Member | Agent type | Model | Work | Skill | After | Owns |", "|---|---|---|---|---|---|---|"]
    for n in order:
        m = by_name[n]
        rows.append(f"| {n} | `{agent_name(m)}` | {m['model']} | {m['work']} | {m['skill'] or '-'} | "
                    f"{', '.join(m['after']) or '-'} | {', '.join(m['owns']) or '-'} |")
    checkpoints = ", ".join(f"{int(c * 100)}%" for c in b["checkpoints"])
    return "\n".join([
        BLOCK_START,
        "## team-desk: rules for the team lead (mandatory)",
        "",
        f"You are the team lead (model: {roster['leader']['model']}). You COORDINATE ONLY: assign, check, "
        "integrate, report. You do not write project files or code yourself.",
        "",
        "### Team",
        *rows,
        "",
        "### Rules",
        "- Spawn teammates ONLY with the agent types above (`subagent_type` = agent type). "
        "Never spawn `general-purpose` or ad-hoc teammates: they inherit your model and your cost.",
        f"- At most {b['max_active']} teammates active at once. Start a member only when every member in its "
        f"'After' column has `{R.STATE_DIR}/status/<name>.done`. Never pre-launch members that would wait.",
        "- Before spawning a member, tell the user: member, model, goal. Wait for the user's ok.",
        f"- Budget: {b['total_tokens']:,} weighted tokens for the whole session. At {checkpoints} of it, stop and "
        "ask the user (they can check with `team-desk cost`).",
        "- Outward-facing or irreversible actions (deploy, publish, payments, emails, deleting files) need the "
        "user's explicit confirmation.",
        "- When a member reports, check its `.done` marker (summary + verification output). Do not redo its work. "
        "If quality is doubtful, propose a `review` member to the user.",
        "- You tick the task list; members only send one final message.",
        "- Keep your context lean: no pasting of large files, summarise, `/compact` above ~120k tokens.",
        "- Never run scripts that open terminals or `claude` processes.",
        BLOCK_END,
    ])


def upsert_block(path, block):
    """Insert or replace the team-desk block in a markdown file, keeping the rest intact."""
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    if BLOCK_START in text and BLOCK_END in text:
        head, rest = text.split(BLOCK_START, 1)
        tail = rest.split(BLOCK_END, 1)[1]
        text = head + block + tail
    else:
        text = (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def generate(roster, project_dir="."):
    """Write all generated files. Returns the list of paths written."""
    written = []
    agents_dir = os.path.join(project_dir, ".claude", "agents")
    os.makedirs(agents_dir, exist_ok=True)
    keep = set()
    for m in roster["members"]:
        p = os.path.join(agents_dir, agent_name(m) + ".md")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(agent_markdown(m, roster))
        keep.add(os.path.basename(p))
        written.append(p)
    # Remove agents of members no longer in the roster (only our own prefix).
    for fn in os.listdir(agents_dir):
        if fn.startswith(AGENT_PREFIX) and fn.endswith(".md") and fn not in keep:
            os.remove(os.path.join(agents_dir, fn))
    claude_md = os.path.join(project_dir, "CLAUDE.md")
    upsert_block(claude_md, lead_rules(roster))
    written.append(claude_md)
    os.makedirs(os.path.join(project_dir, R.STATE_DIR, "status"), exist_ok=True)
    return written
