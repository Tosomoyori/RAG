---
kind: logging_system
name: 日志系统：基于 print() 的无框架输出
category: logging_system
scope:
    - '**'
source_files:
    - rag_langchain.py
    - tools/mini_redis_resp.py
---

## 概述

本仓库**未引入任何日志框架**。代码中不存在 `logging`、`loguru`、`structlog`、`python-json-logger` 等第三方库的导入与初始化，也没有 `log/`、`logging/` 目录。所有可观测性输出均通过 Python 内置的 `print()` 直接写入 stdout。

## 关键文件与位置

- `rag_langchain.py`：RAG 主流程脚本，包含约 18 处 `print()` 调用，覆盖文档语种检测、索引完成、缓存命中/未命中、耗时统计、MRR/Hit Rate 指标、缓存后端名称等场景。
- `tools/mini_redis_resp.py`：内嵌 mini-redis 服务，使用 `print(..., flush=True)` 输出监听地址与服务停止信息。
- `verify_cache.py`、`verify_redis_backend.py`：验证脚本，仅透传或打印少量结果。
- `app.py`、`cache.py`：FastAPI 应用入口与缓存层，未发现任何日志相关代码（FastAPI 默认的 uvicorn 日志由外部进程管理）。

## 架构与约定

- **无集中式 logger 实例**：没有 `logging.getLogger(__name__)` 之类的 logger 对象，也没有配置文件（如 `logging.conf`、`pyproject.toml` 中的 logging section）。
- **无结构化字段**：日志行是纯文本 f-string，不包含 JSON 结构体、trace_id、request_id、level 等字段。
- **无级别控制**：全部使用 `print()`，无法按 DEBUG/INFO/WARNING/ERROR 分级过滤。
- **无 sink 路由**：输出始终到 stdout，没有文件、网络、远端收集器（如 ELK、CloudWatch）集成。
- **工具脚本中的 flush**：`tools/mini_redis_resp.py` 在关键启动/停止消息上显式传入 `flush=True`，以确保交互式终端下立即可见——这是仓库中唯一对 I/O 缓冲有意识处理的日志点。

## 约束与规则

- 仓库中**不存在**强制性的日志规范；当前实现仅为开发/调试阶段的原始输出。
- FastAPI 运行时的请求日志由 uvicorn 默认处理（stdout），业务侧未对其进行定制。
- 由于没有统一的 logger 抽象，新增日志点时无法保证格式一致性（现有 `print()` 风格也不统一：有的带 `[命中]` 前缀，有的直接输出键值）。