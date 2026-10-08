"""Propose a starter team from the project's files and the installed skills.

Heuristic and deliberately small: one member per work type (research -> design -> code -> review),
each bound to the best-matching skill when one exists. The user edits the result.
"""

import json
import os
import re

from . import roster as R

# Work type -> keywords searched in skill names and descriptions (name hits weigh more).
KEYWORDS = {
    "research": ["recon", "research", "scout", "survey", "analy", "explore"],
    "design": ["design", "ui", "ux", "theme", "style", "frontend"],
    "code": ["build", "code", "implement", "backend", "api", "develop", "app"],
    "review": ["test", "review", "audit", "diff", "qa", "verify"],
    "doc": ["doc", "write", "readme", "paper", "report", "guide"],
}
PIPELINE = ["research", "design", "code", "review"]
ROLES = {
    "research": "Investigate the problem space and write a short, sourced brief the others build on.",
    "design": "Turn the brief into a design: structure, components, visual tokens, written specs.",
    "code": "Implement the current slice following the design. Run the real build before reporting.",
    "review": "Review and test what was built; report concrete defects with file and line.",
    "doc": "Write the documentation for what was built.",
}
OWNS = {
    "research": ["docs/research/**"],
    "design": ["docs/design/**"],
    "code": ["src/**"],
    "review": ["docs/review/**"],
    "doc": ["docs/**"],
}


def read_frontmatter(path):
    meta = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read(4000)
    except OSError:
        return meta
    m = re.match(r"---\s*\n(.*?)\n---", text, re.S)
    if m:
        key = None
        for line in m.group(1).splitlines():
            if line[:1] in (" ", "	"):
                if key:  # continuation of a block scalar (description: >- ...)
                    meta[key] = (meta[key] + " " + line.strip()).strip()
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                key, v = k.strip(), v.strip()
                meta[key] = "" if v in (">", ">-", "|", "|-") else v.strip("'\"")
    return meta


def disabled_skills(project_dir):
    """Skills switched off via skillOverrides in user or project settings."""
    off = set()
    for p in (os.path.expanduser("~/.claude/settings.json"), os.path.join(project_dir, ".claude", "settings.json")):
        try:
            with open(p, encoding="utf-8") as f:
                for name, state in (json.load(f).get("skillOverrides") or {}).items():
                    if state == "off":
                        off.add(name)
        except (OSError, ValueError):
            pass
    return off


def list_skills(project_dir=".", dirs=None):
    dirs = dirs or R.skill_dirs(project_dir)
    off = disabled_skills(project_dir)
    skills = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            md = os.path.join(d, name, "SKILL.md")
            if name in off or name == "team-desk" or not os.path.exists(md):
                continue
            meta = read_frontmatter(md)
            skills.setdefault(name, {"name": name, "description": meta.get("description", ""), "dir": d})
    return list(skills.values())


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def score(skill, work):
    """Keyword hits on whole words (prefix match: 'test' hits 'testing'); name hits weigh 3x."""
    name, desc = tokens(skill["name"]), tokens(skill["description"])
    hit = lambda words, k: any(w.startswith(k) for w in words)
    kws = KEYWORDS[work]
    # Earlier keywords are more specific: they get a small tie-breaking bonus.
    return sum((3 * hit(name, k) + hit(desc, k)) * (1 + (len(kws) - i) / 100) for i, k in enumerate(kws))


def detect_code_dir(project_dir):
    for d in ("src", "app", "web", "lib"):
        if os.path.isdir(os.path.join(project_dir, d)):
            return [f"{d}/**"]
    return OWNS["code"]


def propose(project_dir=".", dirs=None):
    skills = list_skills(project_dir, dirs)
    used, members, prev = set(), [], None
    for work in PIPELINE:
        ranked = sorted((s for s in skills if s["name"] not in used), key=lambda s: -score(s, work))
        best = ranked[0] if ranked and score(ranked[0], work) > 0 else None
        m = {"name": work if work != "code" else "build", "work": work, "role": ROLES[work],
             "owns": detect_code_dir(project_dir) if work == "code" else OWNS[work]}
        if best:
            used.add(best["name"])
            m["skill"] = best["name"]
        if prev:
            m["after"] = [prev]
        members.append(m)
        prev = m["name"]
    return {"project": os.path.basename(os.path.abspath(project_dir)), "leader": {"model": "opus"},
            "budget": dict(R.DEFAULT_BUDGET), "members": members}


def describe(data):
    r = R.normalise(data)
    lines = [f"Proposed team for '{r['project']}' (lead: {r['leader']['model']}, "
             f"max {r['budget']['max_active']} active, budget {r['budget']['total_tokens']:,} weighted tokens):", ""]
    for m in r["members"]:
        after = f" after {', '.join(m['after'])}" if m["after"] else ""
        lines.append(f"  {m['name']:<10} {m['model']:<7} skill: {m['skill'] or '-':<22} owns: {', '.join(m['owns'])}{after}")
    return "\n".join(lines)
