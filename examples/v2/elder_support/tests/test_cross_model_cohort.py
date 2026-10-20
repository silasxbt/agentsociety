"""Offline tests: no model calls, no production writes."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("cohort", TOOLS / "cross_model_cohort.py")
cohort = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cohort)


class CohortTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / "base"
        for c in cohort.CONDITIONS:
            for s in cohort.SEEDS:
                d = self.base / f"{c}_s{s}"
                d.mkdir(parents=True)
                config = {"env_modules": [{"kwargs": {"elders": [
                    {"id": 1, "focal": True}, {"id": 2, "focal": True}]}}]}
                (d / "init_config.json").write_text(json.dumps(config))
                (d / "steps.yaml").write_text("steps: 24\n")

    def populate(self, root, shift=0):
        for c in cohort.CONDITIONS:
            for s in cohort.SEEDS:
                d = root / f"{c}_s{s}"
                state = d / "env/ElderSupportEnv/state"
                state.mkdir(parents=True)
                value = .4 if c == "none" else .2 + shift
                rows = [dict(month=m, isolation_rate=value, avg_loneliness=value,
                             deep_isolation_rate=.1, avg_active_ties=3) for m in range(25)]
                (state / "metrics.jsonl").write_text("\n".join(map(json.dumps, rows)))
                rows = [dict(month=m, agent_id=a, action="call_family")
                        for a in (1, 2) for m in range(25)]
                (state / "decisions.jsonl").write_text("\n".join(map(json.dumps, rows)))
                (d / "trace").mkdir()
                (d / "trace/trace_test.jsonl").write_text(json.dumps(
                    {"name": "llm.completion", "status": {"code": "ok"}}))
                (d / "DONE").touch()

    def test_prepare_exact_eight_and_no_overwrite(self):
        target = self.root / "new"
        cohort.prepare(self.base, target)
        self.assertEqual(len(list(target.iterdir())), 8)
        for d in target.iterdir():
            self.assertEqual((d / "init_config.json").read_bytes(),
                             (self.base / d.name / "init_config.json").read_bytes())
            self.assertEqual(json.loads((d / "manifest.json").read_text())["reasoning_effort"], "medium")
        with self.assertRaises(ValueError):
            cohort.prepare(self.base, target)

    def test_missing_source_leaves_no_partial_cohort(self):
        (self.base / "none_s1/steps.yaml").unlink()
        with self.assertRaises(ValueError):
            cohort.prepare(self.base, self.root / "new")
        self.assertFalse((self.root / "new").exists())

    def test_paired_differences_and_exclusions(self):
        target = self.root / "new"
        cohort.prepare(self.base, target)
        self.populate(self.base)
        self.populate(target, shift=.1)
        result = cohort.report(self.base, target)
        self.assertEqual(len(result["paired_contrasts"]), 6)
        row = result["paired_contrasts"][0]
        self.assertTrue(row["eligible"])
        self.assertAlmostEqual(row["outcomes"]["isolation_rate_iv"]["difference_in_differences"], .1)
        (target / "casework_s1/INVALID").touch()
        self.assertFalse(cohort.report(self.base, target)["paired_contrasts"][0]["eligible"])

    def test_fully_silent_agent_detected(self):
        self.populate(self.base)
        run = self.base / "none_s1"
        path = run / "env/ElderSupportEnv/state/decisions.jsonl"
        rows = [r for r in cohort.read_lines(path) if r["agent_id"] == 1]
        path.write_text("\n".join(map(json.dumps, rows)))
        result = cohort.summarize(run)
        self.assertTrue(result["legacy_valid"])
        self.assertFalse(result["valid"])
        self.assertEqual(result["fixed_roster_silence"], .5)

    def test_corrupt_data_fails_closed(self):
        self.populate(self.base)
        run = self.base / "none_s1"
        (run / "trace/trace_test.jsonl").write_text("broken json")
        self.assertFalse(cohort.summarize(run)["valid"])

    def test_report_includes_third_model_vs_none(self):
        astra = self.root / "astra"
        opus = self.root / "opus"
        cohort.prepare(self.base, astra)
        cohort.prepare(self.base, opus, model="claude-opus-5-5", provider="anthropic",
                       cohort="opus")
        self.populate(self.base)
        self.populate(astra, shift=.1)
        self.populate(opus, shift=.05)
        result = cohort.report(self.base, astra, extra_cohorts={"opus_medium": opus})
        row = result["paired_contrasts"][0]
        self.assertTrue(row["eligible"])
        self.assertAlmostEqual(row["outcomes"]["isolation_rate_iv"]["opus_medium_vs_none"], -.15)
        self.assertIn("opus_medium", result["runs"])

    def test_prepare_records_provider_and_third_seed(self):
        target = self.root / "opus"
        (self.base / "none_s3").mkdir(parents=True)
        (self.base / "none_s3/init_config.json").write_text(
            (self.base / "none_s1/init_config.json").read_text()
        )
        (self.base / "none_s3/steps.yaml").write_text("steps: 24\n")
        for c in cohort.CONDITIONS:
            if c == "none":
                continue
            d = self.base / f"{c}_s3"
            d.mkdir()
            (d / "init_config.json").write_text((self.base / f"{c}_s1/init_config.json").read_text())
            (d / "steps.yaml").write_text("steps: 24\n")
        cohort.prepare(
            self.base, target, model="claude-opus-5-5", reasoning_effort="medium",
            provider="anthropic", cohort="opus_medium_v2", seeds=(1, 2, 3),
        )
        self.assertEqual(len(list(target.iterdir())), 12)
        m = json.loads((target / "none_s1/manifest.json").read_text())
        self.assertEqual(m["model"], "claude-opus-5-5")
        self.assertEqual(m["provider"], "anthropic")
        self.assertTrue((target / "platform_s3/manifest.json").is_file())

    def test_config_mismatch_excluded(self):
        target = self.root / "new"
        cohort.prepare(self.base, target)
        self.populate(self.base)
        self.populate(target)
        (target / "casework_s1/steps.yaml").write_text("changed")
        row = cohort.report(self.base, target)["paired_contrasts"][0]
        self.assertFalse(row["matching_configs"])
        self.assertFalse(row["eligible"])


if __name__ == "__main__":
    unittest.main()
