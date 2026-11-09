"""EPUB extraction and section-boundary regression checks."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import ModuleType
from zipfile import ZipFile

from document_loader import load_sections, chunk_sections
from langchain_core.documents import Document
from retrieval import expand_context


class DocumentLoaderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "book.epub"

    def write_book(self, body, first_href="first.xhtml"):
        with ZipFile(self.path, "w") as book:
            book.writestr("META-INF/container.xml", '''<container><rootfiles>
                <rootfile full-path="OPS/book.opf"/></rootfiles></container>''')
            book.writestr("OPS/book.opf", f'''<package xmlns="http://www.idpf.org/2007/opf">
                <manifest>
                <item id="second" href="second.xhtml" media-type="application/xhtml+xml"/>
                <item id="first" href="{first_href}" media-type="application/xhtml+xml"/>
                <item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>
                </manifest><spine><itemref idref="first"/><itemref idref="nav"/>
                <itemref idref="second" linear="no"/></spine></package>''')
            book.writestr("OPS/first.xhtml", body)
            book.writestr("OPS/second.xhtml", "<html><body>excluded</body></html>")
            book.writestr("OPS/nav.xhtml", "<html><body>navigation</body></html>")

    def test_body_headings_entities_and_noncontent(self):
        self.write_book('''<html><head><title>Excluded title</title></head><body>
            <nav>Excluded navigation</nav><h1>第一章</h1><p>甲&amp;乙</p>
            <script>Excluded script</script><h2>第二节</h2><p>丙<b>丁</b>。</p>
            </body></html>''')
        sections = load_sections(self.path)
        self.assertEqual([s.title for s in sections], ["第一章", "第二节"])
        self.assertEqual([s.text for s in sections], ["第一章\n甲&乙", "第二节\n丙丁。"])
        self.assertNotEqual(sections[0].location, sections[1].location)
        chunks, metadata = chunk_sections(sections, "zh", lambda text, lang: [text], "book.epub")
        self.assertEqual(len(chunks), 2)
        self.assertEqual([m["index"] for m in metadata], [0, 1])
        self.assertEqual(metadata[1]["chapter"], "第二节")

    def test_spine_order_overrides_archive_and_manifest_order(self):
        self.write_book("<html><body><p>first</p></body></html>")
        with ZipFile(self.path, "a") as book:
            book.writestr("OPS/book2.opf", '''<package><manifest>
                <item id="b" href="second.xhtml" media-type="application/xhtml+xml"/>
                <item id="a" href="first.xhtml" media-type="application/xhtml+xml"/>
                </manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>''')
            # The alternate container is exercised by replacing the fixture archive.
            entries = {e.filename: book.read(e) for e in book.infolist()}
        entries["META-INF/container.xml"] = b'<container><rootfile full-path="OPS/book2.opf"/></container>'
        with ZipFile(self.path, "w") as book:
            for name, data in entries.items():
                book.writestr(name, data)
        self.assertEqual([s.text for s in load_sections(self.path)], ["first", "excluded"])

    def test_invalid_and_empty_epub(self):
        self.path.write_bytes(b"invalid")
        with self.assertRaisesRegex(ValueError, "invalid"):
            load_sections(self.path)
        self.write_book("<html><body> </body></html>")
        with self.assertRaisesRegex(ValueError, "no readable"):
            load_sections(self.path)

    def test_resource_cannot_escape_archive_root(self):
        self.write_book("<html><body>text</body></html>", "../../outside.xhtml")
        with self.assertRaisesRegex(ValueError, "invalid resource"):
            load_sections(self.path)

    def test_text_formats_keep_original_content(self):
        for extension in (".txt", ".md", ".markdown"):
            path = Path(self.directory.name) / f"source{extension}"
            path.write_text("# 标题\n\n正文", encoding="utf-8")
            sections = load_sections(path)
            self.assertEqual(sections[0].text, "# 标题\n\n正文")
            _, metadata = chunk_sections(sections, "zh", lambda text, lang: [text], path.name)
            self.assertEqual(metadata, [{"index": 0, "source": path.name}])

    def test_neighbors_respect_sections_and_legacy_documents(self):
        class Store:
            def __init__(self, docs):
                self.docs = docs

            def get(self, **kwargs):
                return {"ids": [str(i) for i in range(len(self.docs))],
                        "documents": [d.page_content for d in self.docs],
                        "metadatas": [d.metadata for d in self.docs]}

        class Tokenizer:
            def encode(self, text, **kwargs):
                return list(text)

        docs = [Document(page_content=str(i), metadata={"source": "book", "index": i,
                         "section": "a" if i < 2 else "b"}) for i in range(3)]
        context = expand_context(Store(docs), [docs[1]], Tokenizer())
        self.assertEqual([d.page_content for d in context], ["1", "0"])
        for doc in docs:
            doc.metadata.pop("section")
        context = expand_context(Store(docs), [docs[1]], Tokenizer())
        self.assertEqual([d.page_content for d in context], ["1", "0", "2"])

    def test_upload_handler_passes_section_metadata_and_invalidates_after_write(self):
        import tasks

        self.write_book("<html><body><h1>第一章</h1><p>正文</p></body></html>")
        events = []
        store = Mock()
        store.get.return_value = {"ids": ["old"]}
        store.delete.side_effect = lambda **kwargs: events.append("delete")
        store.add_texts.side_effect = lambda *args, **kwargs: events.append("add")
        rag = ModuleType("rag_langchain")
        rag.detect_lang = lambda text: "zh"
        rag.split_by_tokens = lambda text, lang: [text]
        rag.load_store = Mock()
        rag.get_all_chunks_in_order = lambda store: []
        rag.save_chunks_to_file = Mock()
        rag.invalidate_caches = lambda: events.append("invalidate") or 0
        rag.LANG_COLLECTIONS = {"zh": "rag_zh"}
        with patch.dict("sys.modules", {"rag_langchain": rag}), patch.object(tasks, "_get_worker_store", return_value=store):
            result = tasks.process_upload_file({"saved_path": str(self.path), "filename": "book.epub"})
            self.assertEqual(result["chunk_count"], 1)
            self.assertEqual(events, ["delete", "add", "invalidate"])
            metadata = store.add_texts.call_args.kwargs["metadatas"][0]
            self.assertEqual(metadata["chapter"], "第一章")
            self.assertEqual(metadata["source"], "book.epub")
            events.clear()
            self.path.write_bytes(b"broken")
            with self.assertRaises(ValueError):
                tasks.process_upload_file({"saved_path": str(self.path)})
            self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
