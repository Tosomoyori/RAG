"""
RAG —— 上传任务队列（Redis Stream 优先，自动降级进程内队列）

解决的问题（README 第八节列的两个痛点）：
  1. 上传阻塞：/upload 原来在请求内同步完成解析、切块、嵌入、入库，
     一本大 PDF 用户要等几十秒；
  2. 削峰：多人同时上传时，重活全部堆积在 FastAPI 进程里把 CPU 占满。

改造后的链路（与 README 第八节画的图一致）：
  /upload -> 存文件 + 往队列扔一条消息 -> 立刻返回 task_id
  worker  -> 消费消息 -> 解析+切块+嵌入+入库 -> 更新任务状态
  前端    -> 拿 task_id 轮询 GET /status/{task_id}

后端选择（与 cache.py 同一套哲学：auto / redis / memory + 降级）：
  QUEUE_BACKEND=auto（默认）：跟随缓存层的探测结果——Redis 可用则用
    Redis Stream（跨进程共享、可跑独立 worker），否则用进程内队列；
  QUEUE_BACKEND=redis：强制 Redis Stream，连不上直接报错（生产用）；
  QUEUE_BACKEND=memory：只用进程内队列，由 web 进程内的后台线程消费。

为什么选 Redis Stream 而不是 RabbitMQ / List(BLPOP)：
  - 项目已经依赖 redis（缓存层在用），Stream 是 Redis 5+ 自带的日志型队列，
    不用引入新中间件；
  - BLPOP"取出即丢"，worker 崩溃 = 消息丢失；Stream 的消息进组后留在 PEL，
    直到 XACK 才算消费完——worker 挂了，重启后 XAUTOCLAIM 认领重做；
  - 消费组（XREADGROUP）天然支持多 worker 分摊，水平扩展不用改代码。

任务状态**跟着队列后端走**而不是跟着缓存后端走，这是刻意的：
  轮询要读到"另一个进程写的状态"（redis 队列 -> 状态存 Redis，
  worker.py 进程写、web 进程读）；如果状态跟着缓存层降级进了内存，
  而队列还在 Redis 上，轮询就会永远 404。

缓存层的配合点（README 第八节点名、也是最容易做错的一处）：
  缓存失效（invalidate_caches -> bump_version）从"收到文件"挪到
  "worker 入库成功"。任务还在排队时，旧答案其实仍然正确——提前失效
  只会让用户在这段时间白白重算，而新答案又还没就绪。
"""
import json
import os
import queue as _queue
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

import cache        # 复用 REDIS_URL 与 auto 模式下的"Redis 可用性"探测结果
from document_loader import load_sections, chunk_sections

# ---------- 配置（.env 可覆盖） ----------
QUEUE_BACKEND = os.getenv("QUEUE_BACKEND", "auto").lower()   # auto / redis / memory
TASK_TTL = int(os.getenv("TASK_TTL", 86400))                 # 任务状态保留 24 小时
# web 进程内是否启动消费线程。单机演示保持默认（开箱即用）；
# 部署独立 worker.py、想让重活彻底离开 web 进程时设 0。
IN_APP_WORKER = os.getenv("QUEUE_WORKER_IN_APP", "1") == "1"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "uploads")

STREAM_KEY = "rag:upload:stream"
GROUP_NAME = "workers"
TASK_KEY_PREFIX = "rag:task:"
# Stream 条目上限：消息 ACK 后仍留在 stream 里（消费组只记位点），
# 不修剪就会无限增长。1000 条积压意味着系统早已严重过载，
# 此时丢最老的任务是可接受的极端降级（任务状态会一直显示 queued）。
STREAM_MAXLEN = 1000

# 任务状态机：queued -> processing -> succeeded | failed
QUEUED = "queued"
PROCESSING = "processing"
SUCCEEDED = "succeeded"
FAILED = "failed"


# ---------- Redis 连接 ----------
def _connect_redis(socket_timeout: float):
    """建一个 Redis 连接（与 cache._connect_redis 同一套约定：RESP2 + 测试钩子）。

    消费侧必须单独建连接、超时给足：XREADGROUP BLOCK 5 秒内不会有回包，
    复用 cache 那种 1 秒超时的连接会先抛 socket 超时。
    """
    module_name = os.getenv("RESP_CLIENT_MODULE", "redis")
    module = __import__(module_name, fromlist=["from_url"])
    kwargs = dict(decode_responses=True, socket_connect_timeout=1, socket_timeout=socket_timeout)
    try:
        # 强制 RESP2（兼容 Redis 6 以下，理由见 cache._connect_redis 的注释）
        client = module.from_url(cache.REDIS_URL, protocol=2, **kwargs)
    except TypeError:
        # 极简 RESP 客户端（tools/resp_client.py）没有 protocol 参数
        client = module.from_url(cache.REDIS_URL, **kwargs)
    client.ping()
    return client


def _task_key(task_id: str) -> str:
    return f"{TASK_KEY_PREFIX}{task_id}"


# ---------- 进程内队列（Redis 不可用时的降级方案） ----------
class _MemoryTaskQueue:
    """queue.Queue + 进程内状态字典。只在单进程内有效：消费方必须是本进程的线程。

    与 _MemoryBackend 一样的局限：重启即失效、多实例不共享——
    但它保证"没有 Redis 时上传功能不受影响"，只是少了独立 worker 的能力。
    """

    name = "memory"

    def __init__(self) -> None:
        self._queue: "_queue.Queue[Dict[str, Any]]" = _queue.Queue()
        self._tasks: Dict[str, tuple] = {}        # task_id -> (task_dict, expire_at)
        self._lock = threading.Lock()             # 只保护 _tasks（Queue 自身线程安全）

    def enqueue(self, task: Dict[str, Any], message: Dict[str, Any]) -> None:
        with self._lock:
            self._tasks[task["task_id"]] = (dict(task), time.time() + TASK_TTL)
        self._queue.put(message)

    def ensure_ready(self) -> None:
        pass

    def next_message(self, consumer: str, block_seconds: float) -> Optional[Dict[str, Any]]:
        try:
            return self._queue.get(timeout=max(block_seconds, 0.01))
        except _queue.Empty:
            return None

    def ack(self, msg: Dict[str, Any]) -> None:
        # 取走即消费，没有"未确认"状态，也就没有崩溃恢复一说（进程死了队列也没了）
        pass

    def reclaim_stale(self, consumer: str, min_idle_ms: int) -> List[Dict[str, Any]]:
        return []

    def save_task(self, task: Dict[str, Any], ttl: int = TASK_TTL) -> None:
        with self._lock:
            self._tasks[task["task_id"]] = (dict(task), time.time() + ttl if ttl else 0)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self._tasks.get(task_id)
            if item is None:
                return None
            task, expire_at = item
            if expire_at and expire_at < time.time():    # 惰性过期
                self._tasks.pop(task_id, None)
                return None
            return dict(task)


# ---------- Redis Stream 队列 ----------
class _RedisStreamQueue:
    """基于 Redis Stream 的任务队列（跨进程共享 + 崩溃恢复）。

    两条连接分工：
      _client       写侧快命令（XADD / XACK / 状态 SET/GET），1~5 秒超时；
      _read_client  消费侧 XREADGROUP，BLOCK 期间没有回包，超时要 > BLOCK。
    """

    name = "redis"

    def __init__(self) -> None:
        self._client = _connect_redis(socket_timeout=5)
        self._read_client = _connect_redis(socket_timeout=15)
        self._group_ready = False

    def ensure_ready(self) -> None:
        """确保消费组存在（幂等）。已在 enqueue 侧调用——组必须在第一条消息
        入队**之前**创建：XGROUP CREATE 的位点默认是 `$`（队尾），
        先入队再建组会把组诞生前的消息永远漏掉。
        """
        if self._group_ready:
            return
        try:
            self._client.xgroup_create(STREAM_KEY, GROUP_NAME, id="$", mkstream=True)
        except Exception as e:
            if "BUSYGROUP" not in str(e).upper():    # 组已存在是正常情况
                raise
        self._group_ready = True

    def enqueue(self, task: Dict[str, Any], message: Dict[str, Any]) -> None:
        self.save_task(task)
        self.ensure_ready()
        fields = {"data": json.dumps(message, ensure_ascii=False)}
        self._client.xadd(STREAM_KEY, fields, maxlen=STREAM_MAXLEN, approximate=True)

    def next_message(self, consumer: str, block_seconds: float) -> Optional[Dict[str, Any]]:
        self.ensure_ready()
        resp = self._read_client.xreadgroup(
            GROUP_NAME, consumer, {STREAM_KEY: ">"}, count=1,
            block=int(block_seconds * 1000))
        # redis-py 返回 [[stream_name, [(entry_id, {field: value}), ...]], ...]，
        # 空回复（BLOCK 超时）返回 None 或 []
        if not resp:
            return None
        entries = resp[0][1]
        if not entries:
            return None
        entry_id, fields = entries[0]
        data = json.loads(fields.get("data") or "{}")
        return {"entry_id": entry_id, **data}

    def ack(self, msg: Dict[str, Any]) -> None:
        self._client.xack(STREAM_KEY, GROUP_NAME, msg["entry_id"])

    def reclaim_stale(self, consumer: str, min_idle_ms: int) -> List[Dict[str, Any]]:
        """认领"别的 consumer 取走后超时未确认"的消息（崩溃恢复）。

        只在 worker 启动时调用一次，平时不去抢别人的活：
        任务虽然幂等，两个 worker 同时做同一个任务纯属浪费。
        """
        self.ensure_ready()
        claimed: List[Dict[str, Any]] = []
        cursor = "0-0"
        while True:
            resp = self._client.xautoclaim(
                STREAM_KEY, GROUP_NAME, consumer, min_idle_ms, start_id=cursor, count=10)
            next_cursor, entries = resp[0], resp[1]
            for entry_id, fields in entries:
                data = json.loads(fields.get("data") or "{}")
                claimed.append({"entry_id": entry_id, **data})
            if str(next_cursor) in ("0", "0-0"):
                break
            cursor = next_cursor
        return claimed

    def save_task(self, task: Dict[str, Any], ttl: int = TASK_TTL) -> None:
        self._client.set(_task_key(task["task_id"]),
                         json.dumps(task, ensure_ascii=False), ex=ttl or None)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        raw = self._client.get(_task_key(task_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None


_queue_instance: Optional[Any] = None
_queue_lock = threading.Lock()


def _get_queue():
    """按配置选队列后端，只初始化一次（双检锁，与 cache._get_backend 一致）。"""
    global _queue_instance
    if _queue_instance is not None:
        return _queue_instance
    with _queue_lock:
        if _queue_instance is not None:
            return _queue_instance

        if QUEUE_BACKEND == "memory":
            _queue_instance = _MemoryTaskQueue()
            print("[queue] QUEUE_BACKEND=memory，使用进程内任务队列")
        elif QUEUE_BACKEND == "redis":
            # 强制模式：连不上直接抛，不静默降级（生产语义，与 CACHE_BACKEND=redis 一致）
            _queue_instance = _RedisStreamQueue()
            print(f"[queue] 已连接 Redis Stream：{STREAM_KEY}（消费组 {GROUP_NAME}）")
        else:
            # auto：跟随缓存层的探测结果。Redis 连不上时缓存已经降级了，
            # 队列再各自为政地去连只会得到同一个结论，还多一轮超时等待。
            if cache.backend_name() == "redis":
                try:
                    _queue_instance = _RedisStreamQueue()
                    print(f"[queue] Redis 可用，上传任务走 Redis Stream：{STREAM_KEY}"
                          f"（消费组 {GROUP_NAME}，可跑独立 worker.py）")
                except Exception as e:
                    _queue_instance = _MemoryTaskQueue()
                    print(f"[queue] Redis Stream 初始化失败（{e}），降级为进程内任务队列")
            else:
                _queue_instance = _MemoryTaskQueue()
                print("[queue] 缓存层未用 Redis，上传任务使用进程内队列（单进程内消费）")
        return _queue_instance


def backend_name() -> str:
    try:
        return _get_queue().name
    except Exception:
        return "unavailable"


# ---------- 入队与状态查询（web 进程这一侧） ----------
def submit_upload(filename: str, file_bytes: bytes, ext: str) -> str:
    """暂存上传文件并入队，返回 task_id（调用方拿它轮询 /status/{task_id}）。

    队列是功能层不是加速层，这里**不能**学缓存 fail-open 静默吞错：
    入队失败必须抛给调用方（/upload 返回失败，用户重传），否则文件收了
    却没人处理，用户只会看到一个永远 queued 的任务。
    """
    task_id = uuid.uuid4().hex[:16]
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    saved_path = os.path.join(UPLOAD_DIR, f"{task_id}{ext}")
    with open(saved_path, "wb") as f:
        f.write(file_bytes)
    try:
        _get_queue().enqueue(
            {"task_id": task_id, "status": QUEUED, "filename": filename,
             "enqueued_at": time.time()},
            {"task_id": task_id, "filename": filename, "saved_path": saved_path},
        )
    except Exception:
        try:
            os.remove(saved_path)     # 入队失败不留孤儿文件
        except OSError:
            pass
        raise
    return task_id


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """按 task_id 查任务状态；不存在 / 已过期返回 None（/status 据此回 404）。"""
    try:
        return _get_queue().get_task(task_id)
    except Exception:
        return None    # fail-open：状态层故障不该拖垮轮询接口


# ---------- 任务处理（worker 侧的默认 handler） ----------
def process_upload_file(msg: Dict[str, Any]) -> Dict[str, Any]:
    """解析 -> 切块 -> 嵌入 -> 入库 -> 失效缓存 -> 刷新 preview。

    逻辑从 app.py 的同步 /upload 平移而来（同一份代码，同步 / 异步两条
    路径共用，避免两份逻辑各自漂移）。两处刻意的差异：
      1. invalidate_caches() 在**入库成功之后**调用——异步化后失效点必须
         挪到这里（见模块 docstring）；同步路径同样受益（语义更准确）；
      2. preview 写绝对路径：worker 进程的 CWD 不一定是项目根目录，
         沿用原来的 `./chunks_preview_{lang}.md` 会把文件写去别处。

    延迟 import rag_langchain：模块导入会连带加载 langchain 全家，
    verify_queue.py 注入假 handler 验证队列流转时不该付这个代价。

    幂等（清空重入，向量缓存兜底重复计算）——这是崩溃恢复敢直接重做的前提。
    """
    from rag_langchain import (
        detect_lang, split_by_tokens, load_store, get_all_chunks_in_order,
        save_chunks_to_file, invalidate_caches, LANG_COLLECTIONS,
    )

    saved_path = msg["saved_path"]
    filename = msg.get("filename") or os.path.basename(saved_path)
    sections = load_sections(saved_path)
    text = "\n\n".join(section.text for section in sections)

    if not text.strip():
        raise ValueError("文件内容为空")

    # 按**文档语种**决定进哪个库、用哪个模型（中英各一个 collection）
    lang = detect_lang(text)
    chunks, metadata = chunk_sections(sections, lang, split_by_tokens, filename)
    if not chunks:
        raise ValueError("分块后无内容")

    # 只替换**该语种**的 collection：先清空，再以 index 0 起重新编号入库。
    # 只删块、不 drop collection（维度不变），保持 Chroma 实例和 retriever 有效。
    store = _get_worker_store(lang)
    old_ids = store.get()["ids"]
    if old_ids:
        store.delete(ids=old_ids)
    store.add_texts(
        chunks,
        metadatas=metadata,
    )

    # 知识库变了，旧答案必须作废——注意这一步在入库成功之后（模块 docstring 说明了为什么）
    invalidated = invalidate_caches()

    # 让该语种的 chunks_preview 跟上向量库（评测脚本以它为 chunk 正文基准）。
    # 失败不影响任务本身（与缓存层一样 fail-open）。
    preview_directory = os.path.abspath(os.getenv("RAG_ARTIFACT_DIR", PROJECT_ROOT))
    preview_file = os.path.join(preview_directory, f"chunks_preview_{lang}.md")
    preview_note = ""
    try:
        os.makedirs(preview_directory, exist_ok=True)
        save_chunks_to_file(get_all_chunks_in_order(store), preview_file)
    except Exception as e:
        preview_note = f"；chunks_preview_{lang}.md 更新失败: {e}"

    label = "中文" if lang == "zh" else "英文"
    message = (f"成功解析文件 {filename}，判定为{label}，"
               f"共 {len(chunks)} 个文本块进入 {LANG_COLLECTIONS[lang]} 库"
               f"（已替换该库原有 {len(old_ids)} 个块，index 0~{len(chunks) - 1}，"
               f"已失效 {invalidated} 条问答/精排缓存）{preview_note}")
    return {"lang": lang, "chunk_count": len(chunks), "old_count": len(old_ids),
            "cache_invalidated": True, "message": message}


_worker_stores: Dict[str, Any] = {}
_worker_store_lock = threading.Lock()


def _get_worker_store(lang: str):
    """worker 进程内按语种缓存 Chroma 句柄。

    embedding 模型有 rag_langchain 的全局单例兜底，但每个任务都 new 一个
    Chroma 包装纯属浪费；同一 collection 的多个 Chroma 实例共享底层
    client（SharedSystemClient 按目录注册），缓存句柄没有额外代价。
    """
    if lang not in _worker_stores:
        with _worker_store_lock:
            if lang not in _worker_stores:
                from rag_langchain import load_store
                _worker_stores[lang] = load_store(lang)
    return _worker_stores[lang]


# ---------- 消费循环 ----------
def _cleanup_upload_file(msg: Dict[str, Any]) -> None:
    """处理完删掉暂存文件（成功失败都删，错误信息已写进任务状态）。"""
    path = msg.get("saved_path")
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _safe_save(backend, task: Dict[str, Any]) -> None:
    """任务状态写入失败只打日志不抛：任务本身可能已经处理完/失败，
    状态层故障不该反过来把 worker 循环打断（Redis 挂了会有退避重启兜底）。"""
    try:
        backend.save_task(task)
    except Exception as e:
        print(f"[queue] 任务状态写入失败（{e}），任务仍在后台处理")


def _handle_message(backend, msg: Dict[str, Any],
                    handler: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
    """处理一条消息：标 processing -> 跑 handler -> 标 succeeded/failed。

    handler 抛异常不会中断消费（毒丸隔离）：错误写进任务状态让用户看到，
    然后照常 ACK。不做自动重试——失败原因多半是文件本身的问题，
    重试一百次也一样，让用户改完重新上传才是正解。
    """
    task_id = msg.get("task_id", "")
    # 状态可能已过期（积压超过 TASK_TTL 才被消费）：兜底一个最小状态，
    # 保证轮询方至少能看到 processing -> 终态的结果。
    task = backend.get_task(task_id) or {
        "task_id": task_id, "status": QUEUED,
        "filename": msg.get("filename", ""),
    }
    started = time.time()
    task.update(status=PROCESSING, started_at=started)
    _safe_save(backend, task)
    try:
        result = handler(msg) or {}
        task.update(result)
        task.update(status=SUCCEEDED)
    except Exception as e:
        task.update(status=FAILED, error=f"{type(e).__name__}: {e}")
        print(f"[queue] 任务 {task_id} 处理失败：{type(e).__name__}: {e}")
    finished = time.time()
    task.update(finished_at=finished, elapsed_ms=round((finished - started) * 1000, 1))
    _safe_save(backend, task)
    _cleanup_upload_file(msg)
    return task


def run_worker(consumer_name: Optional[str] = None,
               handler: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
               once: bool = False,
               block_seconds: float = 5.0,
               reclaim_min_idle_ms: int = 60_000) -> Optional[Dict[str, Any]]:
    """消费上传任务。once=True 只处理一条（无消息时返回 None）。

    handler 可注入：verify_queue.py 用假 handler 验证队列流转，
    避免为了测队列而加载 1GB 模型；默认是 process_upload_file。
    """
    backend = _get_queue()
    consumer = consumer_name or f"worker-{os.getpid()}"
    do = handler or process_upload_file

    # 崩溃恢复：认领上次 worker 死掉时"取走了但没确认"的消息。
    # 敢直接重做是因为 process_upload_file 幂等（清库重入）。
    for msg in backend.reclaim_stale(consumer, reclaim_min_idle_ms):
        try:
            _handle_message(backend, msg, do)
        finally:
            backend.ack(msg)

    while True:
        msg = backend.next_message(consumer, block_seconds)
        if msg is None:
            if once:
                return None
            continue
        try:
            task = _handle_message(backend, msg, do)
        finally:
            backend.ack(msg)    # 失败也确认：不留毒丸在 PEL 里反复重试
        if once:
            return task


# ---------- web 进程内的内置 worker ----------
_in_app_thread: Optional[threading.Thread] = None


def start_in_app_worker() -> bool:
    """在当前进程里拉起一个后台消费线程（app.py 的 lifespan 里调用）。

    - memory 后端：这是唯一消费者（进程外没人看得到进程内队列）；
    - redis 后端：默认也起一个，"单机零配置"开箱即用；部署独立 worker.py
      时设 QUEUE_WORKER_IN_APP=0 关掉（留着也无害——消费组自动分流，
      只是 web 进程分不到重活的前提就不成立了）。
    """
    global _in_app_thread
    if not IN_APP_WORKER:
        print("[queue] QUEUE_WORKER_IN_APP=0：web 进程不消费任务，"
              "请确保 worker.py 正在运行，否则上传任务只会排队")
        return False
    if _in_app_thread is not None and _in_app_thread.is_alive():
        return True
    try:
        name = _get_queue().name
    except Exception as e:
        print(f"[queue] 任务队列初始化失败，内置 worker 未启动：{e}")
        return False
    _in_app_thread = threading.Thread(
        target=_in_app_worker_main, name="upload-task-worker", daemon=True)
    _in_app_thread.start()
    print(f"[queue] 内置 worker 线程已启动（后端 {name}）")
    return True


def _in_app_worker_main() -> None:
    """内置消费线程的主循环：出错不死、退避重启（Redis 瞬断自愈）。"""
    while True:
        try:
            run_worker(consumer_name=f"in-app-{os.getpid()}")
        except Exception as e:
            print(f"[queue] 内置 worker 异常（{type(e).__name__}: {e}），5 秒后重启")
            time.sleep(5)
