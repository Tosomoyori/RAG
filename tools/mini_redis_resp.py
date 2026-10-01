"""
极简 RESP（Redis 协议）测试服务器 —— 用于验证 cache.py / tasks.py 的 Redis 代码路径。

为什么需要它？
  要真实验证 _RedisBackend / _RedisStreamQueue，需要（a）python `redis` 客户端包，
  （b）一个 Redis 服务。本机有 redis-server，但客户端包未安装且当前沙箱不允许写
  Python 环境。这个脚本用标准库 socket 直接讲 RESP 协议，配合 `redis` 客户端的
  RESP 解析器，就能把每条代码路径真实跑一遍，并把它发出的命令记录下来，
  用于断言"实现是否符合预期"（例如必须用 SCAN 而不是会阻塞实例的 KEYS）。

它**不是** Redis 的替代品，只实现了本测试用到的命令：
  PING GET SET(EX) INCR DELETE SCAN(COUNT/MATCH) EXISTS KEYS FLUSHALL
  以及 redis-py 连接时的 CLIENT SETINFO / CLIENT SETNAME（返回 OK 即可）
  Stream（tasks.py 队列用）：XADD(MAXLEN) XGROUP(CREATE/MKSTREAM)
  XREADGROUP(GROUP/COUNT/BLOCK/STREAMS/>) XACK XAUTOCLAIM XLEN

  Stream 实现与真 Redis 的差异（测试时要知道）：
  - XREADGROUP 不阻塞：BLOCK 参数被接受但立即返回 nil（空），
    所以消费侧的"阻塞等待"语义无法在这里验证，只验证协议往返；
  - XAUTOCLAIM 一次认领全部符合条件的消息，cursor 恒为 0-0；
  - 不支持按 ID 读 pending、不维护 idle 之外的 PEL 元数据。

用法：
    python tools/mini_redis_resp.py 6399            # 启动在 6399 端口
    （另开一个终端）CACHE_BACKEND=redis REDIS_URL=redis://127.0.0.1:6399/0 python verify_cache.py
    （另开一个终端）QUEUE_BACKEND=redis REDIS_URL=redis://127.0.0.1:6399/0 python verify_queue.py
"""
import fnmatch
import socket
import sys
import threading
import time
from typing import Dict, List

HOST = "127.0.0.1"
DEFAULT_PORT = 6399

_data: Dict[str, str] = {}          # 简化：只存字符串（版本号、JSON）
_expire: Dict[str, float] = {}
_lock = threading.Lock()
_commands: List[str] = []           # 记录收到的命令，便于事后断言

# ---------- Stream 存储（tasks.py 队列验证用） ----------
# stream: key -> [(entry_id, {field: value}), ...]（按追加顺序，entry_id 单调递增）
# group:  key -> {group_name: {"next": 待投递下标, "pending": {entry_id: [consumer, since_ms]}}}
_streams: Dict[str, List[tuple]] = {}
_groups: Dict[str, Dict[str, dict]] = {}
_stream_ms = 0                       # 上一个 entry_id 的毫秒部分
_stream_seq = 0                      # 同一毫秒内的序号


def _next_stream_id() -> str:
    """生成单调递增的 entry_id（ms-seq）。真实 Redis 同款格式。"""
    global _stream_ms, _stream_seq
    now_ms = int(time.time() * 1000)
    if now_ms > _stream_ms:
        _stream_ms, _stream_seq = now_ms, 0
    else:
        _stream_seq += 1
    return f"{_stream_ms}-{_stream_seq}"


def _encode(value: str) -> bytes:
    return value.encode("utf-8")


def _simple(text: str) -> bytes:
    return b"+" + _encode(text) + b"\r\n"


def _error(text: str) -> bytes:
    return b"-" + _encode(text) + b"\r\n"


def _integer(n: int) -> bytes:
    return b":" + str(n).encode() + b"\r\n"


def _bulk(value) -> bytes:
    if value is None:
        return b"$-1\r\n"
    data = _encode(value) if isinstance(value, str) else value
    return b"$" + str(len(data)).encode() + b"\r\n" + data + b"\r\n"


def _array(items: List[bytes]) -> bytes:
    out = b"*" + str(len(items)).encode() + b"\r\n"
    for item in items:
        out += _bulk(item)
    return out


def _resp(obj) -> bytes:
    """递归编码 RESP 响应（Stream 命令的返回是嵌套数组，_array 编不了）。"""
    if obj is None:
        return b"$-1\r\n"
    if isinstance(obj, str):
        return _bulk(obj)
    if isinstance(obj, int):
        return _integer(obj)
    if isinstance(obj, (list, tuple)):
        out = b"*" + str(len(obj)).encode() + b"\r\n"
        for item in obj:
            out += _resp(item)
        return out
    raise TypeError(f"无法编码的类型: {type(obj)}")


def _stream_entry_fields(key: str, entry_id: str) -> dict:
    for eid, fields in _streams.get(key, []):
        if eid == entry_id:
            return fields
    return {}


def _is_expired(key: str) -> bool:
    exp = _expire.get(key)
    if exp is not None and exp < time.time():
        _data.pop(key, None)
        _expire.pop(key, None)
        return True
    return False


def _to_str(value: bytes) -> str:
    return value.decode("utf-8", "replace")


def dispatch(args: List[bytes]) -> bytes:
    """执行一条命令。返回 RESP 响应字节。"""
    if not args:
        return _error("empty command")
    cmd = _to_str(args[0]).upper()
    argv = [_to_str(a) for a in args[1:]]
    _commands.append(" ".join([cmd] + argv))

    with _lock:
        if cmd == "PING":
            return _simple("PONG")

        if cmd in ("CLIENT", "SELECT", "AUTH"):
            return _simple("OK")

        if cmd == "GET":
            key = argv[0]
            _is_expired(key)
            return _bulk(_data.get(key))

        if cmd == "SET":
            key, value = argv[0], argv[1]
            ttl = None
            for i, opt in enumerate(argv[2:], start=2):
                if opt.upper() in ("EX", "PX") and i + 1 < len(argv):
                    n = float(argv[i + 1])
                    ttl = n if opt.upper() == "EX" else n / 1000.0
            _data[key] = value
            if ttl is not None:
                _expire[key] = time.time() + ttl
            else:
                _expire.pop(key, None)
            return _simple("OK")

        if cmd == "INCR":
            key = argv[0]
            _is_expired(key)
            current = int(_data.get(key, "0")) + 1
            _data[key] = str(current)
            _expire.pop(key, None)
            return _integer(current)

        if cmd == "DELETE":
            n = 0
            for key in argv:
                if _data.pop(key, None) is not None:
                    _expire.pop(key, None)
                    n += 1
            return _integer(n)

        if cmd == "EXISTS":
            return _integer(sum(1 for k in argv if not _is_expired(k) and k in _data))

        if cmd == "KEYS":
            pattern = argv[0] if argv else "*"
            keys = [k for k in list(_data) if not _is_expired(k) and fnmatch.fnmatchcase(k, pattern)]
            # 故意记录：客户端如果用了 KEYS，_commands 里会出现这条，测试会断言它不存在
            return _array([_encode(k) for k in keys])

        if cmd == "SCAN":
            # 简化实现：一次性返回全部匹配 key，cursor 返回 0 表示遍历结束
            pattern, count = "*", 10
            for i, opt in enumerate(argv):
                if opt.upper() == "MATCH" and i + 1 < len(argv):
                    pattern = argv[i + 1]
                if opt.upper() == "COUNT" and i + 1 < len(argv):
                    count = int(argv[i + 1])
            keys = [k for k in list(_data) if not _is_expired(k) and fnmatch.fnmatchcase(k, pattern)]
            batch = keys[:count]
            return b"*2\r\n" + _bulk("0") + _array([_encode(k) for k in batch])

        if cmd == "FLUSHALL":
            _data.clear()
            _expire.clear()
            _streams.clear()
            _groups.clear()
            return _simple("OK")

        if cmd == "DBSIZE":
            return _integer(len(_data))

        # ---------- Stream 命令（tasks.py 的 Redis 队列路径） ----------
        if cmd == "XADD":
            # XADD key [MAXLEN ~|= n] id field value [field value ...]
            key = argv[0]
            maxlen, i = None, 1
            while i < len(argv) and argv[i].upper() == "MAXLEN":
                maxlen = int(argv[i + 2])     # ~ / = 前缀忽略，直接精确裁剪
                i += 3
            entry_id = argv[i] if i < len(argv) else "*"
            if entry_id != "*":
                return _error("mini redis 的 XADD 只支持自动生成 id (*)")
            flat = argv[i + 1:]
            if len(flat) < 2 or len(flat) % 2:
                return _error("XADD 需要 field value 成对参数")
            fields = {flat[j]: flat[j + 1] for j in range(0, len(flat), 2)}
            entry_id = _next_stream_id()
            stream = _streams.setdefault(key, [])
            stream.append((entry_id, fields))
            if maxlen is not None and len(stream) > maxlen:
                del stream[:len(stream) - maxlen]
            return _bulk(entry_id)

        if cmd == "XGROUP":
            # XGROUP CREATE key group $|0 [MKSTREAM]
            if len(argv) < 4 or argv[0].upper() != "CREATE":
                return _error("mini redis 只支持 XGROUP CREATE")
            key, group, group_id = argv[1], argv[2], argv[3]
            mkstream = any(a.upper() == "MKSTREAM" for a in argv[4:])
            groups = _groups.setdefault(key, {})
            if group in groups:
                return _error("BUSYGROUP Consumer Group name already exists")
            if key not in _streams and mkstream:
                _streams[key] = []
            # $ = 从当前队尾（新消息）开始投递；其它值一律从头开始
            start = len(_streams.get(key, [])) if group_id == "$" else 0
            groups[group] = {"next": start, "pending": {}}
            return _simple("OK")

        if cmd == "XREADGROUP":
            # XREADGROUP GROUP g c [COUNT n] [BLOCK ms] STREAMS key >
            if argv[0].upper() != "GROUP":
                return _error("syntax error")
            group, consumer = argv[1], argv[2]
            count, i = None, 3
            while i < len(argv):
                opt = argv[i].upper()
                if opt == "COUNT":
                    count = int(argv[i + 1]); i += 2
                elif opt == "BLOCK":
                    i += 2        # 接受参数但不阻塞：无消息立即返回 nil
                else:
                    break
            if i + 2 >= len(argv) or argv[i].upper() != "STREAMS":
                return _error("syntax error")
            key, marker = argv[i + 1], argv[i + 2]
            if marker != ">":
                return _error("mini redis 只支持 XREADGROUP 的 > (新消息) 模式")
            g = _groups.get(key, {}).get(group)
            if g is None:
                return _error(f"NOGROUP no such group {group} for key {key}")
            stream = _streams.get(key, [])
            entries = stream[g["next"]:]
            if count is not None:
                entries = entries[:count]
            g["next"] += len(entries)
            now_ms = int(time.time() * 1000)
            out = []
            for entry_id, fields in entries:
                g["pending"][entry_id] = [consumer, now_ms]
                flat = []
                for f, v in fields.items():
                    flat += [f, v]
                out.append([entry_id, flat])
            if not out:
                return b"*-1\r\n"        # 无新消息：nil（BLOCK 超时也是这个语义）
            return _resp([[key, out]])

        if cmd == "XACK":
            # XACK key group id [id ...]
            key, group, ids = argv[0], argv[1], argv[2:]
            g = _groups.get(key, {}).get(group)
            if g is None:
                return _integer(0)
            n = sum(1 for entry_id in ids if g["pending"].pop(entry_id, None) is not None)
            return _integer(n)

        if cmd == "XAUTOCLAIM":
            # XAUTOCLAIM key group consumer min-idle-ms start [COUNT n]
            key, group, consumer = argv[0], argv[1], argv[2]
            min_idle_ms = int(argv[3])
            start = argv[4] if len(argv) > 4 else "0-0"
            count = None
            if len(argv) > 6 and argv[5].upper() == "COUNT":
                count = int(argv[6])
            g = _groups.get(key, {}).get(group)
            if g is None:
                return _error(f"NOGROUP no such group {group} for key {key}")
            now_ms = int(time.time() * 1000)
            claimed = []
            for entry_id, (owner, since_ms) in list(g["pending"].items()):
                if entry_id < start:
                    continue
                if now_ms - since_ms >= min_idle_ms:
                    g["pending"][entry_id] = [consumer, now_ms]
                    flat = []
                    for f, v in _stream_entry_fields(key, entry_id).items():
                        flat += [f, v]
                    claimed.append([entry_id, flat])
                    if count is not None and len(claimed) >= count:
                        break
            return _resp(["0-0", claimed, []])

        if cmd == "XLEN":
            return _integer(len(_streams.get(argv[0], [])))

    return _error(f"unknown command {cmd}")


def read_command(conn) -> List[bytes]:
    """读一条命令，支持 RESP 数组（redis-py 用这个）。"""
    line = b""
    while not line.endswith(b"\r\n"):
        chunk = conn.recv(1)
        if not chunk:
            return []
        line += chunk
    if not line.startswith(b"*"):
        return [line.strip()]          # inline 命令
    n = int(line[1:].strip())
    args = []
    for _ in range(n):
        header = b""
        while not header.endswith(b"\r\n"):
            chunk = conn.recv(1)
            if not chunk:
                return []
            header += chunk
        length = int(header[1:].strip())
        payload = b""
        while len(payload) < length + 2:
            payload += conn.recv(length + 2 - len(payload))
        args.append(payload[:length])
    return args


def handle(conn) -> None:
    try:
        while True:
            args = read_command(conn)
            if not args:
                return
            conn.sendall(dispatch(args))
    except OSError:
        pass
    finally:
        conn.close()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, port))
    srv.listen(16)
    print(f"[mini-redis] listening on {HOST}:{port}", flush=True)
    try:
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=handle, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()
        print("[mini-redis] stopped", flush=True)
        with open("mini_redis_commands.log", "w", encoding="utf-8") as f:
            f.write("\n".join(_commands))


if __name__ == "__main__":
    main()
