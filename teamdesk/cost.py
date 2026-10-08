"""Token usage per team member, read from Claude Code transcripts.

Weighted tokens express everything in "input token" units using Anthropic's price ratios:
cache read 0.1x, cache write 1.25x, output 5x. It is a relative measure of spend that works for
API and subscription users alike, not a currency amount.
"""

import glob
import json
import os
import re
from datetime import datetime, timedelta, timezone

from . import roster as R

WEIGHTS = {"input_tokens": 1.0, "cache_read_input_tokens": 0.1, "cache_creation_input_tokens": 1.25, "output_tokens": 5.0}
RUN_FILE = "run.json"


def projects_root():
    return os.path.join(os.path.expanduser("~/.claude"), "projects")


def transcript_dir(project_dir):
    return os.path.join(projects_root(), re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(project_dir)))


def mark_run_start(project_dir):
    path = os.path.join(project_dir, R.STATE_DIR, RUN_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"started": datetime.now(timezone.utc).isoformat()}, f)


def run_start(project_dir):
    try:
        with open(os.path.join(project_dir, R.STATE_DIR, RUN_FILE), encoding="utf-8") as f:
            return datetime.fromisoformat(json.load(f)["started"])
    except (OSError, KeyError, ValueError):
        return None


def parse_ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def read_transcript(path):
    """Usage totals and identity of one transcript file."""
    t = {"file": path, "name": None, "turns": 0, "models": set(), "first": None, "last": None,
         **{k: 0 for k in WEIGHTS}}
    meta = path[:-len(".jsonl")] + ".meta.json"
    if os.path.exists(meta):
        try:
            with open(meta, encoding="utf-8") as f:
                t["name"] = json.load(f).get("name")
        except (OSError, ValueError):
            pass
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            ts = parse_ts(d.get("timestamp"))
            if ts:
                t["first"] = t["first"] or ts
                t["last"] = ts
            t["name"] = t["name"] or d.get("agentName")
            if d.get("type") != "assistant":
                continue
            msg = d.get("message") or {}
            usage = msg.get("usage") or {}
            if not usage:
                continue
            t["turns"] += 1
            if msg.get("model"):
                t["models"].add(msg["model"])
            for k in WEIGHTS:
                t[k] += usage.get(k) or 0
    t["name"] = t["name"] or "lead"
    return t


def weighted(t):
    return sum(t[k] * w for k, w in WEIGHTS.items())


def raw(t):
    return sum(t[k] for k in WEIGHTS)


def report(project_dir, since=None, since_hours=None, all_sessions=False):
    """Aggregate per member name. Default window: since the last `team-desk up`."""
    if since_hours is not None:
        since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    elif since is None and not all_sessions:
        since = run_start(project_dir)
    base = transcript_dir(project_dir)
    files = glob.glob(os.path.join(base, "*.jsonl")) + glob.glob(os.path.join(base, "*", "subagents", "*.jsonl"))
    members = {}
    for path in files:
        t = read_transcript(path)
        if not t["turns"] or (since and t["last"] and t["last"] < since):
            continue
        name = t["name"][3:] if t["name"].startswith("td-") else t["name"]
        m = members.setdefault(name, {"name": name, "sessions": 0, "turns": 0, "models": set(),
                                      **{k: 0 for k in WEIGHTS}})
        m["sessions"] += 1
        m["turns"] += t["turns"]
        m["models"] |= t["models"]
        for k in WEIGHTS:
            m[k] += t[k]
    rows = sorted(members.values(), key=weighted, reverse=True)
    total = sum(weighted(r) for r in rows)
    return {"since": since, "dir": base, "rows": rows, "weighted": total, "raw": sum(raw(r) for r in rows)}


def threshold_hit(rep, budget):
    """Highest checkpoint fraction already passed, or None."""
    used = rep["weighted"] / budget["total_tokens"] if budget["total_tokens"] else 0
    passed = [c for c in sorted(budget["checkpoints"]) + [1.0] if used >= c]
    return passed[-1] if passed else None


def fmt(n):
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"


def short_model(models):
    names = sorted({m.split("-")[1] if m.startswith("claude-") and "-" in m[7:] else m for m in models})
    return ",".join(names) or "-"


def render(rep, budget, short=False):
    used = rep["weighted"] / budget["total_tokens"] if budget["total_tokens"] else 0
    hit = threshold_hit(rep, budget)
    bar_len = 30
    filled = min(bar_len, int(used * bar_len))
    head = (f"budget [{'#' * filled}{'.' * (bar_len - filled)}] {used * 100:.0f}% "
            f"({fmt(rep['weighted'])} of {fmt(budget['total_tokens'])} weighted)")
    if hit is not None:
        head += f"  ⚠ past {int(hit * 100)}%: stop and decide"
    if short:
        top = ", ".join(f"{r['name']} {weighted(r) / rep['weighted'] * 100:.0f}%" for r in rep["rows"][:4]) \
            if rep["weighted"] else "no usage yet"
        return f"{head}\n{top}"
    since = rep["since"].astimezone().strftime("%Y-%m-%d %H:%M") if rep["since"] else "all sessions"
    w = max([16] + [len(r["name"]) + 2 for r in rep["rows"]])
    lines = [head, f"window: {since}", "",
             f"{'member':<{w}}{'model':<14}{'turns':>6}{'raw':>9}{'weighted':>10}{'share':>7}"]
    for r in rep["rows"]:
        share = weighted(r) / rep["weighted"] * 100 if rep["weighted"] else 0
        lines.append(f"{r['name']:<{w}}{short_model(r['models']):<14}{r['turns']:>6}{fmt(raw(r)):>9}"
                     f"{fmt(weighted(r)):>10}{share:>6.0f}%")
    if not rep["rows"]:
        lines.append(f"(no transcripts in {rep['dir']})")
    lines += ["", f"total raw {fmt(rep['raw'])} · weighted = input 1x, cache read 0.1x, cache write 1.25x, output 5x"]
    return "\n".join(lines)
