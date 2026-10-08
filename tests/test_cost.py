import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from teamdesk import cost as C
from teamdesk import roster as R


def line(ts, model="claude-opus-5-5", cr=0, cw=0, inp=0, out=0, agent=None):
    d = {"type": "assistant", "timestamp": ts, "message": {"model": model, "usage": {
        "input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw}}}
    if agent:
        d["agentName"] = agent
    return json.dumps(d)


class CostTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        self.proj = os.path.join(self.tmp.name, "proj")
        os.makedirs(self.proj)
        self.patch = mock.patch.object(C, "projects_root", lambda: os.path.join(self.home, ".claude", "projects"))
        self.patch.start()
        self.tdir = C.transcript_dir(self.proj)
        os.makedirs(os.path.join(self.tdir, "s1", "subagents"))
        now = datetime.now(timezone.utc)
        self.recent = (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
        self.old = (now - timedelta(days=2)).isoformat().replace("+00:00", "Z")
        self.write("lead.jsonl", [line(self.recent, cr=1_000_000, out=10_000)])
        self.write("b.jsonl", [line(self.recent, model="claude-sonnet-5-5", cr=100_000, cw=8_000, agent="td-build"),
                               line(self.recent, model="claude-sonnet-5-5", cr=100_000, agent="td-build")])
        self.write("old.jsonl", [line(self.old, cr=9_000_000, agent="td-research")])
        self.write(os.path.join("s1", "subagents", "agent-x.jsonl"), [line(self.recent, model="claude-haiku-4-5", inp=500)])
        with open(os.path.join(self.tdir, "s1", "subagents", "agent-x.meta.json"), "w") as f:
            json.dump({"name": "scout"}, f)

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def write(self, rel, lines):
        with open(os.path.join(self.tdir, rel), "w", encoding="utf-8") as f:
            f.write("\n".join(lines + ["not json"]) + "\n")

    def test_weighting_and_grouping(self):
        rep = C.report(self.proj, all_sessions=True)
        rows = {r["name"]: r for r in rep["rows"]}
        self.assertEqual(set(rows), {"lead", "build", "research", "scout"})
        self.assertEqual(rows["build"]["turns"], 2)
        self.assertAlmostEqual(C.weighted(rows["lead"]), 1_000_000 * 0.1 + 10_000 * 5)
        self.assertAlmostEqual(C.weighted(rows["build"]), 200_000 * 0.1 + 8_000 * 1.25)
        self.assertEqual(rep["rows"][0]["name"], "research")  # biggest first

    def test_window_since_last_up(self):
        C.mark_run_start(self.proj)
        self.assertEqual(C.report(self.proj)["rows"], [])  # everything predates the run start
        rep = C.report(self.proj, since_hours=1)
        self.assertNotIn("research", {r["name"] for r in rep["rows"]})

    def test_thresholds_and_render(self):
        rep = C.report(self.proj, since_hours=1)  # 150k + 30k + 500 = 180.5k weighted
        budget = {**R.DEFAULT_BUDGET, "total_tokens": 300_000}
        self.assertEqual(C.threshold_hit(rep, budget), 0.5)
        self.assertIsNone(C.threshold_hit(rep, {**budget, "total_tokens": 10_000_000}))
        out = C.render(rep, budget)
        self.assertIn("past 50%", out)
        self.assertIn("sonnet", out)
        self.assertIn("lead", C.render(rep, budget, short=True))


if __name__ == "__main__":
    unittest.main()
