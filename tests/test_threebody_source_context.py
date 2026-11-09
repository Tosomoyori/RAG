"""Source identity validation and preservation of excerpt text."""
import unittest
from eval.threebody.source_context import render_sources, source_metadata
from eval.threebody.semantic_grading import validate_grade


class SourceContextTests(unittest.TestCase):
    def test_labels_use_actual_metadata_not_question_chapter(self):
        sources = [{"text": "他研究纳米材料", "metadata": {
            "index": 543, "parent_chapter": "第二十二章 地球叛军", "chapter": "子节"}}]
        rendered = render_sources(sources)
        self.assertIn('"id": "chunk-543"', rendered)
        self.assertIn('"chapter": "第二十二章 地球叛军"', rendered)
        self.assertIn("\n他研究纳米材料\n", rendered)

    def test_duplicate_source_ids_are_rejected(self):
        source = {"text": "same", "metadata": {"index": 1}}
        with self.assertRaises(ValueError):
            source_metadata([source, source])

    def test_wrong_source_cannot_receive_full_grounding(self):
        with self.assertRaises(ValueError):
            validate_grade({"correctness": 2, "grounding": 2, "behavior": 2, "language": 2,
                            "reason": "bad source", "unsupported_claims": [], "source_errors": ["Wrong chapter"]})


if __name__ == "__main__":
    unittest.main()
