# RAG —— 带 Redis 缓存与上传任务队列的 PDF 问答

在**无缓存版本**的基础上，先后叠加了两层能力，RAG 管道（加载 → 切块 → 嵌入 → 入库 → 召回 → 精排 → 生成）逐行未变，接口与前端保持向后兼容：

- **缓存层**（cache.py）：解决"同一个问题、同一段文本，不要重复算第二遍"；
- **任务队列**（tasks.py，见[第八节](#八消息队列上传异步化与削峰)）：解决"/upload 同步阻塞几十秒"与"多人同时上传把 CPU 打满"。

> 本项目对应迭代计划里的两个主题：**缓存（已完成）** 与 **消息队列（已完成）**。

---

## 一、为什么 RAG 特别需要缓存

RAG 的一次问答要串行做四件重活：

| 环节 | 成本 | 是否可复用 |
|---|---|---|
| 问题向量化 | 模型前向一次，几十毫秒 | ✅ 同一个问题完全可复用 |
| 向量召回 | Chroma 查一次 | ✅ 结果确定性，可复用 |
| Cross-Encoder 精排 | **召回 20 条就要前向 20 次**，本地 CPU 上百毫秒级 | ✅ (问题, 片段) 组合可复用 |
| DeepSeek 生成 | **5~15 秒**，且**按 token 计费** | ✅ 同一问题答案可复用 |

前三个环节是"算力"，最后一个是"钱 + 时间"。而真实使用中，用户重复提问、多人问同一个问题、
刷新页面重问，都是非常常见的——这些请求**全部在重算一模一样的东西**。

无缓存版里的"模型懒加载 + 全局单例"解决的是"模型不要重复加载"，
但**每次请求的文本依然要完整走一遍前向计算**。这正是"模型单例 ≠ 缓存"的地方：

| | 模型单例（已有） | 缓存（新增） |
|---|---|---|
| 解决什么 | 同一进程内不重复**加载模型** | 同一输入不重复**计算结果** |
| 丢掉会怎样 | 变慢（重新加载 1GB 模型） | 变慢（重算一遍），**不会变错** |
| 跨进程/多实例 | 每个进程各一份 | Redis 下全局共享 |

---

## 二、三层缓存设计

```
用户提问
   │
   ├─① 问答缓存（问题原文 + 检索参数 + 缓存版本  →  答案 + 引用片段）
   │      命中 ──► 直接返回（不查库、不精排、不调 DeepSeek）
   │      未命中
   ▼
   ② 向量缓存（文本 hash → 向量）──► 只把未命中的文本送进 embedding 模型
   ▼
   ③ 精排分数缓存（(问题,片段) hash → 分数）──► 只对未算过的组合跑 cross-encoder
   ▼
   DeepSeek 生成  ──►  回写 ①
```

三层各自独立生效，任意一层命中都能省掉对应环节，测试与观察也互相不干扰。

### ① 问答缓存 —— 省时间、省钱

- **Key**：`rag:v{版本}:qa:{sha256(问题.strip() + k + top_n)}`
- **Value**：`{answer, sources, ts, question}`
- **TTL**：默认 1 小时（`CACHE_ANSWER_TTL`）
- 问题会先 `strip()`，避免"末尾多个空格就当成新问题"；
- **检索参数进 key**：改了 `k` 或 `top_n` 不会命中旧口径的答案——否则调参后拿到旧结果，会误以为参数没生效。

### ② 向量缓存 —— 省算力

包装 `HuggingFaceEmbeddings` 的 `embed_documents` / `embed_query`，**只把未命中的文本送进模型**：

```python
cached = cache.get_embeddings(texts, model_tag)            # 命中的直接拿
miss_texts = [t for t in texts if key(t) not in cached]    # 未命中的才算
```

- **Key**：`rag:embed:{model_tag}:{sha256(文本)}`（**含模型标签，不含缓存版本号**）
- **TTL**：默认 24 小时（`CACHE_EMBEDDING_TTL`）
- **为什么不含版本号**：向量只取决于"文本 + 模型"，与知识库内容无关。上传新文档时清掉向量缓存
  纯属浪费——同一段文本下次还要重算。**只有换 embedding 模型时才需要清**。
- **为什么必须含模型标签**：向量是模型算出来的，两个模型即使维度相同，向量也分属
  不同的空间。只按文本 hash 存会让两个模型**互相覆盖对方的向量**，而且同为 768 维时
  不会报错，只是检索静默变烂。本项目按语种分了两个模型，所以 `model_tag` 取语种
  （`"zh"` / `"en"`）。旧调用方不传该参数时退回 `rag:embed:{sha256(文本)}`，保持兼容。

### ③ 精排分数缓存 —— 省最慢的一环

cross-encoder 要把 `(问题, 片段)` 成对送进模型，召回 20 条就是 20 次前向。缓存键是二者内容哈希，
所以"同一问题换文档"、"同一文档换问题"都能部分复用。

- **Key**：`rag:rerank:{sha256(问题 + "||" + 片段)}`
- **TTL**：默认 1 小时（`CACHE_RERANK_TTL`）

---

## 三、最容易写错的两件事，以及本项目的解法

### 1. 失效：文档更新了，答案还是旧的

上传新文档后，向量库变了，但缓存里还躺着**基于旧文档生成的答案**——
用户会拿到一个"看起来很正常但是错的"回答。这是缓存系统里最典型的事故。

本项目的解法是**版本号**（`cache.py` 的 `bump_version()`）：

- 所有问答/精排 key 都带 `v{版本}`；上传成功后版本号 +1；
- 旧 key 瞬间"再也拼不出来"，等于全部失效——**比逐个删 key 更可靠**，不存在漏删；
- `clear()` 用通配前缀 `rag:v*:qa:` 清理**所有历史版本**，避免旧 key 变成删不掉的垃圾。

对照 `verify_cache.py` 第 5 节，这部分有 5 条专门用例覆盖。

### 2. 边界：缓存只能让系统"变慢"，不能让它"变错"

这是判断一个缓存写得对不对的标准。落实到代码里：

- 任何缓存读写异常都 **fail-open**：读不到就当未命中，照常走真实链路，绝不因为缓存挂了而报错；
- 答案缓存**不是唯一数据源**：清空缓存后重新提问，答案应该完全一致；
- **语义缓存默认关闭**。它能让"换个说法问同一问题"也命中，但近似匹配天然会误命中，
  阈值调低（如 0.85）时很容易答非所问。在 RAG 场景下，"答错"比"慢几秒"严重得多，
  所以默认不开，要开请显式设置：

  ```bash
  SEMANTIC_CACHE=1
  SEMANTIC_THRESHOLD=0.95    # 阈值越接近 1 越保守
  ```

---

## 四、降级策略：没有 Redis 也能跑

缓存是加速层，**不该成为单点依赖**。`cache.py` 按配置选后端：

| `CACHE_BACKEND` | 行为 | 适用 |
|---|---|---|
| `auto`（默认） | 能连 Redis 就用 Redis，连不上自动用进程内内存 | 开发/演示 |
| `redis` | 强制 Redis，连不上**直接报错** | 生产（避免静默降级后多实例缓存不共享） |
| `memory` | 只用进程内内存，零外部依赖 | 单机/离线调试 |

> ⚠️ 内存后端的局限要说清楚：**只在单进程内有效，重启即失效，多实例之间不共享**。
> 它保证"没有 Redis 时功能不受影响"，但拿不到 Redis 那种跨进程/跨实例的收益。

---

## 五、接口变化（相对无缓存版）

| 接口 | 变化 |
|---|---|
| `POST /upload` | **默认异步入队**（第八节）：存文件 + 入队 + 立刻返回 `task_id`；响应新增 `task_id` / `status`。传 `?sync=true` 保留旧的同步行为 |
| `GET /status/{task_id}` | **新增**：上传任务状态轮询（`queued → processing → succeeded / failed`） |
| `POST /ask` | 响应新增 `cache_hit` / `cache_type` / `elapsed_ms`；请求可传 `use_cache: false` 强制重算 |
| `GET /cache/stats` | **新增**：后端类型、命中率、TTL、当前缓存版本 |
| `POST /cache/clear` | **新增**：清空缓存，可传 `{"kinds": ["qa"]}` 定向清理 |
| `GET /health` | **新增**：轻量健康检查（含任务队列后端与内置 worker 状态） |
| `GET /` | 前端页面 |

前端的"提问"旁边多了一个 **跳过缓存** 勾选框：勾上走完整链路，不勾走缓存，
方便你亲眼对比"命中缓存"与"真实计算"的耗时差（答案区会显示徽标与毫秒数）。

上传则是**立即返回任务号**，页面轮询 `/status/{task_id}` 展示排队 → 解析向量化 → 完成的全过程——
一本大 PDF 不再让请求干等几十秒（这正是第八节消息队列的收益）。

---

## 六、安装与运行

```bash
cd RAG
pip install -r requirements.txt

# 1) 配置（与无缓存版相同的 DEEPSEEK_API_KEY，加缓存/队列相关项）
copy .env .env        # Windows；Linux/macOS 用 cp

# 2) 启动 Redis（可选，没有也能跑，缓存与队列都会自动降级为进程内实现）
redis-server                  # 本机默认 127.0.0.1:6379

# 3) 启动服务（默认已在 web 进程内内置一个任务 worker，单机开箱即用）
python app.py                 # http://127.0.0.1:8000
```

模型文件放在本项目根目录：`text2vec-base-chinese/`、`mmarco-mMiniLMv2-L12-H384-v1/`。

### 运行独立 worker（可选：进程隔离 / 水平扩展）

默认配置下单机不需要——`QUEUE_WORKER_IN_APP=1` 时 web 进程里有消费线程。
要把"解析+嵌入+入库"的重活彻底从 web 进程剥离，或多开消费者分摊：

```bash
python worker.py                      # 终端 A（可开多个，Redis 消费组自动分流）
set QUEUE_WORKER_IN_APP=0             # 可选：web 进程不再消费
python app.py                         # 终端 B
```

worker 处理中途崩溃不会丢任务：消息留在 PEL，重启后 `XAUTOCLAIM` 自动认领重做
（任务幂等：清库重入，向量缓存兜底重复计算）。

### 验证缓存层（不需要模型、不需要联网）

```bash
python verify_cache.py                       # 默认 auto
CACHE_BACKEND=memory python verify_cache.py   # 只测内存后端
CACHE_BACKEND=redis  python verify_cache.py   # 只测真实 Redis
```

Windows 下想拿到干净的 UTF-8 日志（PowerShell 重定向默认是 UTF-16）：

```powershell
$env:VERIFY_LOG="verify_memory.log"; python verify_cache.py
```

覆盖 7 组共 35 条用例：基础读写/TTL、问答缓存、向量缓存、精排缓存、**版本号失效**、
定向清理与统计、后端健康。退出码 0 表示全部通过。

实测结果（本机）：

| 后端 | 结果 |
|---|---|
| `memory`（进程内内存） | **通过 35/35，失败 0** |
| `redis`（真实 RESP 协议往返） | **通过 35/35，失败 0** |

> 注意：`CACHE_BACKEND=redis` 时如果连不上 Redis，脚本会**直接报错而不是静默降级**，
> 并在结果里标记 `Redis 后端可用性` 失败 —— 避免"以为测了 Redis，其实测的是内存"。

### 验证任务队列（不需要模型、不需要 DeepSeek Key）

```bash
python verify_queue.py                        # 默认（auto，通常降级 memory）
QUEUE_BACKEND=memory python verify_queue.py    # 只测进程内队列
QUEUE_BACKEND=redis  python verify_queue.py    # 真实 Redis Stream
```

它注入**假 handler**（模拟成功/失败/耗时）把队列流转真实跑一遍：入队与状态、
消费成功/失败路径、毒丸隔离、FIFO、**入队立即返回 vs 同步阻塞的耗时对比**、
状态 TTL；Redis 模式下额外验证**跨实例消费（模拟独立 worker 进程）、ACK 防重、
崩溃恢复（XAUTOCLAIM 认领重做）**。实测：memory 后端 **24/24**、
Redis Stream 后端（mini redis 真实 RESP 往返）**28/28**，失败 0。

### 验证 Redis 后端的关键实现细节

`verify_redis_backend.py` 会断言几条"上生产才看得出来"的细节：

```bash
python tools/mini_redis_resp.py 6399    # 终端 A：最小 RESP 服务（纯标准库）
python verify_redis_backend.py          # 终端 B
```

它验证：

1. **写缓存真的带 TTL** —— 命令里必须有 `SET ... EX`，否则数据永久驻留；
2. **批量清理必须用 `SCAN` 游标遍历，绝不能用 `KEYS`** ——
   `KEYS` 在大 key 空间下会阻塞整个 Redis 实例，是线上经典事故；
3. **版本号用原生 `INCR`** —— 原子操作，多实例并发上传不会互相覆盖版本号；
4. 中文/长文本经过 RESP 编解码后不丢字节；
5. `clear()` 能清掉**所有历史版本**的 key（不只是当前版本）。

实测结果：**通过 15/15，失败 0**。

> 为什么不用 python `redis` 包跑这两个脚本？
> `tools/resp_client.py` 是一个纯标准库的 RESP 客户端，接口与 redis-py 一致，
> 配合 `tools/mini_redis_resp.py` 就能在没有 `redis` 包的环境下真实跑通
> `cache.py` 的 `_RedisBackend`（协议是真的，只有客户端实现是极简版）。
> 装了 `redis` 包时，直接 `pip install -r requirements.txt` 后用 `CACHE_BACKEND=redis` 跑即可，
> 不需要 `RESP_CLIENT_MODULE` 这个测试钩子（默认就是官方包）。


### 观察缓存效果

启动服务后重复问同一个问题，或在页面上点 **刷新** 看缓存统计：

```bash
curl http://127.0.0.1:8000/cache/stats
```

预期：第一次 `cache_hit=false`（耗时实打实），第二次 `cache_hit=true, cache_type="exact"`（毫秒级返回）。

---

## 七、相对无缓存版的代码改动

| 文件 | 说明 |
|---|---|
| `cache.py` | **新增**。三种缓存的读写封装 + Redis/内存双后端 + 版本号失效 + 命中统计 |
| `rag_langchain.py` | 嵌入方法包一层向量缓存；`rerank()` → `rerank_cached()`；新增 `query()`（带缓存的问答入口）、`invalidate_caches()`、`SemanticCache` |
| `app.py` | `/ask` 改走 `query()`；`/upload` 默认异步入队（`?sync=true` 保留同步路径）；新增 3 个运维接口与 `/status/{task_id}`；lifespan 拉起内置 worker；前端路径改到 `templates/` |
| `tasks.py` | **新增（队列层）**。Redis Stream / 进程内双后端、任务状态机、消费循环（可注入 handler）、`process_upload_file()`（解析+切块+入库+失效缓存，同步/异步共用） |
| `worker.py` | **新增（队列层）**。独立消费进程入口（`python worker.py`，可多开） |
| `templates/index.html` | 新增缓存命中徽标、耗时、跳过缓存开关、缓存统计面板；上传改为轮询任务状态 |
| `verify_cache.py` | **新增**。缓存层验证脚本（35 条用例，不依赖模型） |
| `verify_queue.py` | **新增（队列层）**。队列验证脚本（memory 24 条 / redis 28 条用例，注入假 handler，不依赖模型） |
| `verify_redis_backend.py` | **新增**。Redis 后端关键实现断言（TTL / SCAN / INCR，15 条用例） |
| `tools/resp_client.py`、`tools/mini_redis_resp.py` | **新增**。纯标准库的最小 RESP 客户端/服务，用于在没有 `redis` 包时验证 Redis 路径；已扩展 XADD/XREADGROUP/XACK/XAUTOCLAIM 等 Stream 命令以覆盖队列路径 |
| `requirements.txt` | 新增 `redis>=5.0`（不装也能跑，缓存与队列都会自动降级） |
| `.env.example`、`.gitignore` | **新增**。缓存/队列配置说明 / 本项目忽略规则 |

**没有改的**：Chroma 用法、LCEL 链、评测口径 —— 所以 Hit Rate / MRR 与
无缓存版 / 缓存版可直接对比（缓存不影响检索结果，只影响要不要重算）。

### 切块：按 token，不按字符

`split_by_tokens()` 用**该语种 embedding 模型自己的 tokenizer** 切块，默认 256 token、
重叠 40（`CHUNK_TOKENS` / `CHUNK_OVERLAP_TOKENS` 可用环境变量覆盖）。

- **为什么不用字符**：同样 300 字符，中文约 250 token、英文只有约 52 token，差近 5 倍。
  用同一个字符数切两种语言，"一个块"在中英两侧承载的信息量完全不可比。
  实测改前 en 库每块中位仅 75 token，改后两库都是 256。
- **为什么用 offset 而不是 decode**：实测 `tok.decode(ids)` **无法**还原原文
  （中文会被规整、英文会丢字符）。所以只借 tokenizer 算 token 的字符边界，
  再按字符位置切原文，保证每个块都是原文的**逐字子串**。
- **为什么取 256 而不是模型上限 512**：留一半余量，避免将来换模型/改配置时
  再次撞上"超长被静默截断"。

---

## 八、消息队列：上传异步化与削峰（已实现）

缓存解决的是"**同样的活不要干第二遍**"，但它不解决另外两个问题：

1. **上传阻塞**：`/upload` 原来在请求内同步完成解析、切块、嵌入、入库，
   一本大 PDF 用户要等几十秒；
2. **削峰**：多人同时上传时，请求会堆积在 FastAPI 进程里，把 CPU 占满。

消息队列解决的是"**把必须马上做的事，改成排队慢慢做**"。实现见
`tasks.py` + `worker.py`，链路如下：

```
/upload ──► 存文件 + 入队（XADD Redis Stream）──► 立刻返回 task_id
                        │
                  worker 消费（XREADGROUP）──► 解析+切块+嵌入+入库 ──► 更新任务状态
                        │
       前端拿 task_id 轮询 GET /status/{task_id}
```

### 后端选择：与缓存层同一套哲学

| `QUEUE_BACKEND` | 行为 | 适用 |
|---|---|---|
| `auto`（默认） | 跟随缓存层探测结果：Redis 可用则用 **Redis Stream**（跨进程共享、可跑独立 worker），否则进程内队列 | 开发/演示 |
| `redis` | 强制 Redis Stream，连不上**直接报错** | 生产（避免静默降级后 worker 进程消费不到任务） |
| `memory` | 进程内队列（`queue.Queue`），web 进程内的后台线程消费 | 单机/离线调试 |

为什么选 Redis Stream 而不是 RabbitMQ / `BLPOP`：
项目已依赖 redis（缓存层在用），不引入新中间件；`BLPOP` 取出即丢、
worker 崩溃即丢消息，而 Stream 的消息进组后留在 PEL 直到 `XACK`——
worker 挂了，重启后 `XAUTOCLAIM` 认领重做（任务幂等：清库重入，
向量缓存兜底重复计算，重做是安全的）。消费组（XREADGROUP）还天然支持
多 worker 分摊，`python worker.py` 多开即水平扩展。

一个容易踩的实现细节：**消费组必须在第一条消息入队之前创建**
（`XGROUP CREATE` 的位点默认是队尾 `$`）——先 `XADD` 再建组，
组诞生前的消息会被永远漏掉。所以 `ensure_ready()` 在 enqueue 侧就会调用。

### 缓存层配合的一处关键改动：失效点后移

队列化后缓存失效（`invalidate_caches()` → `bump_version()`）从
**"收到文件"挪到了"worker 入库成功"**（`tasks.process_upload_file` 内部）：

> 任务还在排队时，旧答案其实仍然正确——提前失效只会让用户在这段时间
> 白白重算，而新答案又还没就绪。

这个函数同时是 `?sync=true` 同步路径的实现（同一份代码，两条路径不会漂移）。

### 任务状态与轮询

- 状态机：`queued → processing → succeeded | failed`，存在 `rag:task:{task_id}`
  （Redis）或进程内字典（memory），TTL 默认 24 小时（`TASK_TTL`）；
- `GET /status/{task_id}` 404 = 任务不存在或已过期；
- 失败的任务把错误写进状态（前端直接显示），**并照常 ACK**——不自动重试：
  失败原因多半是文件本身的问题，重试一百次也一样，让用户改完重新上传才是正解。
  崩溃恢复只针对"worker 没跑完 handler 就死掉"的场景（消息还在 PEL）。

### 判断队列写得对不对的标准（与缓存层一脉相承）

- **队列是功能层，不是加速层**：入队失败必须让 `/upload` 返回失败（用户重传），
  不能学缓存 fail-open 静默吞掉——文件收了却没人处理是最坏的体验；
- **毒丸隔离**：单个坏文件失败不拖垮队列，后续任务照常消费；
- **状态可见性跟随队列后端**：任务状态跟队列走（队列在 Redis → 状态在 Redis），
  而不是跟缓存后端走——否则 worker.py 进程写的状态，web 进程轮询永远 404。

> LLM 缓存这类"边界"要格外小心：它必须可随时清空且不改变正确答案，
> 这也是本项目坚持"缓存只是加速层、fail-open、版本号失效"的原因。

### 还可以继续做的

- 上传文件的类型/大小限制（目前只校验扩展名）；
- 任务优先级与死信队列（连续失败的隔离区，而非单次 failed 即终止）；
- `uploads/` 孤儿文件的定期清理（worker 崩溃时暂存文件会留下）。
