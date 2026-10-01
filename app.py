"""
RAG Web 服务 —— 中英双库 + 缓存层 + 上传任务队列

**双库设计**：中英各一个 Chroma collection，各配一个 embedding 模型
（见 rag_langchain.py 的 LANG_MODELS）。按文档/问题的语种自动路由：
中文问题查中文库，英文问题查英文库，两者互不影响。

为什么必须分库？两个模型虽然都是 768 维，但向量分属**不同的空间**，
混进同一个 collection 会让相似度变成噪声，检索静默出错而不报错。

接口对照：
  POST /upload         默认**异步入队**（tasks.py）：存文件 + 入队 + 立刻返回
                       task_id；解析、切块、嵌入、入库由 worker 慢慢做。
                       传 ?sync=true 走旧的同步路径（评测脚本/一次性调试用）。
                       按文档语种【只替换该语种的库】：清空该库 -> 重新入库
                       -> 失效旧缓存（失效点在 worker 入库成功后）-> 刷新
                       chunks_preview_{lang}.md
  GET  /status/{id}    上传任务的状态轮询（queued/processing/succeeded/failed）
  POST /ask            按问题语种路由；额外返回 cache_hit / cache_type / elapsed_ms / lang
  GET  /cache/stats    查看缓存后端、命中率、缓存版本、各语种库块数
  POST /cache/clear    手动清空缓存（可选按类型清）
  GET  /health         轻量健康检查（含各语种库块数、任务队列状态）
  GET  /               前端页面

设计要点：
  1. 缓存是"加速层"不是"数据源"：清掉缓存系统只会变慢，答案不会变错；
  2. 上传文档会替换该语种的库并 bump 缓存版本（在 worker 入库成功后执行），
     避免"文档更新了、答案还是旧的"；也避免任务还在排队时旧答案被提前作废；
  3. 任何缓存异常都 fail-open（读不到就当未命中，照常走真实链路）；
  4. 目标语种的库为空时直接给出可读提示，**不**走检索——
     否则模型会"凭印象作答"，得到看起来正常但没有依据的回答。
"""
import os
import tempfile
import threading
import warnings
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

# 屏蔽 langchain-community sunset 的 DeprecationWarning（见 rag_langchain.py 顶部注释）
warnings.filterwarnings("ignore", message=".*langchain-community is being sunset.*")

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from langchain_core.output_parsers import StrOutputParser

import cache
import tasks
from rag_langchain import (
    prompt, llm, load_store, make_retriever, make_chain,
    query as rag_query,
    detect_lang, LANG_COLLECTIONS, DEFAULT_LANG,
    _get_chroma_client,
    RETRIEVE_K, RERANK_TOP_N,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时拉起内置任务 worker（QUEUE_WORKER_IN_APP=0 可关，见 tasks.py）。"""
    tasks.start_in_app_worker()
    yield


app = FastAPI(title="RAG Web Service (LangChain + Cache + Task Queue)",
              lifespan=lifespan)

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
    task_id: Optional[str] = None    # 异步模式：拿它轮询 GET /status/{task_id}
    status: str = ""                 # 异步模式返回的初始状态（queued）
    chunk_count: int = 0             # 只有 ?sync=true 的同步路径会填
    cache_invalidated: bool = False
    lang: str = ""                   # 文档被判定的语种，决定进哪个库


class CacheClearRequest(BaseModel):
    kinds: Optional[List[str]] = None    # 空 = 全部；可传 ["qa","embed","rerank"]


@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...), sync: bool = False):
    """上传 PDF 或 Markdown 文件。

    默认走任务队列（README 第八节）：存文件 + 入队 + **立刻**返回 task_id，
    解析、切块、嵌入、入库交给 worker 慢慢做——一本大 PDF 不再让用户
    在 HTTP 请求里干等几十秒，多人同时上传也只是排队而不是把 CPU 打满。

    ?sync=true 保留旧的同步路径（评测脚本/一次性调试用），
    处理逻辑与 worker 是同一个函数（tasks.process_upload_file），不会漂移。
    """
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".pdf", ".md", ".markdown", ".txt"):
        return UploadResponse(
            success=False,
            message=f"不支持的文件类型: {ext or '(无扩展名)'}，请上传 PDF 或 Markdown 文件")

    file_bytes = await file.read()
    if not file_bytes:
        return UploadResponse(success=False, message="文件内容为空")

    if sync:
        # 同步路径：请求内做完解析+入库（行为与缓存版一致）。
        # 文件类型/空文件已在上面快速失败；内容级问题（如 PDF 无文本）
        # 在 process_upload_file 里抛出，这里转成可读的失败响应。
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        try:
            result = tasks.process_upload_file(
                {"saved_path": tmp_path, "filename": filename})
            return UploadResponse(
                success=True, message=result["message"],
                chunk_count=result["chunk_count"],
                cache_invalidated=result["cache_invalidated"],
                lang=result["lang"],
            )
        except Exception as e:
            return UploadResponse(success=False, message=f"上传失败: {e}")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # 异步路径：暂存文件 + 入队 + 立刻返回。入队失败会抛出（队列是功能层，
    # 不能像缓存那样 fail-open 静默吞掉——文件收了却没人处理是最坏的体验）。
    try:
        task_id = tasks.submit_upload(filename, file_bytes, ext)
    except Exception as e:
        return UploadResponse(success=False, message=f"任务入队失败: {e}")
    return UploadResponse(
        success=True,
        message=(f"已接收 {filename}（{len(file_bytes) / 1024:.1f} KB），任务已加入队列"
                 f"（后端 {tasks.backend_name()}）。解析与向量化在后台进行，"
                 f"可用 task_id 查询进度。"),
        task_id=task_id,
        status=tasks.QUEUED,
    )


@app.get("/status/{task_id}")
def task_status(task_id: str):
    """上传任务的状态轮询（前端在 /upload 返回 task_id 后反复调用它）。

    状态机：queued -> processing -> succeeded | failed。
    404 = 任务不存在或状态已过期（TASK_TTL，默认 24 小时）。
    """
    task = tasks.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404,
                            detail=f"任务 {task_id} 不存在或已过期")
    return task


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
            "cache_healthy": cache.healthy(),
            "queue": {"backend": tasks.backend_name(),
                      "in_app_worker": tasks.IN_APP_WORKER},
            "collections": collection_counts()}


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    """返回前端页面。"""
    with open(FRONTEND, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
