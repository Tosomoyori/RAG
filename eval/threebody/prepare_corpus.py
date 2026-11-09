"""Prepare, build and verify isolated Three-Body Problem corpus indexes."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from document_loader import Section, load_epub, chunk_sections

DIRECTORY = Path(__file__).resolve().parent
CONFIG_PATH = DIRECTORY / "corpus_config.json"
PUBLIC = ROOT / "eval/corpora/threebody"
LOCAL = PUBLIC / "local"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def extract(config):
    source = ROOT / config["source"]
    if file_hash(source) != config["source_sha256"]:
        raise ValueError("Source EPUB hash differs from the frozen corpus configuration")
    result = []
    resources = set()
    for section in load_epub(source):
        number = int(re.search(r"part(\d+)\.xhtml", section.location)[1])
        resources.add(number)
        book = next((b for b in config["books"] if b["resources"][0] <= number <= b["resources"][1]), None)
        if book is None:
            if str(number) not in config["excluded_resources"]:
                raise ValueError(f"Unclassified resource: {section.location}")
            continue
        # Exact standalone markers supply additional boundaries in volume three.
        matches = list(re.finditer(r"(?m)^【[^【】\n]{1,100}】$", section.text))
        starts = [0] + [m.start() for m in matches if m.start() > 0]
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(section.text)
            text = section.text[start:end].rstrip("\n")
            if not text.strip():
                continue
            title = section.title if start == 0 else text.splitlines()[0].strip("【】")
            location = f"{section.location}/scene-{index}"
            result.append({"book": book["id"], "book_title": book["title"],
                           "chapter": section.title, "title": title, "location": location,
                           "parent_location": section.location, "parent_char_start": start,
                           "parent_char_end": start + len(text), "text": text,
                           "text_sha256": digest(text.encode("utf-8"))})
    expected = set(range(61))
    if resources != expected:
        raise ValueError("EPUB resource coverage differs from the configured edition")
    return result


def setup_runtime(config, scope):
    index = (ROOT / "eval/indexes/threebody" / scope).resolve()
    if index == (ROOT / "chroma_db").resolve():
        raise ValueError("Experiment index must differ from the application index")
    os.environ["RAG_INDEX_DIR"] = str(index)
    os.environ["RAG_ARTIFACT_DIR"] = str(LOCAL / scope)
    os.environ["CHUNK_TOKENS"] = str(config["chunk_tokens"])
    os.environ["CHUNK_OVERLAP_TOKENS"] = str(config["chunk_overlap_tokens"])
    os.environ["CACHE_BACKEND"] = "memory"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    os.chdir(ROOT)
    import rag_langchain as rag
    if Path(rag.CHROMA_DB_PATH) != index:
        raise ValueError("Runtime index directory mismatch")
    return rag, index


def prepare(config, scope):
    rows = [row for row in extract(config) if row["book"] in config["scopes"][scope]]
    rag, index = setup_runtime(config, scope)
    sections = [Section(row["text"], row["title"], row["location"]) for row in rows]
    texts, metadata = chunk_sections(sections, "zh", rag.split_by_tokens, config["source"])
    by_location = {row["location"]: row for row in rows}
    chunks = []
    for text, item in zip(texts, metadata):
        row = by_location[item["section"]]
        item.update(book=row["book"], book_title=row["book_title"],
                    parent_chapter=row["chapter"], corpus=scope,
                    text_sha256=digest(text.encode("utf-8")))
        chunks.append({"text": text, "metadata": item})
    destination = LOCAL / scope
    write_json(destination / "sections.json", rows)
    write_json(destination / "chunks.json", chunks)
    code_files = [CONFIG_PATH, Path(__file__), ROOT / "document_loader.py", ROOT / "rag_langchain.py"]
    model = ROOT / rag.LANG_MODELS["zh"]
    model_files = sorted(p for p in model.rglob("*") if p.is_file() and (
        p.suffix in (".json", ".txt", ".safetensors", ".bin", ".model")))
    manifest = {
        "scope": scope, "source_sha256": config["source_sha256"],
        "index_directory": index.relative_to(ROOT).as_posix(), "collection": "rag_zh",
        "chunk_tokens": rag.CHUNK_TOKENS, "chunk_overlap_tokens": rag.CHUNK_OVERLAP_TOKENS,
        "embedding_model": rag.LANG_MODELS["zh"], "embedding_max_seq": rag.LANG_MAX_SEQ["zh"],
        "packages": {name: importlib.metadata.version(name) for name in
                     ("chromadb", "transformers", "sentence-transformers", "langchain-chroma")},
        "files_sha256": {p.relative_to(ROOT).as_posix(): file_hash(p) for p in code_files + model_files},
        "sections_sha256": file_hash(destination / "sections.json"),
        "chunks_sha256": file_hash(destination / "chunks.json"),
        "section_count": len(rows), "chunk_count": len(chunks),
        "characters": sum(len(row["text"]) for row in rows),
        "sections": [{k: v for k, v in row.items() if k != "text"} |
                     {"characters": len(row["text"])} for row in rows],
        "excluded_resources": config["excluded_resources"], "policies": config["policies"],
    }
    write_json(PUBLIC / f"{scope}.manifest.json", manifest)
    print(json.dumps({"scope": scope, "sections": len(rows), "chunks": len(chunks),
                      "characters": manifest["characters"]}, ensure_ascii=False), flush=True)


def frozen(config, scope):
    manifest = read_json(PUBLIC / f"{scope}.manifest.json")
    if manifest["source_sha256"] != file_hash(ROOT / config["source"]):
        raise ValueError("Source hash mismatch")
    for name, expected in manifest["files_sha256"].items():
        if file_hash(ROOT / name) != expected:
            raise ValueError(f"Frozen dependency changed: {name}; prepare corpus again")
    for name in ("sections", "chunks"):
        if file_hash(LOCAL / scope / f"{name}.json") != manifest[f"{name}_sha256"]:
            raise ValueError(f"Frozen {name} changed")
    return manifest, read_json(LOCAL / scope / "chunks.json")


def verify_store(store, chunks):
    data = store.get(include=["documents", "metadatas"])
    actual = {identifier: (text, metadata) for identifier, text, metadata in
              zip(data["ids"], data["documents"], data["metadatas"])}
    expected = {f"chunk-{i}": (row["text"], row["metadata"]) for i, row in enumerate(chunks)}
    if actual != expected:
        raise ValueError("Index content/metadata differs from the frozen corpus")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "build", "verify"))
    parser.add_argument("--scope", choices=("book1", "trilogy"), required=True)
    args = parser.parse_args()
    config = read_json(CONFIG_PATH)
    if args.action == "prepare":
        prepare(config, args.scope)
        return
    manifest, chunks = frozen(config, args.scope)
    rag, index = setup_runtime(config, args.scope)
    store = rag.load_store("zh")
    if args.action == "build" and store._collection.count() == 0:
        for start in range(0, len(chunks), 64):
            batch = chunks[start:start + 64]
            store.add_texts([r["text"] for r in batch],
                            metadatas=[r["metadata"] for r in batch],
                            ids=[f"chunk-{i}" for i in range(start, start + len(batch))])
            print(f"{args.scope}: {start + len(batch)}/{len(chunks)} chunks", flush=True)
    # Existing or interrupted indexes are never silently overwritten.
    verify_store(store, chunks)
    write_json(LOCAL / args.scope / "index-verification.json", {
        "scope": args.scope, "index_directory": str(index), "chunk_count": len(chunks),
        "chunks_sha256": manifest["chunks_sha256"], "content_and_metadata_match": True})
    print(f"Verified {args.scope}: {len(chunks)} chunks", flush=True)


if __name__ == "__main__":
    main()
