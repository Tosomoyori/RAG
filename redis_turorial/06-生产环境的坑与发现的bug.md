# 06 生产环境的坑与三个 bug

这一节把前面几节提到的生产级注意事项集中起来，并把我在读代码时**实际发现的三个 bug** 讲清楚。
后者的教学价值更高——**它们都不是"写错了一个字符"，而是"设计和实现之间出现了缝隙"**。

## 一、SCAN vs KEYS：最重要的一条

```python
def delete_prefix(self, prefix: str) -> int:
    """用 SCAN 删除，绝不用 KEYS（KEYS 会阻塞整个 Redis 实例）。"""
    deleted = 0
    for key in self._client.scan_iter(match=f"{prefix}*", count=500):
        deleted += self._client.delete(key)
    return deleted
```

### 为什么 `KEYS` 是灾难

`KEYS pattern` 会**一次性遍历整个 keyspace**，并且在执行期间
**阻塞 Redis 的所有其他命令**——因为 Redis 的命令执行是单线程的。

后果：

| key 数量 | `KEYS` 耗时 | 影响 |
|---|---|---|
| 1 万 | 几毫秒 | 无感 |
| 100 万 | 几百毫秒 ~ 秒级 | 所有请求卡住 |
| 1000 万 | 数秒 ~ 数十秒 | **整个服务不可用** |

而且它**没有任何警告**——本地开发时你的 Redis 里就几百个 key，快得很；
一到线上就变成事故。

### `SCAN` 的解决方式：游标分批

`SCAN` 每次只返回**一小批** key 和一个**游标（cursor）**，
下次带着游标继续，直到游标回到 `"0"` 表示遍历结束。

```
SCAN 0 MATCH rag:* COUNT 500   ->  [ "1234", [key1, key2, ...] ]   游标不为 0，继续
SCAN 1234 MATCH rag:* COUNT 500 ->  [ "5678", [...] ]              继续
...
SCAN 9012 MATCH rag:* COUNT 500 ->  [ "0", [...] ]                 游标归零，结束
```

**每次调用之间 Redis 可以服务其他请求**，不会长时间阻塞。

对应客户端里的实现（`resp_client.py:107-115`）：

```python
def scan_iter(self, match: str = "*", count: int = 10) -> Iterator[str]:
    cursor = "0"
    while True:
        reply = self._cmd("SCAN", cursor, "MATCH", match, "COUNT", str(count))
        cursor, keys = reply[0], reply[1]
        for key in keys:
            yield key
        if str(cursor) == "0":      # cursor 归零 = 遍历结束
            return
```

注意它是个**生成器**（`yield`）——边扫边处理，不用把所有 key 攒在内存里。

### `SCAN` 的两个"坑中坑"

1. **`SCAN` 不保证返回所有元素**。如果在遍历过程中 keyspace 发生变化，
   某些 key 可能被返回多次、也可能被漏掉。**对"清理类"操作这是可接受的**
   （漏掉的 key 有 TTL 兜底），但对"必须精确"的场景不行。
2. **`COUNT` 是提示不是保证**。它告诉 Redis "我大概想一次拿这么多"，
   实际返回数量可能多也可能少。**不要写依赖返回数量的逻辑。**

> 项目里 `verify_redis_backend.py` 专门有一条断言：
> ```python
> check("没有使用 KEYS（线上会阻塞 Redis 实例）", not backend.used_keys())
> ```
> 而且它是靠**记录服务端收到的命令**来验证的——见第 3 节。
> 这说明作者很清楚这条规则的重要性，并且用测试把它**锁住了**。

## 二、原子性：`INCR` 而不是读-改-写

已在第 5 节详细讲过。核心：

```python
def incr(self, key: str) -> int:
    return int(self._client.incr(key))       # 服务端保证原子
```

**Redis 的单线程模型让单个命令天然原子**。凡是能用一条命令表达的复合操作，
就不要拆成"读 + 改 + 写"——那是一切并发 bug 的源头。

同类的还有 `SETNX`（分布式锁）、`HSET`（部分更新）、`SET ... EX`（设值+过期一步完成）。

## 三、协议版本：RESP3 与 `HELLO`

已在第 4 节讲。要点：redis-py 5+ 默认 RESP3，连接时发 `HELLO`，
而 Redis 6 以下不认识 → 整个后端失效。项目用 `protocol=2` 强制降级。

**教训**：客户端库的默认行为会随版本变化，而服务端不一定跟得上。
升级依赖时要意识到"协议层"也可能变。

## 四、N+1 往返：一个性能问题（不是 bug）

这是我在读代码时注意到的**性能隐患**。看 `cache.py` 的向量缓存：

```python
def get_embeddings(texts, model_tag=""):
    result = {}
    for text in texts:
        digest = embedding_key(text)
        value = get(_embed_storage_key(text, model_tag))     # ← 循环里一次 GET
        ...
```

**每个文本一次独立的 `GET`**。用 `mini_redis_resp.py` 记录的 `_commands` 就能看到，
一次批量查 173 个块会产生 **173 条 `GET` 命令**。

同样，`set_embeddings` 是 N 条 `SET`。

| 场景 | 173 次往返的代价 |
|---|---|
| 本机 Redis（回环） | ~17 毫秒，基本无感 |
| 跨网络 Redis（1ms RTT） | **~173 毫秒**，明显拖慢 |
| 跨可用区（5ms RTT） | **~865 毫秒**，不可接受 |

**正确的做法是 `MGET`**（一次拿多个 key）或 **pipeline**（一次发多条命令、一次收所有回复）：

```python
# 现在：N 次往返
for text in texts:
    get(key(text))

# 改进：1 次往返
values = client.mget([key(t) for t in texts])
```

> 这类问题叫 **N+1 查询**，是缓存和数据库领域最常见的性能陷阱。
> **本地开发几乎发现不了**（回环网络快到看不出来），一到真实网络就暴露。

## 五、本项目没有处理的三个缓存经典问题

这三个不是 bug，是**已知未做**的部分，值得知道名字：

### 缓存穿透（Penetration）

查询一个**根本不存在**的数据，每次都会穿透到后端。
恶意攻击者可以构造大量不存在的 key 打垮系统。

标准解法：**缓存空值**（`SET key "" EX 60`）或**布隆过滤器**。

### 缓存雪崩（Avalanche）

**大量 key 在同一时刻集中过期**，请求全部涌向后端。

本项目有实际风险：所有 QA 缓存的 TTL 都是 3600 秒，
如果服务刚启动时批量写入，1 小时后会集体过期。

标准解法：**TTL 加随机抖动**（`3600 + random(0, 300)`）。

### 缓存击穿（Breakdown / Stampede）

**某个热 key 过期瞬间，大量并发请求同时发现未命中**，
一起去查后端、一起去调 LLM。

本项目的 `bump_version()` 是**主动制造雪崩**——版本号一涨，
所有 QA 缓存同时失效，下一秒的并发请求会**全部打到 DeepSeek**。

标准解法：**互斥锁**（只让一个请求去计算，其余等待）或**逻辑过期**
（不真过期，异步刷新）。

> 对一个单机演示项目来说这些都不是必须的。但**知道它们存在**，
> 你才能判断"我这个场景需不需要处理"。

---

# 三个真实存在的 bug

下面三个是我读代码时发现的。**注意它们的性质各不相同**——
这比 bug 本身更有教学意义。

## Bug 1：`DELETE` vs `DEL` —— 客户端连不上真 Redis

**状态：仍然存在**

`tools/resp_client.py:104-105`：

```python
def delete(self, *keys: str) -> int:
    return int(self._cmd("DELETE", *keys))
```

而真实 Redis 的命令是 **`DEL`**，**没有 `DELETE` 这个命令**。

三方对照（我实测确认过）：

| 谁 | 发的/认的命令 |
|---|---|
| 真实 `redis-py` 8.1.0 | `DEL` |
| 项目的 `RespClient` | `DELETE` |
| 项目的 `mini_redis_resp.py` | `DELETE`（`dispatch` 里只实现了这一个） |

进程内直接调 mini 服务端的 `dispatch` 验证：

```
DELETE   -> b':0\r\n'                ← 认
DEL      -> b'-unknown command DEL'  ← 不认
```

### 为什么这很值得讲

`resp_client.py` 的开头写着：

```python
class RespClient:
    """接口刻意模仿 redis-py，便于直接替换。"""
```

**接口模仿了，协议没模仿。** 结果是：

- `RespClient` + `mini_redis_resp.py` → ✅ 能跑（两边都错成一样的）
- `RespClient` + **真实 Redis** → ❌ `clear()` 一调用就报
  `unknown command 'DELETE'`

也就是说，这个"便于直接替换"的客户端**不能替换**。

**为什么一直没暴露？** 因为它只在测试里和 mini 服务端配对使用，
而 mini 服务端是照着它的错误实现的。**两个错误互相印证，就成了一对"正确"。**

修复很简单（把两处都改成 `DEL`），但它说明一个更普遍的问题：

> **测试替身（test double）如果不忠实于真实协议，测出来的"通过"是假的。**
> 这个 mini server 验证了"后端逻辑对不对"，但**不能**验证"能不能和真 Redis 通信"。
> 这两件事必须分清楚。

## Bug 2：注释描述了一个从未实现的意图 —— 已修复

**状态：本项目已修复**

`cache.py` 原来的 `set_embeddings` 写着：

```python
def set_embeddings(pairs: List[tuple]) -> None:
    """pairs: [(文本, 向量), ...]。文本 hash 与模型名绑定，换模型不会命中旧向量。"""
    for text, vector in pairs:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        set(f"rag:embed:{digest}", list(vector), EMBEDDING_TTL)
```

注释说"与模型名绑定"，**但代码里根本没有模型名**——key 只有文本 hash。

后果：换 embedding 模型后，**同一段文本会命中旧模型算出的向量**。
而且两个模型都是 768 维，**不会报错**，只是检索结果静默变烂。

**修复**：key 改成 `rag:embed:{cache_tag}:{digest}`，
`cache_tag` 现在形如 `zh|./text2vec-base-chinese|seq512`——
覆盖了所有会改变向量取值的因素。

### 教学点

**注释写的不是代码做的事，而是写注释的人打算让代码做的事。**
两者可能不一致，而且这种不一致**没有任何机制会自动发现**。

这是最难查的一类 bug：你读注释以为它是安全的，于是不去看实现。

## Bug 3：函数少传一个参数 —— 已修复

**状态：本项目已修复**

```python
def _embed_query_cached(raw_embed_query, text: str) -> List[float]:   # 要 2 个参数
    ...

# 调用处：
vector = _embed_query_cached(question)                                # 只传了 1 个
```

会直接抛 `TypeError: missing 1 required positional argument: 'text'`。

**为什么一直没暴露？** 因为这条路径在默认配置下**永远不会被执行**：

```python
SEMANTIC_CACHE_ENABLED = os.getenv("SEMANTIC_CACHE", "0") == "1"   # 默认 false
...
if SEMANTIC_CACHE_ENABLED:
    vector = _embed_query_cached(question)      # ← 默认关着，走不到
```

**所以只要有人把语义缓存打开（`SEMANTIC_CACHE=1`），整个功能立刻崩掉。**
而这是个"选配功能"，平时测试根本不会覆盖到。

### 教学点

**默认关闭的功能 = 长期不被执行的代码 = bug 的温床。**

推论：如果你有一个"以后可能会开"的开关，要么**给它写测试**，
要么**把它删掉**。放在那里不管，它只会腐烂。

---

## 小结：三个 bug 的共性

| Bug | 性质 | 为什么难发现 |
|---|---|---|
| `DELETE` vs `DEL` | 协议不兼容 | 测试替身跟着一起错，互相印证 |
| 缓存 key 不含模型 | 实现与注释不符 | 注释让人放心，不去看实现 |
| 少传一个参数 | 死代码里的错误 | 默认配置下永远不执行 |

**没有一个是"逻辑写错了"。** 它们都藏在**缝隙**里：
注释与实现之间、测试与真实环境之间、默认配置与可选配置之间。

读代码时，最值得警惕的恰恰是这些地方。

---

**下一节**：[07 动手实验](07-动手实验.md)
