"""
极简 RESP 客户端（仅标准库 socket）—— 用于在没有 python `redis` 包的环境下
验证 cache.py 的 _RedisBackend / tasks.py 的 _RedisStreamQueue 代码路径。

它只实现这两个模块真正用到的方法：
    缓存：ping() / get(key) / set(key, value, ex=) / incr(key)
          / delete(*keys) / scan_iter(match=, count=)
    队列：xadd() / xgroup_create() / xreadgroup() / xack() / xautoclaim() / xlen()

用法（配合 tools/mini_redis_resp.py）：
    python tools/mini_redis_resp.py 6399            # 终端 A
    CACHE_BACKEND=redis REDIS_URL=redis://127.0.0.1:6399/0 \
    RESP_CLIENT_MODULE=tools.resp_client python verify_cache.py     # 终端 B
    QUEUE_BACKEND=redis REDIS_URL=redis://127.0.0.1:6399/0 \
    RESP_CLIENT_MODULE=tools.resp_client python verify_queue.py     # 终端 B
"""
import re
import socket
from typing import Iterator, Optional, Tuple, Union


class RespClient:
    """接口刻意模仿 redis-py，便于直接替换。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 6379, db: int = 0):
        self.host = host
        self.port = port
        self.db = db
        self._sock: Optional[socket.socket] = None

    # ---------- 连接 ----------
    def _connect(self) -> socket.socket:
        if self._sock is None:
            self._sock = socket.create_connection((self.host, self.port), timeout=3)
            if self.db:
                self._send(["SELECT", str(self.db)])
        return self._sock

    def _send(self, args) -> None:
        out = [b"*" + str(len(args)).encode() + b"\r\n"]
        for a in args:
            data = a if isinstance(a, bytes) else str(a).encode("utf-8")
            out.append(b"$" + str(len(data)).encode() + b"\r\n" + data + b"\r\n")
        self._connect().sendall(b"".join(out))

    # ---------- RESP 解析 ----------
    def _read_line(self) -> bytes:
        buf = b""
        while not buf.endswith(b"\r\n"):
            chunk = self._connect().recv(1)
            if not chunk:
                raise ConnectionError("连接被对端关闭")
            buf += chunk
        return buf[:-2]

    def _read_exact(self, n: int) -> bytes:
        data = b""
        while len(data) < n:
            chunk = self._connect().recv(n - len(data))
            if not chunk:
                raise ConnectionError("连接被对端关闭")
            data += chunk
        return data

    def _parse(self):
        line = self._read_line()
        kind, rest = line[:1], line[1:]
        if kind == b"+":
            return rest.decode("utf-8")
        if kind == b"-":
            raise RuntimeError(rest.decode("utf-8"))
        if kind == b":":
            return int(rest)
        if kind == b"$":
            n = int(rest)
            if n == -1:
                return None
            data = self._read_exact(n + 2)[:-2]
            return data.decode("utf-8")
        if kind == b"*":
            n = int(rest)
            if n == -1:
                return None
            return [self._parse() for _ in range(n)]
        raise RuntimeError(f"无法解析的响应类型：{line!r}")

    def _cmd(self, *args):
        self._send(list(args))
        return self._parse()

    # ---------- 与 _RedisBackend 对应的方法 ----------
    def ping(self) -> bool:
        return self._cmd("PING") == "PONG"

    def get(self, key: str) -> Optional[str]:
        return self._cmd("GET", key)

    def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        args = ["SET", key, value]
        if ex:
            args += ["EX", str(ex)]
        return self._cmd(*args) == "OK"

    def incr(self, key: str) -> int:
        return int(self._cmd("INCR", key))

    def delete(self, *keys: str) -> int:
        return int(self._cmd("DELETE", *keys))

    def scan_iter(self, match: str = "*", count: int = 10) -> Iterator[str]:
        cursor = "0"
        while True:
            reply = self._cmd("SCAN", cursor, "MATCH", match, "COUNT", str(count))
            cursor, keys = reply[0], reply[1]
            for key in keys:
                yield key
            if str(cursor) == "0":      # cursor 归零 = 遍历结束
                return

    # ---------- Stream 命令（tasks.py 的 Redis 队列用；签名与 redis-py 一致） ----------

    @staticmethod
    def _fields_to_dict(flat) -> dict:
        """X 系列命令的 field-value 平铺列表 -> dict（redis-py 的返回形状）。"""
        flat = list(flat or [])
        return {flat[i]: flat[i + 1] for i in range(0, len(flat) - 1, 2)}

    def xadd(self, key: str, fields: dict, id: str = "*",
             maxlen: int = None, approximate: bool = True) -> str:
        args = ["XADD", key]
        if maxlen:
            # ~ 表示近似修剪（生产惯例；mini redis 直接精确裁到 maxlen）
            args += ["MAXLEN", "~" if approximate else "=", str(maxlen)]
        args.append(id)
        for field, value in fields.items():
            args += [str(field), str(value)]
        return self._cmd(*args)

    def xgroup_create(self, key: str, group: str, id: str = "$",
                      mkstream: bool = False):
        args = ["XGROUP", "CREATE", key, group, id]
        if mkstream:
            args.append("MKSTREAM")
        return self._cmd(*args)

    def xreadgroup(self, groupname: str, consumername: str, streams: dict,
                   count: int = None, block: int = None) -> list:
        """streams: {stream_name: ">"}。返回 [[name, [(id, {f: v}), ...]], ...]。

        注意：mini redis 的 XREADGROUP 是非阻塞的（立即返回空数组），
        所以这里的 block 只影响发出去的参数，不影响本地等待。
        """
        args = ["XREADGROUP", "GROUP", groupname, consumername]
        if count:
            args += ["COUNT", str(count)]
        if block is not None:
            args += ["BLOCK", str(block)]
        args.append("STREAMS")
        for name, entry_id in streams.items():
            args += [name, entry_id]
        reply = self._cmd(*args)
        if not reply:
            return []
        return [[name, [(entry_id, self._fields_to_dict(fields))
                        for entry_id, fields in entries]]
                for name, entries in reply]

    def xack(self, key: str, group: str, *ids: str) -> int:
        return int(self._cmd("XACK", key, group, *ids))

    def xautoclaim(self, key: str, groupname: str, consumername: str,
                   min_idle_time: int, start_id: str = "0-0",
                   count: int = None) -> list:
        """返回 [next_cursor, [(id, {f: v}), ...], [被清理的 id...]]（redis-py 的形状）。"""
        args = ["XAUTOCLAIM", key, groupname, consumername,
                str(min_idle_time), start_id]
        if count:
            args += ["COUNT", str(count)]
        reply = self._cmd(*args)
        next_cursor, entries = reply[0], reply[1]
        parsed = [(entry_id, self._fields_to_dict(fields))
                  for entry_id, fields in entries]
        deleted = reply[2] if len(reply) > 2 else []
        return [next_cursor, parsed, deleted]

    def xlen(self, key: str) -> int:
        return int(self._cmd("XLEN", key))

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None


def from_url(url: str, decode_responses: bool = True,
             socket_connect_timeout: float = 3, socket_timeout: float = 3) -> RespClient:
    """解析 redis://host:port/db 形式的 URL（与 redis.Redis.from_url 调用方式一致）。"""
    m = re.match(r"redis://(?P<host>[^:/]+)(?::(?P<port>\d+))?/(?P<db>\d+)?", url)
    if not m:
        raise ValueError(f"无法解析 REDIS_URL: {url}")
    return RespClient(host=m.group("host"),
                      port=int(m.group("port") or 6379),
                      db=int(m.group("db") or 0))
