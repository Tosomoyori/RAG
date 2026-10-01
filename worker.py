"""
独立上传任务 worker —— 从 Redis Stream 消费"解析 + 嵌入 + 入库"任务。

什么时候需要它：
  - 默认配置（QUEUE_WORKER_IN_APP=1）下 web 进程里已有一个消费线程，
    单机演示**不需要**这个脚本；
  - 想把重活从 web 进程剥离（削峰的本意），或多开消费者水平扩展时：
      python worker.py                     # 终端 A（可开多个，消费组自动分流）
      set QUEUE_WORKER_IN_APP=0            # 可选：让 web 进程不再消费
      python app.py                        # 终端 B

崩溃恢复：worker 处理中途挂掉，消息留在 PEL；本进程重启后 XAUTOCLAIM
认领超时（默认 60 秒）未确认的消息重做。任务本身幂等（清库重入、
向量缓存兜底重复计算），重做是安全的。

用法：
    python worker.py                          # 默认连 .env 里的 REDIS_URL
    WORKER_NAME=gpu-1 python worker.py        # 指定 consumer 名（便于在 Redis 侧区分实例）
"""
import os

import tasks


def main() -> int:
    backend = tasks.backend_name()
    if backend != "redis":
        # 进程内队列只有本进程看得到，独立进程消费不到它——
        # 直接说清楚并退出，而不是空转一个永远等不到消息的循环。
        print(f"[worker] 当前队列后端是 {backend}（进程内队列），独立进程消费不到。")
        print("        需要 Redis Stream：请确认 Redis 已启动，且 QUEUE_BACKEND 为 auto/redis。")
        return 2

    consumer = os.getenv("WORKER_NAME") or f"worker-{os.getpid()}"
    print(f"[worker] 启动消费：{tasks.STREAM_KEY} 组 {tasks.GROUP_NAME} "
          f"consumer={consumer}（Ctrl+C 退出）")
    try:
        tasks.run_worker(consumer_name=consumer)
    except KeyboardInterrupt:
        print("\n[worker] 已退出。未确认的消息会留在 PEL，下次启动时自动认领重做。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
