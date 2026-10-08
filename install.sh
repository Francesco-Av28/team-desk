#!/usr/bin/env bash
# team-desk installer: links the CLI into ~/.local/bin and the /team-desk skill into ~/.claude/skills.
# Re-run safely after `git pull`. Usage: ./install.sh [--tmux-conf]
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
BIN_DIR="$HOME/.local/bin"
SKILL_DIR="$HOME/.claude/skills"

need() { command -v "$1" >/dev/null 2>&1 || [ -x "$HOME/.local/bin/$1" ] || { echo "missing: $1 ($2)"; MISSING=1; }; }
MISSING=0
need python3 "sudo apt install python3"
need tmux "sudo apt install tmux  |  brew install tmux"
need claude "curl -fsSL https://claude.ai/install.sh | bash"
[ "$MISSING" = 0 ] || echo "install the missing tools above, then re-run (continuing anyway)"

mkdir -p "$BIN_DIR" "$SKILL_DIR"
chmod +x "$ROOT/bin/team-desk" "$ROOT/hooks/guard_owns.py"
ln -sfn "$ROOT/bin/team-desk" "$BIN_DIR/team-desk"
ln -sfn "$ROOT/skill/team-desk" "$SKILL_DIR/team-desk"
echo "linked $BIN_DIR/team-desk -> $ROOT/bin/team-desk"
echo "linked $SKILL_DIR/team-desk -> $ROOT/skill/team-desk"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "add to your shell rc: export PATH=\"$BIN_DIR:\$PATH\"";; esac

if [ "${1:-}" = "--tmux-conf" ]; then
  "$BIN_DIR/team-desk" tmux-conf -y
else
  echo "optional: team-desk tmux-conf   (Ctrl+Z = undo, mouse, 60% lead pane; installs with a backup)"
fi
"$BIN_DIR/team-desk" --version
