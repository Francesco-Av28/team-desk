import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
import guard_owns as GO  # noqa: E402

from teamdesk import generate as G  # noqa: E402
from teamdesk import roster as R  # noqa: E402


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        with open(os.path.join(self.root, "team.json"), "w") as f:
            json.dump({"members": [{"name": "build", "work": "code", "role": "x", "owns": ["web/**", "README.md"]},
                                   {"name": "free", "work": "doc", "role": "x"}]}, f)
        os.environ["CLAUDE_PROJECT_DIR"] = self.root

    def tearDown(self):
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.tmp.cleanup()

    def run_hook(self, member, tool, path):
        event = {"tool_name": tool, "tool_input": {"file_path": path}, "cwd": self.root}
        return GO.main(["guard", member], io.StringIO(json.dumps(event)))

    def test_allows_owned_paths(self):
        for p in ("web/app/page.tsx", "web", "README.md", os.path.join(self.root, "web", "x.css"),
                  ".team-desk/status/build.done"):
            with self.subTest(p=p):
                self.assertEqual(self.run_hook("build", "Write", p), 0)

    def test_blocks_everything_else(self):
        for p in ("docs/x.md", "webx/a", "../outside.txt", "/etc/passwd", ".team-desk/status/other.done",
                  "team.json", "sub/README.md"):
            with self.subTest(p=p):
                self.assertEqual(self.run_hook("build", "Edit", p), 2)

    def test_ignores_reads_and_unrestricted_members(self):
        self.assertEqual(self.run_hook("build", "Read", "docs/x.md"), 0)
        self.assertEqual(self.run_hook("free", "Write", "anything.md"), 0)
        self.assertEqual(self.run_hook("unknown", "Write", "anything.md"), 0)

    def test_member_from_agent_type(self):
        def ev(agent_type, path):
            e = {"tool_name": "Write", "tool_input": {"file_path": path}, "cwd": self.root}
            if agent_type:
                e["agent_type"] = agent_type
            return GO.main(["guard"], io.StringIO(json.dumps(e)))
        self.assertEqual(ev("td-build", "docs/x.md"), 2)
        self.assertEqual(ev("td-build", "web/x.md"), 0)
        self.assertEqual(ev(None, "docs/x.md"), 0)  # the lead
        self.assertEqual(ev("Explore", "docs/x.md"), 0)  # not a team-desk member

    def test_gen_installs_project_hook_once_and_keeps_settings(self):
        os.makedirs(os.path.join(self.root, ".claude"))
        with open(os.path.join(self.root, ".claude", "settings.json"), "w") as f:
            json.dump({"skillOverrides": {"x": "off"}, "hooks": {"PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}]}}, f)
        r = R.normalise({"members": [{"name": "build", "work": "code", "role": "x", "owns": ["web/**"]}]})
        G.generate(r, self.root)
        G.generate(r, self.root)
        with open(os.path.join(self.root, ".claude", "settings.json")) as f:
            s = json.load(f)
        self.assertEqual(s["skillOverrides"], {"x": "off"})
        cmds = [h["command"] for e in s["hooks"]["PreToolUse"] for h in e["hooks"]]
        self.assertEqual(sum("guard_owns.py" in c for c in cmds), 1)
        self.assertIn("mine.sh", cmds)

if __name__ == "__main__":
    unittest.main()
