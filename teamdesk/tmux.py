"""tmux sessions: the team session (lead + teammates' panes) and the separate dashboard session."""

import json
import os
import re
import shlex
import shutil
import subprocess
import time

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "team-desk")
TEAM_ENV = {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}
LEAD_SETTINGS = {"teammateMode": "tmux"}
MAIN_PANE_WIDTH = "60%"


class TmuxError(RuntimeError):
    pass


def require_tmux():
    if not shutil.which("tmux"):
        raise TmuxError("tmux not found (Ubuntu/WSL: sudo apt install tmux; macOS: brew install tmux)")


def run(*args, check=True):
    p = subprocess.run(["tmux", *args], capture_output=True, text=True)
    if check and p.returncode != 0:
        raise TmuxError(f"tmux {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def slug(project_dir):
    base = os.path.basename(os.path.abspath(project_dir)).lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-") or "project"


def session_name(project_dir, dash=False):
    return f"td-{slug(project_dir)}" + ("-dash" if dash else "")


def exists(name):
    return subprocess.run(["tmux", "has-session", "-t", f"={name}"], capture_output=True).returncode == 0


def lead_command(model):
    claude = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    return f"{shlex.quote(claude)} --model {model} -n team-lead --settings {shlex.quote(json.dumps(LEAD_SETTINGS))}"


def up(project_dir, model="opus"):
    """Create the team session with the lead in pane 0. Returns (session, created)."""
    require_tmux()
    name = session_name(project_dir)
    if exists(name):
        return name, False
    env = []
    for k, v in TEAM_ENV.items():
        env += ["-e", f"{k}={v}"]
    # The pane runs a login shell, and the lead is typed into it: if Claude exits or is suspended
    # (Ctrl+Z), the shell is still there to run `fg` or restart it.
    run("new-session", "-d", "-s", name, "-c", os.path.abspath(project_dir), *env, "-x", "200", "-y", "50")
    run("set-option", "-w", "-t", name, "main-pane-width", MAIN_PANE_WIDTH)
    run("set-hook", "-t", name, "after-split-window", "select-layout main-vertical")
    run("send-keys", "-t", f"{name}:0.0", lead_command(model), "Enter")
    return name, True


def panes(name):
    out = run("list-panes", "-s", "-t", name, "-F", "#{pane_id}\t#{pane_index}\t#{pane_current_command}\t#{pane_title}")
    rows = []
    for line in out.splitlines():
        pid, idx, cmd, title = (line.split("\t") + ["", "", "", ""])[:4]
        rows.append({"id": pid, "index": int(idx or 0), "command": cmd, "title": title})
    return rows


def stop(name):
    """Interrupt every Claude in the session with Escape: the lead first, so it stops dispatching."""
    require_tmux()
    if not exists(name):
        raise TmuxError(f"no session {name}")
    ids = [p["id"] for p in sorted(panes(name), key=lambda p: p["index"])]
    for pid in ids:
        run("send-keys", "-t", pid, "Escape")
        time.sleep(0.3)
        run("send-keys", "-t", pid, "Escape")
    return ids


def down(name):
    require_tmux()
    if exists(name):
        run("kill-session", "-t", f"={name}")
        return True
    return False


def dash(project_dir, interval=30):
    """Separate session that refreshes `team-desk status` and `team-desk cost`."""
    require_tmux()
    name = session_name(project_dir, dash=True)
    if not exists(name):
        td = shlex.quote(BIN)
        loop = (f"while true; do clear; {td} status; echo; {td} cost --short; "
                f"echo; date '+updated %H:%M:%S (every {interval}s, Ctrl+C to stop)'; sleep {interval}; done")
        run("new-session", "-d", "-s", name, "-c", os.path.abspath(project_dir))
        run("send-keys", "-t", f"{name}:0.0", loop, "Enter")
    return name


def attach_hint(name):
    inside = bool(os.environ.get("TMUX"))
    return f"tmux switch-client -t {name}" if inside else f"tmux attach -t {name}"
