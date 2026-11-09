"""Lexical fusion and bounded context expansion for document retrieval."""
import math
import re
from collections import Counter

from langchain_core.documents import Document


def lexical_terms(text):
    terms = re.findall(r"[a-z0-9]+", text.casefold())
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        terms.extend(run[i:i + 2] for i in range(len(run) - 1))
        if len(run) == 1:
            terms.append(run)
    return terms


def read_documents(store):
    data = store.get(include=["documents", "metadatas"])
    return [Document(page_content=text, metadata=metadata or {}, id=identifier)
            for identifier, text, metadata in zip(
                data["ids"], data["documents"], data["metadatas"])]


def document_key(document):
    return (document.metadata.get("source"), document.metadata.get("index"),
            document.page_content)


def bm25_rank(question, documents, k):
    """Rank positive matches with BM25, k1=1.5 and b=0.75."""
    counts = [Counter(lexical_terms(document.page_content)) for document in documents]
    average_length = sum(sum(count.values()) for count in counts) / max(len(counts), 1)
    if average_length == 0:
        return []
    query_terms = set(lexical_terms(question))
    frequencies = Counter(term for count in counts for term in query_terms if term in count)
    ranked = []
    for document, count in zip(documents, counts):
        normalization = 1.5 * (0.25 + 0.75 * sum(count.values()) / average_length)
        score = 0.0
        for term in query_terms & count.keys():
            inverse_frequency = math.log(1 + (len(counts) - frequencies[term] + 0.5)
                                         / (frequencies[term] + 0.5))
            score += inverse_frequency * count[term] * 2.5 / (count[term] + normalization)
        if score > 0:
            ranked.append((score, document))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [document for _, document in ranked[:k]]


def retrieve_candidates(store, question, k, mode="vector"):
    if mode not in ("vector", "hybrid"):
        raise ValueError(f"Unsupported retrieval mode: {mode}")
    dense = store.as_retriever(search_kwargs={"k": k}).invoke(question)
    if mode == "vector":
        return dense
    lexical = bm25_rank(question, read_documents(store), k)
    scores = {}
    documents = {}
    for ranking in (dense, lexical):
        for rank, document in enumerate(ranking, 1):
            key = document_key(document)
            documents[key] = document
            scores[key] = scores.get(key, 0.0) + 1 / (60 + rank)
    keys = sorted(scores, key=scores.get, reverse=True)
    return [documents[key] for key in keys[:k]]


def expand_context(store, seeds, tokenizer, radius=1, max_chunks=10, max_tokens=2560):
    """Retain ranked seeds first, then add same-source neighbors within budgets."""
    if radius < 0 or max_chunks < 1 or max_tokens < 1:
        raise ValueError("Context budgets must be positive and radius nonnegative")
    documents = read_documents(store)
    by_position = {}
    for document in documents:
        position = (document.metadata.get("source"), document.metadata.get("index"))
        by_position.setdefault(position, []).append(document)
    candidates = list(seeds)
    for seed in seeds:
        index = seed.metadata.get("index")
        source = seed.metadata.get("source")
        if not isinstance(index, int) or not source:
            continue
        centers = by_position.get((source, index), [])
        if len(centers) != 1 or centers[0].page_content != seed.page_content:
            continue
        for distance in range(1, radius + 1):
            for offset in (-distance, distance):
                neighbors = by_position.get((source, index + offset), [])
                if (len(neighbors) == 1
                        and neighbors[0].metadata.get("section") == seed.metadata.get("section")):
                    candidates.extend(neighbors)
    result = []
    seen = set()
    tokens = 0
    for document in candidates:
        key = document_key(document)
        if key in seen:
            continue
        length = len(tokenizer.encode(document.page_content, add_special_tokens=False))
        if tokens + length > max_tokens:
            continue
        result.append(document)
        seen.add(key)
        tokens += length
        if len(result) >= max_chunks:
            break
    return result
