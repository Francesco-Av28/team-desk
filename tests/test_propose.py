import json
import os
import tempfile
import unittest
from unittest import mock

from teamdesk import propose as P
from teamdesk import roster as R


def skill(root, name, desc):
    os.makedirs(os.path.join(root, name))
    with open(os.path.join(root, name, "SKILL.md"), "w") as f:
        f.write(f"---\nname: {name}\ndescription: {desc}\n---\nbody\n")


class ProposeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proj = os.path.join(self.tmp.name, "proj")
        self.skills = os.path.join(self.proj, ".claude", "skills")
        os.makedirs(os.path.join(self.proj, "web"))
        skill(self.skills, "replica-recon", "Recon the target app screens and flows")
        skill(self.skills, "replica-design", "Design tokens and UI components")
        skill(self.skills, "replica-build", "Build the app code")
        skill(self.skills, "replica-test", "Test and verify")
        skill(self.skills, "replica-brand", "Brand and design identity")
        with open(os.path.join(self.proj, ".claude", "settings.json"), "w") as f:
            json.dump({"skillOverrides": {"replica-brand": "off"}}, f)
        self.home = mock.patch.dict(os.environ, {"HOME": self.tmp.name, "USERPROFILE": self.tmp.name})
        self.home.start()

    def tearDown(self):
        self.home.stop()
        self.tmp.cleanup()

    def test_pipeline_binds_matching_skills(self):
        data = P.propose(self.proj, dirs=[self.skills])
        r = R.normalise(data)
        got = {m["name"]: (m["skill"], m["model"]) for m in r["members"]}
        self.assertEqual(got, {"research": ("replica-recon", "haiku"), "design": ("replica-design", "sonnet"),
                               "build": ("replica-build", "opus"), "review": ("replica-test", "sonnet")})
        self.assertEqual(R.order(r), ["research", "design", "build", "review"])
        self.assertEqual(r["members"][2]["owns"], ["web/**"])

    def test_whole_word_matching(self):
        s = {"name": "replica-build", "description": "Build the app code"}
        self.assertEqual(P.score(s, "design"), 0)  # 'ui' must not match inside 'build'
        self.assertGreater(P.score(s, "code"), 0)

    def test_disabled_skills_are_skipped(self):
        names = {s["name"] for s in P.list_skills(self.proj, dirs=[self.skills])}
        self.assertNotIn("replica-brand", names)

    def test_no_skills_gives_role_only_team(self):
        r = R.normalise(P.propose(self.proj, dirs=["/nonexistent"]))
        self.assertTrue(all(m["skill"] is None and m["role"] for m in r["members"]))
        self.assertIn("Proposed team", P.describe(P.propose(self.proj, dirs=["/nonexistent"])))


if __name__ == "__main__":
    unittest.main()
