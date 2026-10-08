import os
import tempfile
import unittest

from teamdesk import generate as G
from teamdesk import roster as R


def sample():
    return {
        "project": "demo",
        "members": [
            {"name": "research", "work": "research", "role": "Map competitors.", "owns": ["docs/research/**"]},
            {"name": "design", "work": "design", "skill": "replica-design", "after": ["research"],
             "owns": ["docs/design/**"]},
            {"name": "build", "work": "code", "role": "Build the app.", "after": ["design"], "max_turns": 40,
             "owns": ["web/**"]},
        ],
    }


class RosterTest(unittest.TestCase):
    def test_defaults_by_work_type(self):
        r = R.normalise(sample())
        models = {m["name"]: m["model"] for m in r["members"]}
        self.assertEqual(models, {"research": "haiku", "design": "sonnet", "build": "opus"})
        self.assertEqual(r["leader"]["model"], "opus")
        self.assertEqual(r["budget"]["max_active"], 2)
        build = r["members"][2]
        self.assertEqual(build["max_turns"], 40)
        self.assertIn("Bash", build["tools"])
        self.assertNotIn("WebFetch", build["tools"])

    def test_order_follows_dependencies(self):
        self.assertEqual(R.order(R.normalise(sample())), ["research", "design", "build"])

    def test_cycle_is_rejected(self):
        d = sample()
        d["members"][0]["after"] = ["build"]
        with self.assertRaisesRegex(R.RosterError, "cycle"):
            R.normalise(d)

    def test_invalid_inputs(self):
        cases = [
            ({"members": []}, "at least one"),
            ({"members": [{"name": "Bad Name", "work": "code", "role": "x"}]}, "lowercase"),
            ({"members": [{"name": "a", "work": "magic", "role": "x"}]}, "work"),
            ({"members": [{"name": "a", "work": "code"}]}, "role"),
            ({"members": [{"name": "a", "work": "code", "role": "x", "model": "gpt"}]}, "model"),
            ({"members": [{"name": "a", "work": "code", "role": "x", "after": ["zz"]}]}, "unknown"),
            ({"members": [{"name": "a", "work": "code", "role": "x"}, {"name": "a", "work": "code", "role": "y"}]},
             "duplicate"),
        ]
        for data, msg in cases:
            with self.subTest(msg=msg), self.assertRaisesRegex(R.RosterError, msg):
                R.normalise(data)

    def test_warnings(self):
        d = sample()
        d["members"] += [{"name": f"x{i}", "work": "doc", "role": "y"} for i in range(2)]
        w = R.warnings(R.normalise(d), dirs=["/nonexistent"])
        self.assertTrue(any("recommended max" in x for x in w))
        self.assertTrue(any("replica-design" in x for x in w))
        self.assertTrue(any("no 'owns'" in x for x in w))


class GenerateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, *p):
        with open(os.path.join(self.dir, *p), encoding="utf-8") as f:
            return f.read()

    def test_agent_files(self):
        G.generate(R.normalise(sample()), self.dir)
        md = self.read(".claude", "agents", "td-build.md")
        self.assertTrue(md.startswith("---\nname: td-build\n"))
        self.assertIn("model: opus", md)
        self.assertIn("maxTurns: 40", md)
        self.assertIn("`web/**`", md)
        self.assertIn(".team-desk/status/design.done", md)
        design = self.read(".claude", "agents", "td-design.md")
        self.assertIn("`replica-design` skill", design)
        self.assertTrue(os.path.isdir(os.path.join(self.dir, ".team-desk", "status")))

    def test_claude_md_block_is_idempotent_and_preserves_text(self):
        with open(os.path.join(self.dir, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# My project\n\nKeep me.\n")
        r = R.normalise(sample())
        G.generate(r, self.dir)
        G.generate(r, self.dir)
        text = self.read("CLAUDE.md")
        self.assertIn("Keep me.", text)
        self.assertEqual(text.count(G.BLOCK_START), 1)
        self.assertIn("| build | `td-build` | opus |", text)
        self.assertIn("Never spawn `general-purpose`", text)

    def test_removed_member_agent_is_deleted_but_foreign_agents_kept(self):
        G.generate(R.normalise(sample()), self.dir)
        foreign = os.path.join(self.dir, ".claude", "agents", "mine.md")
        open(foreign, "w").close()
        d = sample()
        d["members"] = d["members"][:2]
        G.generate(R.normalise(d), self.dir)
        agents = sorted(os.listdir(os.path.join(self.dir, ".claude", "agents")))
        self.assertEqual(agents, ["mine.md", "td-design.md", "td-research.md"])


if __name__ == "__main__":
    unittest.main()
