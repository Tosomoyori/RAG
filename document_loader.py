"""Document extraction with ordered, chapter-aware EPUB sections."""
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import posixpath
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from zipfile import ZipFile, BadZipFile


SUPPORTED_EXTENSIONS = (".pdf", ".md", ".markdown", ".txt", ".epub")


@dataclass(frozen=True)
class Section:
    text: str
    title: str = ""
    location: str = ""


class _ChapterParser(HTMLParser):
    """Extract body text and split at explicit headings; omit navigation markup."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_body = False
        self.suppressed = []
        self.heading = None
        self.heading_text = []
        self.title = ""
        self.parts = []
        self.sections = []

    def flush(self):
        text = "\n".join(line.strip() for line in "".join(self.parts).splitlines()
                         if line.strip())
        if text:
            self.sections.append((self.title, text))
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.in_body = True
        if not self.in_body:
            return
        if tag in ("script", "style", "nav"):
            self.suppressed.append(tag)
        if self.suppressed:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.flush()
            self.heading = tag
            self.heading_text = []
        if tag in ("p", "div", "br", "li", "tr", "section", "blockquote"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.suppressed:
            if tag == self.suppressed[-1]:
                self.suppressed.pop()
            return
        if tag == self.heading:
            self.title = "".join(self.heading_text).strip()
            self.parts.append("\n")
            self.heading = None
        if tag in ("p", "div", "li", "tr", "section", "blockquote"):
            self.parts.append("\n")
        if tag == "body":
            self.in_body = False

    def handle_data(self, data):
        if self.in_body and not self.suppressed:
            self.parts.append(data)
            if self.heading:
                self.heading_text.append(data)


def _member_path(base, href):
    path = posixpath.normpath(posixpath.join(base, unquote(href.split("#", 1)[0])))
    if path.startswith(("../", "/")) or path == "..":
        raise ValueError("EPUB contains an invalid resource path")
    return path


def load_epub(path):
    """Read XHTML resources in OPF spine order without extracting archive files."""
    try:
        with ZipFile(path) as book:
            container = ET.fromstring(book.read("META-INF/container.xml"))
            rootfile = container.find(".//{*}rootfile")
            if rootfile is None:
                raise ValueError("EPUB has no package document")
            package_path = _member_path("", rootfile.attrib["full-path"])
            package = ET.fromstring(book.read(package_path))
            base = posixpath.dirname(package_path)
            manifest = {item.attrib["id"]: item for item in package.findall("{*}manifest/{*}item")}
            sections = []
            for ref in package.findall("{*}spine/{*}itemref"):
                if ref.get("linear", "yes") == "no":
                    continue
                item = manifest[ref.attrib["idref"]]
                if "nav" in item.get("properties", "").split():
                    continue
                if item.get("media-type") not in ("application/xhtml+xml", "text/html"):
                    continue
                resource = _member_path(base, item.attrib["href"])
                parser = _ChapterParser()
                parser.feed(book.read(resource).decode("utf-8-sig"))
                parser.close()
                parser.flush()
                for number, (title, text) in enumerate(parser.sections):
                    sections.append(Section(text, title, f"{resource}#section-{number}"))
            if not sections:
                raise ValueError("EPUB contains no readable text")
            return sections
    except (BadZipFile, KeyError, ET.ParseError, UnicodeError) as exc:
        raise ValueError("EPUB package or text is invalid or unsupported") from exc


def load_sections(path):
    """Load supported formats; preserve the existing PDF/text extraction behavior."""
    path = str(path)
    if not Path(path).is_file():
        raise FileNotFoundError(f"找不到文档：{path}")
    extension = Path(path).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支持的文件类型：{extension}")
    if extension == ".epub":
        return load_epub(path)
    if extension == ".pdf":
        from langchain_community.document_loaders import PyMuPDFLoader
        return [Section("".join(page.page_content for page in PyMuPDFLoader(path).load()))]
    return [Section(Path(path).read_text(encoding="utf-8"))]


def chunk_sections(sections, lang, splitter, source):
    """Assign global chunk positions and retain EPUB section identifiers."""
    chunks, metadata = [], []
    for section in sections:
        for text in splitter(section.text, lang):
            item = {"index": len(chunks), "source": source}
            if section.location:
                item.update(section=section.location, chapter=section.title)
            chunks.append(text)
            metadata.append(item)
    return chunks, metadata
