"""Validation of malformed and contradictory semantic grader outputs."""
import unittest
from eval.threebody.semantic_grading import validate_grade


class GradingValidationTests(unittest.TestCase):
    def test_valid_grounded_grade(self):
        grade = {"correctness": 2, "grounding": 2, "behavior": 2, "language": 2,
                 "reason": "Supported by context", "unsupported_claims": []}
        self.assertIs(validate_grade(grade), grade)

    def test_boolean_is_not_a_score(self):
        with self.assertRaises(ValueError):
            validate_grade({"correctness": True})

    def test_full_grounding_conflicts_with_unsupported_claim(self):
        with self.assertRaises(ValueError):
            validate_grade({"correctness": 2, "grounding": 2, "behavior": 2, "language": 2,
                            "reason": "Contradiction", "unsupported_claims": ["Invented price"]})


if __name__ == "__main__":
    unittest.main()
