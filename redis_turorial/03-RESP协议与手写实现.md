# 03 RESP 协议与手写实现

对应代码：`tools/resp_client.py`（130 行）、`tools/mini_redis_resp.py`（221 行）

这一节是整套教程里最有价值的部分。**Redis 的一切都建立在 RESP 之上**，
但绝大多数人从没看过它长什么样——因为官方的 `redis` 包把它全遮住了。

而这个项目里有**一份完整的、能跑通的 RESP 实现**，只有 130+221 行。

## RESP 是什么

**RESP = REdis Serialization Protocol**，是客户端和服务端之间讲的话。

它极其简单：**一行一个"类型标记 + 内容"，用 `\r\n` 分隔**。
没有 JSON，没有二进制头，没有握手协商（RESP2 下）。

### 五种类型

| 类型 | 首字节 | 例子 | 含义 |
|---|---|---|---|
| Simple String | `+` | `+OK\r\n` | 状态回复（成功） |
| Error | `-` | `-ERR unknown command\r\n` | 错误 |
| Integer | `:` | `:42\r\n` | 整数 |
| Bulk String | `$` | `$5\r\nhello\r\n` | 二进制安全的字符串 |
| Array | `*` | `*2\r\n$3\r\nfoo\r\n$3\r\nbar\r\n` | 多个值的列表 |

两个必须注意的点：

1. **`$` 后面跟的是"长度"，不是"内容"**。因为字符串可能包含 `\r\n`，
   所以必须先告诉对方读几个字节，这叫**长度前缀（length-prefixed）**。
   这是二进制安全的关键——你存什么字节，取出来就是什么字节。
2. **`$` 和 `*` 都可以是 `-1`**，表示 nil / 不存在。所以 `GET` 一个不存在的 key 会收到 `$-1\r\n`，
   而不是空字符串。**"不存在"和"空值"是两件不同的事**，协议层面就分开了。

### 亲手看一眼

不需要装任何客户端，用 `nc` 或 Python 的 socket 就能直接和 Redis 对话：

```bash
printf 'PING\r\n' | nc 127.0.0.1 6379
# +PONG

printf 'SET foo bar\r\nGET foo\r\nGET nosuchkey\r\n' | nc 127.0.0.1 6379
# +OK
# $3
# bar
# $-1
```

（注意：`GET nosuchkey` 回的是 `$-1`，不是 `$0`。）

### 客户端发出去的是什么

客户端发命令用 **Array** 形式。`SET foo bar` 在网线上是：

```
*3\r\n$3\r\nSET\r\n$3\r\nfoo\r\n$3\r\nbar\r\n
└┬┘    └┬┘ └┬┘    └┬┘ └┬┘    └┬┘ └┬┘
 3个参数 长度3 SET  长度3 foo  长度3 bar
```

对应 `tools/resp_client.py:36-41`：

```python
def _send(self, args) -> None:
    out = [b"*" + str(len(args)).encode() + b"\r\n"]
    for a in args:
        data = a if isinstance(a, bytes) else str(a).encode("utf-8")
        out.append(b"$" + str(len(data)).encode() + b"\r\n" + data + b"\r\n")
    self._connect().sendall(b"".join(out))
```

**注意它先拼成完整的 bytes 再一次性 `sendall`**，而不是一个参数一次 `send`。
这是对的——减少系统调用，也避免对方读到"半个命令"。

## 客户端解析：递归下降

`resp_client.py:62-82` 的 `_parse()` 是个教科书式的**递归下降解析器**：

```python
def _parse(self):
    line = self._read_line()
    kind, rest = line[:1], line[1:]
    if kind == b"+":  return rest.decode("utf-8")          # 状态
    if kind == b"-":  raise RuntimeError(rest.decode())     # 错误
    if kind == b":":  return int(rest)                      # 整数
    if kind == b"$":                                        # 批量字符串
        n = int(rest)
        if n == -1: return None                             # ← nil
        data = self._read_exact(n + 2)[:-2]                 # ← 读 n+2 含结尾 \r\n
        return data.decode("utf-8")
    if kind == b"*":                                        # 数组
        n = int(rest)
        if n == -1: return None
        return [self._parse() for _ in range(n)]            # ← 递归
```

**`Array` 那一条是递归的**：数组的每个元素又可以是任意 RESP 类型，
包括另一个数组。`SCAN` 的返回就是 `[cursor, [key1, key2, ...]]`，正好用上。

还有一个容易踩的细节在 `_read_line()`：

```python
def _read_line(self) -> bytes:
    buf = b""
    while not buf.endswith(b"\r\n"):
        chunk = self._connect().recv(1)     # ← 一次只读 1 字节
```

**为什么一次只读 1 字节？** 因为 TCP 是**流**，不保证"一次 recv 就是一行"。
你 `recv(1024)` 可能读到一行半、也可能只读到半个字节。
这里用最笨但最正确的办法：逐个字节读到 `\r\n` 为止。

> 生产级实现会用缓冲区（读一大块，自己在内存里找 `\r\n`，剩下的留给下次），
> 效率高得多。但**"逐字节读"是理解协议最直白的写法**，读代码时先看懂这个。

对称地，`_read_exact(n)` 负责"精确读 n 个字节"，因为 `$` 后面已经告诉你长度了：

```python
def _read_exact(self, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = self._connect().recv(n - len(data))    # ← 每次只补还缺的部分
        if not chunk:
            raise ConnectionError("连接被对端关闭")
        data += chunk
    return data
```

## 服务端：一个 if 链就够了

`mini_redis_resp.py:78-157` 的 `dispatch()` 就是一个大的 `if/elif`：

```python
def dispatch(args: List[bytes]) -> bytes:
    cmd = _to_str(args[0]).upper()
    argv = [_to_str(a) for a in args[1:]]
    _commands.append(" ".join([cmd] + argv))     # ← 记录命令，便于事后断言

    with _lock:
        if cmd == "PING":
            return _simple("PONG")
        if cmd == "GET":
            key = argv[0]
            _is_expired(key)                     # ← 惰性过期
            return _bulk(_data.get(key))
        if cmd == "SET":
            ...                                  # 解析 EX / PX
        if cmd == "INCR":
            current = int(_data.get(key, "0")) + 1
            _data[key] = str(current)
            _expire.pop(key, None)               # ← 版本号不设过期
            return _integer(current)
```

几个值得注意的点：

**① 每个响应类型都有对应的构造函数**（`:39-62`）。想清楚"我要回哪种类型"，
比手拼字节串可靠得多：

```python
def _simple(text): return b"+" + _encode(text) + b"\r\n"
def _error(text):  return b"-" + _encode(text) + b"\r\n"
def _integer(n):   return b":" + str(n).encode() + b"\r\n"
def _bulk(value):
    if value is None:
        return b"$-1\r\n"                      # ← nil 的表示法
    ...
```

**② `_commands` 列表是整个测试方案的关键**（`:32`、`:84`）。
服务端把收到的每条命令记下来，测试脚本就能事后断言**"客户端到底发了什么命令"**。

这就是 `verify_redis_backend.py` 能测"必须用 SCAN 而不是 KEYS"的原理：

```python
check("没有使用 KEYS（线上会阻塞 Redis 实例）",
      not backend.used_keys())
```

**光看客户端代码是测不出这个的**——你得看它在网线上真的发了什么。这个设计很聪明。

**③ SET 的选项解析**（`:98-110`）故意只认 `EX`/`PX`，因为 `_RedisBackend` 只用这两个：

```python
ttl = None
for i, opt in enumerate(argv[2:], start=2):
    if opt.upper() in ("EX", "PX") and i + 1 < len(argv):
        n = float(argv[i + 1])
        ttl = n if opt.upper() == "EX" else n / 1000.0
```

## 为什么这个设计很聪明

看 `mini_redis_resp.py` 开头的说明：

> 要真实验证 `_RedisBackend`，需要（a）python `redis` 客户端包，（b）一个 Redis 服务。
> 本机有 redis-server，但客户端包未安装且当前沙箱不允许写入 Python 环境。

所以作者用**标准库 socket** 自己造了一个。这带来三个好处：

1. **零依赖**：不需要 `pip install redis`，不需要起真的 Redis 服务
2. **可断言**：`_commands` 记录了全部命令，能验证"实现是否符合预期"而不只是"结果对不对"
3. **依然真实**：被测的是 `cache.py` 里那段**生产用的代码路径**，
   只有"对端"是替身——协议是真的，代码路径是真的

这是一种很成熟的测试思路：**替换环境，不替换被测代码。**

## 但它有一个根本限制

因为是自己写的，所以它**只实现了自己用到的那几个命令**：

```
PING GET SET(EX) INCR DELETE SCAN(COUNT/MATCH) EXISTS KEYS FLUSHALL
以及 redis-py 连接时的 CLIENT SETINFO / CLIENT SETNAME
```

这意味着：

- **它不能被当成"Redis 兼容性测试"**。它验的是"我的后端逻辑对不对"，
  **不是**"我的客户端能不能和真 Redis 说话"。
- 而且——见下一节——它和真实 Redis 在**一个命令名上就不一致**，
  导致那个"刻意模仿 redis-py"的客户端**其实连不上真 Redis**。

## 自己动手看命令

`mini_redis_resp.py` 退出时会把收到的所有命令写到 `mini_redis_commands.log`：

```python
finally:
    srv.close()
    with open("mini_redis_commands.log", "w", encoding="utf-8") as f:
        f.write("\n".join(_commands))
```

这是最直观的"看网线上发生了什么"的方式。第 7 节有完整的动手步骤。

---

**下一节**：[04 后端抽象与降级](04-后端抽象与降级.md) —— `cache.py` 怎么在 Redis 和内存之间切换
