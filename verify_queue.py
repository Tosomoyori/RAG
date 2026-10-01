"""
RAG 上传任务队列验证脚本（不加载任何模型，秒级跑完）

为什么单独写这个脚本？
  队列层的正确性（入队、状态流转、失败隔离、崩溃恢复）只取决于 tasks.py，
  和 embedding 模型无关。process_upload_file 默认 handler 要加载 1GB 模型，
  所以这里注入**假 handler**（返回固定的结果字典 / 抛异常 / 模拟耗时），
  把队列流转真实跑一遍：不需要模型、不需要 DeepSeek Key。

运行：
    python verify_queue.py                       # 默认（auto -> 跟随缓存层，通常降级 memory）
    QUEUE_BACKEND=memory python verify_queue.py   # 只测进程内队列
    QUEUE_BACKEND=redis  python verify_queue.py   # 真实 Redis Stream（需本机 Redis）

    没装 redis 包也能验证 Redis Stream 代码路径（协议是真的，客户端是极简版）：
    python tools/mini_redis_resp.py 6399                     # 终端 A
    QUEUE_BACKEND=redis REDIS_URL=redis://127.0.0.1:6399/0 \
        RESP_CLIENT_MODULE=tools.resp_client python verify_queue.py   # 终端 B

把结果同时写入 UTF-8 日志文件（避免 Windows 控制台/重定向的编码问题）：
    set VERIFY_LOG=verify_queue.log && python verify_queue.py

退出码 0 = 全部通过；非 0 = 有用例失败。
"""
import os
import sys
import time

# 允许在仓库内直接运行：确保能 import 同目录的 tasks.py / cache.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cache     # noqa: E402
import tasks     # noqa: E402

_log_file = None
if os.getenv("VERIFY_LOG"):
    _log_file = open(os.getenv("VERIFY_LOG"), "w", encoding="utf-8")

PASSED, FAILED = [], []
ALL_TASK_IDS = []          # 收集本脚本创建的任务，收尾检查 uploads/ 无残留
SLOW_SECONDS = 0.25        # 假 handler 模拟"解析+嵌入+入库"的耗时


def _emit(line: str) -> None:
    print(line)
    if _log_file is not None:
        _log_file.write(line + "\n")
        _log_file.flush()


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        _emit(f"  [PASS] {name}" + (f"  ({detail})" if detail else ""))
    else:
        FAILED.append(name)
        _emit(f"  [FAIL] {name}" + (f"  ({detail})" if detail else ""))


def section(title: str) -> None:
    _emit(f"\n=== {title} ===")


def submit(filename: str, content: str) -> str:
    task_id = tasks.submit_upload(filename, content.encode("utf-8"), ".md")
    ALL_TASK_IDS.append(task_id)
    return task_id


def staged_path(task_id: str) -> str:
    return os.path.join(tasks.UPLOAD_DIR, f"{task_id}.md")


# ---------- 假 handler：代替 process_upload_file（不加载模型） ----------
_handled = []              # 记录消费顺序，FIFO 用例要断言它


def fake_ok(msg):
    """模拟成功：确认 worker 拿到的消息足以定位暂存文件，返回结果字典。"""
    assert os.path.isfile(msg["saved_path"]), f"暂存文件不存在: {msg['saved_path']}"
    _handled.append(msg["filename"])
    return {"lang": "zh", "chunk_count": 3, "old_count": 1,
            "cache_invalidated": True,
            "message": f"fake 处理完成：{msg['filename']}"}


def fake_fail(msg):
    """模拟失败：比如 PDF 解析出来没有文本。"""
    raise ValueError("模拟解析失败：文件内容为空")


def fake_slow(msg):
    """模拟一本大 PDF 的解析+切块+嵌入+入库耗时。"""
    time.sleep(SLOW_SECONDS)
    return fake_ok(msg)


def main() -> int:
    backend = tasks.backend_name()
    extra = ""
    if os.getenv("RESP_CLIENT_MODULE"):
        extra = f"（用 {os.getenv('RESP_CLIENT_MODULE')} 顶替 redis 包）"
    _emit(f"队列后端：{backend}{extra}（QUEUE_BACKEND={tasks.QUEUE_BACKEND}，"
          f"缓存后端 {cache.backend_name()}）")

    # 用 redis 模式跑却降级到 memory 时，明确提示：这次没有真的验证 Redis Stream 路径
    if tasks.QUEUE_BACKEND == "redis" and backend != "redis":
        _emit("  [WARN] QUEUE_BACKEND=redis 但后端不是 redis：Redis Stream 路径未被验证！")
        FAILED.append("Redis 队列可用性")

    # ---------- 1. 入队与任务状态 ----------
    section("1. 入队与任务状态")
    tid = submit("测试文档.md", "你好，队列。")
    check("submit_upload 返回 task_id", bool(tid))
    task = tasks.get_task(tid)
    check("初始状态为 queued", bool(task) and task["status"] == tasks.QUEUED)
    check("状态里记录了文件名", bool(task) and task["filename"] == "测试文档.md")
    check("文件已暂存到 uploads/", os.path.isfile(staged_path(tid)))
    check("未知 task_id 查不到（/status 会 404）", tasks.get_task("no-such-id") is None)

    # ---------- 2. 消费成功路径 ----------
    section("2. 消费成功路径（状态流转 + 结果回写 + 文件清理）")
    t = tasks.run_worker(once=True, handler=fake_ok, block_seconds=2)
    check("任务状态变为 succeeded", bool(t) and t["status"] == tasks.SUCCEEDED)
    check("handler 的结果回写到任务状态",
          bool(t) and t["chunk_count"] == 3 and t["lang"] == "zh")
    check("状态里带回拼好的 message",
          bool(t) and "fake 处理完成" in t["message"])
    check("耗时字段有值", bool(t) and t.get("elapsed_ms", -1) >= 0)
    check("处理完暂存文件已删除", not os.path.exists(staged_path(tid)))
    again = tasks.run_worker(once=True, handler=fake_ok, block_seconds=1)
    check("空队列再消费返回 None（不抛异常）", again is None)

    # ---------- 3. 失败路径与毒丸隔离 ----------
    section("3. 失败路径与毒丸隔离")
    tid_f = submit("坏文件.md", "\ufeff")     # BOM：字节非空（入队不拦），处理时才失败
    t_f = tasks.run_worker(once=True, handler=fake_fail, block_seconds=2)
    check("handler 抛异常 -> 任务 failed", bool(t_f) and t_f["status"] == tasks.FAILED)
    check("错误信息写进状态（前端可读）",
          bool(t_f) and "模拟解析失败" in t_f["error"])
    check("失败也清理暂存文件", not os.path.exists(staged_path(tid_f)))
    # 毒丸不拖垮队列：失败任务确认后，下一条照常消费
    tid_n = submit("好文件.md", "正常内容")
    t_n = tasks.run_worker(once=True, handler=fake_ok, block_seconds=2)
    check("失败任务之后队列继续工作",
          bool(t_n) and t_n["status"] == tasks.SUCCEEDED)

    # ---------- 4. 多任务 FIFO ----------
    section("4. 多任务 FIFO 顺序")
    _handled.clear()
    ids = [submit(f"顺序{i}.md", f"内容{i}") for i in range(3)]
    for _ in ids:
        tasks.run_worker(once=True, handler=fake_ok, block_seconds=2)
    check("按入队顺序消费", _handled == [f"顺序{i}.md" for i in range(3)],
          f"实际顺序: {_handled}")

    # ---------- 5. 入队立即返回（上传不再阻塞） ----------
    section("5. 入队立即返回（README 第八节的第 1 个收益）")
    _handled.clear()
    t0 = time.perf_counter()
    slow_ids = [submit(f"大文件{i}.md", f"重活{i}") for i in range(3)]
    enqueue_s = time.perf_counter() - t0
    for _ in slow_ids:
        tasks.run_worker(once=True, handler=fake_slow, block_seconds=2)
    check("3 次入队显著快于串行处理", enqueue_s < 0.5,
          f"入队合计 {enqueue_s * 1000:.0f}ms；同步做这 3 个活需要 "
          f"~{3 * SLOW_SECONDS * 1000:.0f}ms")
    check("3 个慢任务最终全部完成",
          all(tasks.get_task(i)["status"] == tasks.SUCCEEDED for i in slow_ids))
    check("每个任务恰好被处理一次", len(_handled) == 3, f"处理了 {len(_handled)} 次")

    # ---------- 6. 任务状态 TTL ----------
    section("6. 任务状态 TTL（TASK_TTL 过期后轮询自然 404）")
    tasks._get_queue().save_task({"task_id": "ttl-probe", "status": tasks.QUEUED}, ttl=1)
    check("TTL 内可读", tasks.get_task("ttl-probe") is not None)
    time.sleep(1.3)
    check("TTL 过期后查不到", tasks.get_task("ttl-probe") is None)

    # ---------- 7. Redis Stream 专属用例 ----------
    if backend == "redis":
        section("7. Redis Stream：跨进程消费 / ACK / 崩溃恢复")
        # 7.1 独立实例消费：worker.py 是独立进程，它看到的是自己新建的后端实例
        tid_x = submit("跨进程.md", "另一个进程处理我")
        original = tasks._queue_instance
        tasks._queue_instance = tasks._RedisStreamQueue()   # 模拟 worker.py 进程
        try:
            t_x = tasks.run_worker(once=True, handler=fake_ok, block_seconds=2)
        finally:
            tasks._queue_instance = original
        check("独立实例消费到了别的实例入队的任务",
              bool(t_x) and t_x["task_id"] == tid_x
              and t_x["status"] == tasks.SUCCEEDED)
        check("处理结果对原实例可见（状态跨进程共享）",
              tasks.get_task(tid_x)["status"] == tasks.SUCCEEDED)

        # 7.2 已确认的消息不会被重复消费
        check("已 ACK 的消息不会被再次消费",
              tasks.run_worker(once=True, handler=fake_ok, block_seconds=1) is None)

        # 7.3 崩溃恢复：消息被取出（进入 PEL）后 worker 死掉，重启的 worker 认领重做
        tid_c = submit("崩溃恢复.md", "worker 挂了别丢我")
        q = tasks._get_queue()
        msg = q.next_message("crashed-worker", 1)   # 取走不确认：模拟处理中途死亡
        check("模拟崩溃：消息已被取出（留在 PEL）",
              bool(msg) and msg["task_id"] == tid_c)
        time.sleep(0.7)                             # 让消息 idle 超过认领阈值
        tasks.run_worker(once=True, handler=fake_ok, block_seconds=1,
                         reclaim_min_idle_ms=500)
        t_c = tasks.get_task(tid_c)
        check("重启 worker 通过 XAUTOCLAIM 认领并完成遗留任务",
              bool(t_c) and t_c["status"] == tasks.SUCCEEDED,
              f"status={t_c and t_c['status']}")
    else:
        section("7. Redis Stream 专属用例（当前后端 memory，跳过）")
        _emit("  跑 Redis Stream 路径：QUEUE_BACKEND=redis python verify_queue.py")

    # ---------- 8. 后端选择 ----------
    section("8. 后端选择")
    check("backend_name 合法", tasks.backend_name() in ("redis", "memory"))
    if tasks.QUEUE_BACKEND == "auto":
        expected = "redis" if cache.backend_name() == "redis" else "memory"
        check(f"auto 跟随缓存层（cache={cache.backend_name()} -> queue={expected}）",
              tasks.backend_name() == expected)

    # ---------- 收尾 ----------
    leftover = [staged_path(i) for i in ALL_TASK_IDS if os.path.exists(staged_path(i))]
    check("uploads/ 无本脚本残留的暂存文件", not leftover, f"残留: {leftover}")

    total = len(PASSED) + len(FAILED)
    _emit(f"\n{'=' * 46}")
    _emit(f"通过 {len(PASSED)}/{total}，失败 {len(FAILED)}")
    if FAILED:
        _emit("失败用例：")
        for name in FAILED:
            _emit(f"  - {name}")
    _emit("=" * 46)
    if _log_file is not None:
        _log_file.close()
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
