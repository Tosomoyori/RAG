"""
RAG Web 服务 —— 中英双库 + 缓存层

**双库设计**：中英各一个 Chroma collection，各配一个 embedding 模型
（见 rag_langchain.py 的 LANG_MODELS）。按文档/问题的语种自动路由：
中文问题查中文库，英文问题查英文库，两者互不影响。

为什么必须分库？两个模型虽然都是 768 维，但向量分属**不同的空间**，
混进同一个 collection 会让相似度变成噪声，检索静默出错而不报错。

接口对照：
  POST /upload         按文档语种【只替换该语种的库】：清空该库 -> 重新入库(index 0 起)
                       -> 失效旧缓存 -> 刷新 chunks_preview_{lang}.md
  POST /ask            按问题语种路由；额外返回 cache_hit / cache_type / elapsed_ms / lang
  GET  /cache/stats    查看缓存后端、命中率、缓存版本、各语种库块数
  POST /cache/clear    手动清空缓存（可选按类型清）
  GET  /health         轻量健康检查（含各语种库块数）
  GET  /               前端页面

设计要点：
  1. 缓存是"加速层"不是"数据源"：清掉缓存系统只会变慢，答案不会变错；
  2. 上传文档会替换该语种的库并 bump 缓存版本，避免"文档更新了、答案还是旧的"；
  3. 任何缓存异常都 fail-open（读不到就当未命中，照常走真实链路）；
  4. 目标语种的库为空时直接给出可读提示，**不**走检索——
     否则模型会"凭印象作答"，得到看起来正常但没有依据的回答。
"""
import os
import tempfile
import threading
import warnings
from typing import Any, Dict, List, Optional

# 屏蔽 langchain-community sunset 的 DeprecationWarning（见 rag_langchain.py 顶部注释）
warnings.filterwarnings("ignore", message=".*langchain-community is being sunset.*")

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from langchain_core.output_parsers import StrOutputParser
from langchain_community.document_loaders import PyMuPDFLoader

import cache
from rag_langchain import (
    prompt, llm, load_store, make_retriever, make_chain,
    split_by_tokens, query as rag_query, invalidate_caches,
    get_all_chunks_in_order, save_chunks_to_file,
    detect_lang, LANG_COLLECTIONS, LANG_MODELS, DEFAULT_LANG,
    _get_chroma_client,
    RETRIEVE_K, RERANK_TOP_N,
)

app = FastAPI(title="RAG Web Service (LangChain + Cache)")

# 全局对象，启动时懒加载（避免重复加载本地模型）
# 注意：这是"模型/连接复用"，不是缓存——缓存见 cache.py 与 rag_langchain.query()
#
# 按语种各一份：中英两个 collection 用的是两个**不同的 embedding 模型**，
# 向量分属不同空间，绝不能混用（见 rag_langchain.py 里 LANG_MODELS 上方的约束说明）。
_stores: Dict[str, Any] = {}
_retrievers: Dict[str, Any] = {}
_chains: Dict[str, Any] = {}
# FastAPI 会把同步的 /ask 丢进线程池，首次并发请求会各自构造一遍，
# 所以这些懒加载单例都走双检锁（与 cache._get_backend 的写法一致）。
_singleton_lock = threading.Lock()

FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "index.html")


def get_store(lang: str = DEFAULT_LANG):
    if lang not in _stores:
        with _singleton_lock:
            if lang not in _stores:
                _stores[lang] = load_store(lang)
    return _stores[lang]


def get_retriever(lang: str = DEFAULT_LANG):
    if lang not in _retrievers:
        with _singleton_lock:
            if lang not in _retrievers:
                _retrievers[lang] = make_retriever(get_store(lang))   # 召回 RETRIEVE_K + 精排 RERANK_TOP_N
    return _retrievers[lang]


def get_chain(lang: str = DEFAULT_LANG):
    """LCEL 链（检索 -> prompt -> DeepSeek -> 文本）。每个语种只构造一次。"""
    if lang not in _chains:
        with _singleton_lock:
            if lang not in _chains:
                _chains[lang] = make_chain(get_retriever(lang))
    return _chains[lang]


def _collection_size(lang: str) -> int:
    """该语种库的块数；库还没建过时返回 0。

    **绝不能**用 get_store() 来数数：那会构造 embedding_function，而
    HuggingFaceEmbeddings 在 __init__ 里就把整个模型载进内存——一个只想
    "看一眼状态"的 GET 请求不该付 400MB×2 的代价（两个语种就是两个模型），
    也不该顺手把没建过的 collection 建出来。

    这里直接问 Chroma 要 count：走的是 collection 的 SQL 计数，
    既不需要 embedding_function，也不需要把文档全取回来。
    """
    loaded = _stores.get(lang)
    if loaded is not None:                 # 已经加载过就复用，顺带避开下面的开销
        try:
            return loaded._collection.count()
        except Exception:
            return 0
    try:
        col = _get_chroma_client().get_collection(
            LANG_COLLECTIONS[lang], embedding_function=None)
        return col.count()
    except Exception:
        return 0                            # 库不存在 = 0 块


def collection_counts() -> Dict[str, int]:
    """各语种 collection 当前的块数（用于 /health 与 /cache/stats）。"""
    return {lang: _collection_size(lang) for lang in LANG_COLLECTIONS}


def _lang_label(lang: str) -> str:
    return "中文" if lang == "zh" else "英文"


class AskRequest(BaseModel):
    query: str
    use_cache: bool = True       # 可传 false 强制走真实链路（便于对比耗时）


class AskResponse(BaseModel):
    answer: str
    sources: List[str]
    cache_hit: bool = False
    cache_type: str = "miss"
    elapsed_ms: float = 0.0
    lang: str = ""               # 问题被判定的语种，决定查哪个库


class UploadResponse(BaseModel):
    success: bool
    message: str
    chunk_count: int = 0
    cache_invalidated: bool = False
    lang: str = ""               # 文档被判定的语种，决定进哪个库


class CacheClearRequest(BaseModel):
    kinds: Optional[List[str]] = None    # 空 = 全部；可传 ["qa","embed","rerank"]


@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """上传 PDF 或 Markdown 文件，解析后加入向量库，并失效受影响的缓存。"""
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()

    file_bytes = await file.read()

    try:
        if ext == ".pdf":
            # 先写入临时文件再交给 PyMuPDFLoader
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            try:
                text = "".join(p.page_content for p in PyMuPDFLoader(tmp_path).load())
            finally:
                os.unlink(tmp_path)
        elif ext in (".md", ".markdown", ".txt"):
            text = file_bytes.decode("utf-8")
        else:
            return UploadResponse(success=False, message=f"不支持的文件类型: {ext}，请上传 PDF 或 Markdown 文件")

        if not text.strip():
            return UploadResponse(success=False, message="文件内容为空")

        # 按**文档语种**决定进哪个库、用哪个模型（中英各一个 collection）
        lang = detect_lang(text)

        # 切块要用该语种的 tokenizer，所以必须排在 lang 之后
        chunks = split_by_tokens(text, lang)
        if not chunks:
            return UploadResponse(success=False, message="分块后无内容")

        # 只替换**该语种**的 collection：先清空，再以 index 0 起重新编号入库。
        # 中文库和英文库互相独立——上传英文文档不会动到中文库，反之亦然。
        # 注意：这里只删块、不 drop collection（维度不变），保持 Chroma 实例和 retriever 有效。
        store = get_store(lang)
        old_ids = store.get()["ids"]
        if old_ids:
            store.delete(ids=old_ids)

        # 向量化 + 入库；嵌入会走向量缓存（重复上传同一文件不会重复算向量）
        store.add_texts(
            chunks,
            metadatas=[{"index": i, "source": filename}
                       for i in range(len(chunks))],
        )

        # 知识库变了：旧答案必须作废，否则用户会拿到基于旧文档的回答
        invalidated = invalidate_caches()

        # 让该语种的 chunks_preview 跟上向量库：评测脚本以它为 chunk 正文基准，
        # 不更新的话它们会拿旧正文去比对新向量库，结论会静默出错。
        # 失败不影响上传本身（与缓存层一样 fail-open）。
        preview_file = f"./chunks_preview_{lang}.md"
        preview_note = ""
        try:
            save_chunks_to_file(get_all_chunks_in_order(store), preview_file)
        except Exception as e:
            preview_note = f"；{preview_file} 更新失败: {e}"

        return UploadResponse(
            success=True,
            message=(f"成功解析文件 {filename}，判定为{_lang_label(lang)}，"
                     f"共 {len(chunks)} 个文本块进入 {LANG_COLLECTIONS[lang]} 库"
                     f"（已替换该库原有 {len(old_ids)} 个块，index 0~{len(chunks) - 1}，"
                     f"已失效 {invalidated} 条问答/精排缓存）{preview_note}"),
            chunk_count=len(chunks),
            cache_invalidated=True,
            lang=lang,
        )
    except Exception as e:
        return UploadResponse(success=False, message=f"上传失败: {str(e)}")


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(request: AskRequest):
    """接收问题，按**问题语种**路由到对应库，先查缓存再走"检索 -> 精排 -> 生成"。"""
    q = request.query.strip()
    if not q:
        return AskResponse(answer="问题不能为空", sources=[], cache_type="empty")

    # 按问题语种选库与模型：中文问题只查中文库，英文问题只查英文库
    lang = detect_lang(q)

    # 空库保护：目标语种的库还没建/没内容时，直接说清楚。
    # 不能放进检索——那样会召回到别的东西（或空），再让模型"凭印象作答"，
    # 得到一个看起来正常、其实没有依据的回答。
    if _collection_size(lang) == 0:
        return AskResponse(
            answer=(f"{_lang_label(lang)}知识库为空。请先在页面上传一份"
                    f"{_lang_label(lang)}文档，再提问。"),
            sources=[], cache_type="empty_collection", lang=lang,
        )

    result = rag_query(
        q,
        retriever=get_retriever(lang),
        chain=get_chain(lang),
        use_cache=request.use_cache,
        k=RETRIEVE_K,
        top_n=RERANK_TOP_N,
        lang=lang,
    )
    return AskResponse(**result, lang=lang)


@app.get("/cache/stats")
def cache_stats():
    """查看缓存运行状态：后端类型、命中率、当前版本号、各语种库的块数。"""
    return {
        "backend": cache.backend_name(),
        "healthy": cache.healthy(),
        "version": cache.get_version(),
        "collections": collection_counts(),
        "ttl_seconds": {
            "answer": cache.ANSWER_TTL,
            "embedding": cache.EMBEDDING_TTL,
            "rerank": cache.RERANK_TTL,
        },
        "stats": cache.get_stats(),
    }


@app.post("/cache/clear")
def cache_clear(request: CacheClearRequest):
    """手动清空缓存。kinds 为空清全部；传 ['qa'] 可只清问答缓存。"""
    deleted = cache.clear(request.kinds)
    return {"success": True, "deleted": deleted, "kinds": request.kinds or ["qa", "embed", "rerank"]}


@app.get("/health")
def health():
    return {"status": "ok", "cache_backend": cache.backend_name(),
            "cache_healthy": cache.healthy(), "collections": collection_counts()}


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    """返回前端页面。"""
    with open(FRONTEND, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
