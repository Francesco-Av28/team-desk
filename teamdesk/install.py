"""Optional tmux config, installed only on request and with a backup."""

import os
import shutil
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(HERE, "tmux", "team-desk.conf")
LINE = f"source-file {SOURCE}"


def tmux_conf(apply=False, target=None):
    target = target or os.path.expanduser("~/.tmux.conf")
    with open(SOURCE, encoding="utf-8") as f:
        body = f.read()
    current = open(target, encoding="utf-8").read() if os.path.exists(target) else ""
    if LINE in current:
        return f"already installed: {target} sources {SOURCE}"
    if not apply:
        return f"{body}\nTo install (backs up {target} first): team-desk tmux-conf -y"
    if current:
        backup = f"{target}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(target, backup)
    with open(target, "a", encoding="utf-8") as f:
        f.write(f"\n# team-desk\n{LINE}\n")
    return f"installed: {target} now sources {SOURCE}" + (f" (backup: {backup})" if current else "")
