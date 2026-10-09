import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from teamdesk import globalrules as GR  # noqa: E402

HOOK = os.path.join(ROOT, "hooks", "td_guard.py")


class Base(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.proj = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.proj, "tmp"))
        self.env = {**os.environ, "TEAMDESK_HOME": self.home, "CLAUDE_PROJECT_DIR": self.proj}
        self.env.pop("TEAMDESK_OFF", None)

    def run_hook(self, event, env=None):
        p = subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True, text=True,
                           env=env or self.env)
        return p.returncode, p.stderr

    def sub(self, tool, agent_type="td-research", agent_id="a1", **ti):
        return {"session_id": "s1", "agent_id": agent_id, "agent_type": agent_type, "tool_name": tool,
                "tool_input": ti, "cwd": self.proj}


class Rules(unittest.TestCase):
    def test_defaults_and_merge(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "rules.json")
            with open(p, "w") as f:
                json.dump({"profiles": {"research": {"max_web": 3}}}, f)
            r = GR.load(p)
            self.assertEqual(r["profiles"]["research"]["max_web"], 3)
            self.assertEqual(r["profiles"]["research"]["model"], "haiku")  # kept from defaults
            self.assertIn("doc", r["profiles"])

    def test_agent_allowed(self):
        r = GR.load("/nonexistent")
        self.assertTrue(GR.agent_allowed(r, "td-research"))
        self.assertFalse(GR.agent_allowed(r, "general-purpose"))
        self.assertFalse(GR.agent_allowed(r, None))

    def test_blocked_domain(self):
        r = GR.load("/nonexistent")
        self.assertEqual(GR.blocked_domain(r, "https://www.linkedin.com/jobs/x"), "linkedin.com")
        self.assertEqual(GR.blocked_domain(r, "curl -s it.linkedin.com/api"), "linkedin.com")
        self.assertIsNone(GR.blocked_domain(r, "https://notlinkedin.com.example.org"))
        self.assertIsNone(GR.blocked_domain(r, "https://www.indeed.com"))

    def test_profile_resolution(self):
        r = GR.load("/nonexistent")
        self.assertEqual(GR.profile_for(r, "td-code")[0], "code")
        self.assertEqual(GR.profile_for(r, "td-writer", {"work": "doc"})[0], "doc")
        self.assertEqual(GR.profile_for(r, "Explore")[0], "research")


class Guard(Base):
    def test_main_session_untouched(self):
        self.assertEqual(self.run_hook({"session_id": "s", "tool_name": "Bash", "tool_input": {"command": "ls"}})[0], 0)

    def test_spawn_general_purpose_blocked(self):
        code, err = self.run_hook({"session_id": "s", "tool_name": "Agent",
                                   "tool_input": {"subagent_type": "general-purpose", "prompt": "x"}})
        self.assertEqual(code, 2)
        self.assertIn("not allowed", err)
        self.assertEqual(self.run_hook({"session_id": "s", "tool_name": "Agent",
                                        "tool_input": {"prompt": "x"}})[0], 2)  # default type = general-purpose

    def test_spawn_td_allowed(self):
        self.assertEqual(self.run_hook({"session_id": "s", "tool_name": "Agent",
                                        "tool_input": {"subagent_type": "td-research"}})[0], 0)

    def test_subagent_cannot_spawn(self):
        self.assertEqual(self.run_hook(self.sub("Agent", subagent_type="td-research"))[0], 2)

    def test_tool_not_in_profile(self):
        code, err = self.run_hook(self.sub("Bash", command="ls"))
        self.assertEqual(code, 2)
        self.assertIn("not in the 'research' profile", err)

    def test_web_limit(self):
        for i in range(15):
            self.assertEqual(self.run_hook(self.sub("WebSearch", query=f"q{i}"))[0], 0)
        code, err = self.run_hook(self.sub("WebFetch", url="https://example.org"))
        self.assertEqual(code, 2)
        self.assertIn("web limit", err)
        self.assertEqual(self.run_hook(self.sub("WebSearch", agent_id="a2", query="q"))[0], 0)  # other agent

    def test_action_limit(self):
        for i in range(40):
            self.assertEqual(self.run_hook(self.sub("Read", file_path="x"))[0], 0)
        self.assertEqual(self.run_hook(self.sub("Read", file_path="x"))[0], 2)

    def test_blocked_domain(self):
        code, err = self.run_hook(self.sub("WebFetch", url="https://www.linkedin.com/jobs/search?k=aml"))
        self.assertEqual(code, 2)
        self.assertIn("linkedin.com", err)

    def test_write_scope_research(self):
        self.assertEqual(self.run_hook(self.sub("Write", file_path=os.path.join(self.proj, "tmp", "out.json")))[0], 0)
        self.assertEqual(self.run_hook(self.sub("Write", file_path="tmp/rel.json"))[0], 0)
        code, err = self.run_hook(self.sub("Write", file_path=os.path.join(self.proj, "README.md")))
        self.assertEqual(code, 2)
        self.assertIn("outside tmp/", err)

    def test_code_profile(self):
        ok = self.run_hook(self.sub("Write", agent_type="td-code", file_path=os.path.join(self.proj, "src", "a.py")))
        self.assertEqual(ok[0], 0)
        self.assertEqual(self.run_hook(self.sub("Write", agent_type="td-code",
                                                file_path=os.path.join(self.proj, ".claude", "settings.json")))[0], 2)
        self.assertEqual(self.run_hook(self.sub("Bash", agent_type="td-code", command="curl https://example.org"))[0], 2)
        self.assertEqual(self.run_hook(self.sub("Bash", agent_type="td-code", command="python -m unittest"))[0], 0)

    def test_kill_switches(self):
        ev = self.sub("Bash", command="ls")
        self.assertEqual(self.run_hook(ev, env={**self.env, "TEAMDESK_OFF": "1"})[0], 0)
        GR.save({"enabled": False}, os.path.join(self.home, "rules.json"))
        self.assertEqual(self.run_hook(ev)[0], 0)

    def test_project_member_uses_roster(self):
        with open(os.path.join(self.proj, "team.json"), "w") as f:
            json.dump({"members": [{"name": "scout", "work": "research", "max_fetches": 2,
                                    "tools": ["Read", "WebSearch", "Write"]}]}, f)
        for _ in range(2):
            self.assertEqual(self.run_hook(self.sub("WebSearch", agent_type="td-scout", query="q"))[0], 0)
        self.assertEqual(self.run_hook(self.sub("WebSearch", agent_type="td-scout", query="q"))[0], 2)

    def test_bad_input_never_blocks(self):
        p = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True, env=self.env)
        self.assertEqual(p.returncode, 0)


class Install(unittest.TestCase):
    def test_init_status_off_remove(self):
        from teamdesk import globalinstall as GI
        with tempfile.TemporaryDirectory() as cd, tempfile.TemporaryDirectory() as home:
            os.environ["TEAMDESK_CLAUDE_DIR"], os.environ["TEAMDESK_HOME"] = cd, home
            try:
                with open(os.path.join(cd, "settings.json"), "w") as f:
                    json.dump({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "other"}]}]},
                               "model": "opus"}, f)
                GI.init()
                GI.init()  # idempotent
                data = json.load(open(os.path.join(cd, "settings.json")))
                cmds = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]
                self.assertEqual(sum("td_guard.py" in c for c in cmds), 1)
                self.assertIn("other", cmds)
                self.assertEqual(data["model"], "opus")
                self.assertTrue(any(fn.startswith("settings.json.bak-teamdesk-") for fn in os.listdir(cd)))
                for n in ("research", "doc", "code"):
                    md = open(os.path.join(cd, "agents", f"td-{n}.md"), encoding="utf-8").read()
                    self.assertIn(f"name: td-{n}", md)
                    self.assertIn("maxTurns:", md)
                self.assertIn("model: haiku", open(os.path.join(cd, "agents", "td-research.md")).read())
                self.assertIn("hook installed: yes", GI.status())
                GI.set_enabled(False)
                self.assertIn("OFF", GI.status())
                GI.remove_hook()
                data = json.load(open(os.path.join(cd, "settings.json")))
                self.assertFalse(GI.hook_installed(data))
                self.assertEqual(data["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "other")
            finally:
                os.environ.pop("TEAMDESK_CLAUDE_DIR"); os.environ.pop("TEAMDESK_HOME")


class GlobalCost(unittest.TestCase):
    def test_global_report_flags(self):
        from teamdesk import cost
        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, "C--Users-x-proj", "sess1", "subagents")
            os.makedirs(d)
            def write(name, agent, turns):
                with open(os.path.join(d, name + ".jsonl"), "w") as f:
                    for i in range(turns):
                        f.write(json.dumps({"type": "assistant", "timestamp": "2026-10-09T02:00:00Z", "agentName": agent,
                                            "message": {"model": "claude-haiku-5-5", "usage": {"input_tokens": 10, "output_tokens": 5}}}) + chr(10))
            write("a1", "td-research", 5)
            write("a2", "general-purpose", 3)
            write("a3", "td-research", 45)
            rep = cost.global_report(hours=24, root=root)
            by = {(t["name"], t["turns"]): t["alert"] for t in rep["rows"]}
            self.assertEqual(by[("td-research", 5)], False)
            self.assertEqual(by[("general-purpose", 3)], True)
            self.assertEqual(by[("td-research", 45)], True)
            self.assertIn("!!", cost.render_global(rep))


if __name__ == "__main__":
    unittest.main()
