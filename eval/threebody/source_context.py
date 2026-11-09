"""Render source identity and chapter metadata alongside unchanged excerpt text."""
import json


def source_metadata(sources):
    result = []
    seen = set()
    for source in sources:
        metadata = source["metadata"]
        index = metadata["index"]
        if type(index) is not int:
            raise ValueError("Source index must be an integer")
        identifier = f"chunk-{index}"
        if identifier in seen:
            raise ValueError("Duplicate source identifier")
        seen.add(identifier)
        result.append({"id": identifier, "book": metadata.get("book_title", ""),
                       "chapter": metadata.get("parent_chapter", metadata.get("chapter", "")),
                       "section": metadata.get("section", ""), "source": metadata.get("source", "")})
    return result


def render_sources(sources):
    labels = source_metadata(sources)
    return ("以下 SOURCE 标签为片段的来源元数据。引用章节或片段编号时以对应标签为准；"
            "不要将其他章节的内容归到问题指定章节。无法由资料确认的来源关系应说明无法确认。\n\n" +
            "\n\n".join(f"[SOURCE {json.dumps(label, ensure_ascii=False)}]\n{source['text']}\n[/SOURCE]"
                          for label, source in zip(labels, sources)))
