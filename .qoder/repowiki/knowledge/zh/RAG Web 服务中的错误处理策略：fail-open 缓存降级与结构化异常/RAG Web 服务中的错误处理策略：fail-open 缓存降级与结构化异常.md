---
kind: error_handling
name: RAG Web 服务中的错误处理策略：fail-open 缓存降级与结构化异常
category: error_handling
scope:
    - '**'
source_files:
    - app.py
    - cache.py
    - rag_langchain.py
    - tools/resp_client.py
    - tools/mini_redis_resp.py
---

## 1. 总体方法

本项目没有统一的自定义异常类体系（如 `errors/` 包），而是采用**分层容错 + fail-open 降级**的策略：

- **FastAPI 层**（`app.py`）：所有业务 handler 用 `try/except Exception` 包裹，捕获后返回结构化的 Pydantic response（`UploadResponse.success=False`、`message=...`），而不是让 FastAPI 抛出 500。
- **缓存层**（`cache.py`）：核心设计原则是「缓存只是加速层，任何一次缓存异常都直接回落到真实计算」——`get()` / `set()` / `clear()` / `bump_version()` / `backend_name()` / `healthy()` 全部用 `try/except Exception` 吞掉底层 Redis/内存后端异常，保证缓存故障不会污染主流程。
- **LangChain 管道层**（`rag_langchain.py`）：对可能静默出错的外部依赖（Chroma、sentence-transformers、文件 IO）使用显式 `raise FileNotFoundError` / `ValueError` 或 `try/except Exception: pass`，把「静默失败」转为「可读提示」。

项目文档中明确声明了约束：
- `app.py` 顶部注释：「任何缓存异常都 fail-open（读不到就当未命中，照常走真实链路）」。
- `cache.py` 模块 docstring：「缓存丢了系统只会'变慢'，不会'变错' —— 所以缓存只是加速层，任何一次缓存异常都直接回落到真实计算（fail-open）」。

## 2. 关键文件与职责

| 文件 | 错误处理职责 |
|---|---|
| `app.py` | HTTP 层 try/except；空库保护（`_collection_size(lang)==0` 时直接返回 `cache_type="empty_collection"`）；上传失败统一返回 `UploadResponse(success=False, message=...)` |
| `cache.py` | Redis/内存双后端抽象；自动降级（`CACHE_BACKEND=auto` 下 Redis 连不上则退化为 `_MemoryBackend`）；TTL 过期；版本号整体失效 |
| `rag_langchain.py` | 显式 `raise FileNotFoundError`（找不到文档）、`raise ValueError`（评测标注越界）；Chroma collection 维度变更需重启进程（代码注释说明） |
| `tools/resp_client.py` | 测试用 RESP 客户端，抛 `ConnectionError` / `RuntimeError` / `ValueError` 等标准异常 |
| `tools/mini_redis_resp.py` | 极简 Redis 模拟，捕获 `OSError` / `KeyboardInterrupt` |

## 3. 架构与约定

### 3.1 缓存后端自动降级
`_get_backend()` 在 `CACHE_BACKEND=auto` 模式下尝试连接 Redis，失败后打印日志并切换为 `_MemoryBackend`。当 `CACHE_BACKEND=redis` 时，连接失败会 `raise RuntimeError`（生产环境禁止静默降级）。降级后的行为差异通过 `backend_name()` 暴露给 `/health` 和 `/cache/stats`。

### 3.2 版本号整体失效
`VERSION_KEY = "rag:cache_version"` 配合 `bump_version()` 的原子 `incr` 操作实现「一次知识库变更即令所有旧答案失效」。key 格式统一为 `rag:v{版本}:{类型}:{内容hash}`，清理时使用通配前缀 `rag:v*:qa:` 删除所有历史版本，避免垃圾 key 残留。

### 3.3 并发安全
所有全局单例（embedding 模型、Chroma client、tokenizer、缓存后端、统计计数器）均使用 `threading.Lock` 或 `RLock` 的双检锁模式初始化，以适配 FastAPI 同步 handler 在线程池中并发调用的场景。

### 3.4 可观测性
`cache.get_stats()` 返回每层的 hit/miss/hit_rate 以及当前 backend 名称，供 `/cache/stats` 暴露。`AskResponse.cache_type` 字段区分 `exact` / `semantic(...)` / `miss` / `empty` / `empty_collection`，便于前端展示命中来源。

## 4. 约定与约束

- **约定（描述性）**：
  - 所有对外暴露的 API 不抛异常，而是返回带 `success` / `message` 的结构化响应。
  - 缓存读取失败一律视为未命中（`get()` 返回 `None`），写入失败被忽略（`set()` 静默 pass）。
  - 目标语种 collection 为空时直接返回提示，不走检索链路，避免 LLM「凭印象作答」。
  - Chroma collection 维度变更后必须停服手动删 `chroma_db/` 再重建，不能仅靠 `delete_collection()`（会作废共享 client 的所有句柄）。
  - 不同 embedding 模型的向量分属不同空间，绝不能混入同一 collection 或共用同一缓存 key，否则检索会「静默出错而不报错」。

- **规则（有强制力）**：
  - `CACHE_BACKEND=redis` 时 Redis 不可用会 `raise RuntimeError`（见 `cache.py:_get_backend` 第 194–195 行），这是唯一会向上冒泡的运行时错误。
  - 文件路径不存在时 `load_raw_text()` 显式 `raise FileNotFoundError`（见 `rag_langchain.py:299`），调用方应据此给出用户可读提示。
  - 评测脚本中 `true_indices` 越界时 `evaluate_retrieval()` 显式 `raise ValueError`（见 `rag_langchain.py:660`），阻止基于错误标注得出无意义指标。
  - Chroma collection 名长度必须在 3~512 字符且首尾为字母数字（见 `rag_langchain.py:78-80` 注释），否则会抛 `InvalidArgumentError`。
  - 语义缓存默认关闭（`SEMANTIC_CACHE_ENABLED = os.getenv("SEMANTIC_CACHE", "0") == "1"`），因为近似匹配存在误判风险，RAG 场景下「答错」比「慢一点」严重得多。