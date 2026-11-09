"""Corpus scope, shared evidence identity and index verification checks."""
from pathlib import Path
import runpy
import unittest

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                            "eval/threebody/prepare_corpus.py"))


class ThreeBodyCorpusTests(unittest.TestCase):
    @unittest.skipUnless((MODULE["ROOT"] / "The Three-Body Problem.epub").exists(),
                         "Local EPUB corpus is unavailable")
    def test_scopes_cover_body_and_keep_narrative_preface(self):
        config = MODULE["read_json"](MODULE["CONFIG_PATH"])
        rows = MODULE["extract"](config)
        first = [r for r in rows if r["book"] == "book1"]
        self.assertEqual(len(first), 36)
        self.assertTrue(first[0]["title"].startswith("第一章"))
        self.assertTrue(first[-1]["title"].startswith("第三十六章"))
        self.assertEqual(len({r["location"] for r in rows}), len(rows))
        self.assertTrue(any(r["title"] == "纪年对照表" for r in rows))
        self.assertTrue(any(r["title"] == "《时间之外的往事》 序言（节选）" for r in rows))
        scenes = [r for r in rows if "/scene-" in r["location"] and
                  r["parent_char_start"] > 0]
        self.assertEqual(len(scenes), 28)
        self.assertTrue(all(r["text"].startswith("【") for r in scenes))
        for row in rows:
            self.assertEqual(row["parent_char_end"] - row["parent_char_start"], len(row["text"]))
            self.assertEqual(row["text_sha256"], MODULE["digest"](row["text"].encode("utf-8")))

    def test_index_verification_rejects_text_or_metadata_changes(self):
        class Store:
            def get(self, **kwargs):
                return {"ids": ["chunk-0"], "documents": ["text"],
                        "metadatas": [{"index": 0, "chapter": "one"}]}
        verify = MODULE["verify_store"]
        verify(Store(), [{"text": "text", "metadata": {"index": 0, "chapter": "one"}}])
        with self.assertRaises(ValueError):
            verify(Store(), [{"text": "text", "metadata": {"index": 0, "chapter": "two"}}])
        with self.assertRaises(ValueError):
            verify(Store(), [{"text": "wrong", "metadata": {"index": 0, "chapter": "one"}}])


if __name__ == "__main__":
    unittest.main()
