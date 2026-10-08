import os
import tempfile
import unittest

from teamdesk import roster as R
from teamdesk import status as S


class StatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.r = R.normalise({"members": [
            {"name": "a", "work": "research", "role": "x"},
            {"name": "b", "work": "design", "role": "x", "after": ["a"]},
            {"name": "c", "work": "code", "role": "x", "after": ["a", "b"]},
        ]})
        os.makedirs(os.path.join(self.dir, ".team-desk", "status"))

    def tearDown(self):
        self.tmp.cleanup()

    def mark(self, name, kind="done"):
        with open(os.path.join(self.dir, ".team-desk", "status", f"{name}.{kind}"), "w") as f:
            f.write("summary line\n")

    def test_states_follow_markers_and_processes(self):
        self.assertEqual(S.member_states(self.r, self.dir, running=set()),
                         {"a": "ready", "b": "waiting", "c": "waiting"})
        self.assertEqual(S.member_states(self.r, self.dir, running={"td-a"})["a"], "working")
        self.mark("a")
        self.mark("b", "blocked")
        self.assertEqual(S.member_states(self.r, self.dir, running=set()),
                         {"a": "done", "b": "blocked", "c": "waiting"})

    def test_render_suggests_next(self):
        self.mark("a")
        out = S.render(self.r, self.dir, running=set())
        self.assertIn("next: b", out)
        self.assertIn("summary line", out)
        self.mark("b")
        self.mark("c")
        self.assertIn("all members done", S.render(self.r, self.dir, running=set()))


if __name__ == "__main__":
    unittest.main()
