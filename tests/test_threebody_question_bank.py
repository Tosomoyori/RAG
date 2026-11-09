"""Question partition integrity and abstention evidence metric checks."""
from pathlib import Path
import runpy
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILDER = runpy.run_path(str(ROOT / "eval/threebody/build_question_bank.py"))
METRICS = runpy.run_path(str(ROOT / "eval/threebody/evidence_metrics.py"))["evidence_metrics"]


class QuestionBankTests(unittest.TestCase):
    def test_abstention_coverage_is_not_perfect_coverage(self):
        result = METRICS({"behavior": "abstain", "evidence": []}, [1, 2])
        self.assertIsNone(result["evidence_coverage"])
        self.assertIsNone(result["all_evidence_found"])
        self.assertFalse(result["evidence_applicable"])

    def test_alternatives_cover_a_fact_but_not_other_required_facts(self):
        case = {"behavior": "answer", "evidence": [
            {"acceptable_indexes": [1, 2]}, {"acceptable_indexes": [9]}]}
        self.assertEqual(METRICS(case, [2])["evidence_coverage"], 0.5)
        self.assertFalse(METRICS(case, [2])["all_evidence_found"])
        self.assertTrue(METRICS(case, [2, 9])["all_evidence_found"])

    def test_answerable_case_cannot_have_empty_evidence(self):
        with self.assertRaises(ValueError):
            METRICS({"behavior": "answer", "evidence": []}, [])

    def test_knowledge_group_cannot_cross_split(self):
        cases = [{"id": f"d{i}", "question": f"d{i}", "group": f"d{i}", "split": "development"} for i in range(24)]
        cases += [{"id": f"t{i}", "question": f"t{i}", "group": f"t{i}", "split": "holdout"} for i in range(16)]
        BUILDER["validate_split"](cases)
        cases[-1]["group"] = cases[0]["group"]
        with self.assertRaisesRegex(ValueError, "crosses split"):
            BUILDER["validate_split"](cases)


if __name__ == "__main__":
    unittest.main()
