"""Review verification must distinguish unseen corpus text from retrieved evidence."""
import unittest
from eval.threebody.review_and_freeze import validate_evidence


class ReviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.corpus = {0: {"text": "observed evidence", "metadata": {"index": 0}},
                       1: {"text": "unseen evidence", "metadata": {"index": 1}}}
        self.sources = [self.corpus[0]]

    def claim(self, index, scope):
        return {"answer_anchor": "claim", "evidence": [
            {"index": index, "quote": self.corpus[index]["text"], "scope": scope}]}

    def test_valid_seen_and_unseen_scopes(self):
        validate_evidence(self.claim(0, "retrieved"), "claim", self.sources, self.corpus)
        validate_evidence(self.claim(1, "corpus_only"), "claim", self.sources, self.corpus)

    def test_unseen_evidence_cannot_be_treated_as_seen(self):
        with self.assertRaises(ValueError):
            validate_evidence(self.claim(1, "retrieved"), "claim", self.sources, self.corpus)

    def test_quote_and_answer_anchor_must_exist(self):
        with self.assertRaises(ValueError):
            validate_evidence(self.claim(0, "retrieved"), "different answer", self.sources, self.corpus)
        claim = self.claim(0, "retrieved")
        claim["evidence"][0]["quote"] = "altered quote"
        with self.assertRaises(ValueError):
            validate_evidence(claim, "claim", self.sources, self.corpus)


if __name__ == "__main__":
    unittest.main()
