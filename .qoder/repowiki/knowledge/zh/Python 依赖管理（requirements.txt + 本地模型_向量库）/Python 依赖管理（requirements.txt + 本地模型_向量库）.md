---
kind: dependency_management
name: Python 依赖管理（requirements.txt + 本地模型/向量库）
category: dependency_management
scope:
    - '**'
source_files:
    - requirements.txt
    - .gitignore
    - bge-base-en-v1.5/.gitattributes
    - mmarco-mMiniLMv2-L12-H384-v1/.gitattributes
    - text2vec-base-chinese/.gitattributes
---

## 1. 使用的系统/方式

本项目使用 Python 生态中最基础的 `pip` 依赖管理，通过根目录的 `requirements.txt` 声明所有第三方包。没有使用 `pyproject.toml`、`poetry`、`Pipfile`、`conda` 或任何虚拟环境锁定工具（如 `pip-tools` / `pipenv lock`）。也没有 `vendor/` 目录或私有 PyPI 源配置。

对于运行时外部资源（嵌入模型、Chroma 向量数据库），项目采用**本地文件 + Git LFS** 的方式：
- `bge-base-en-v1.5/`、`mmarco-mMiniLMv2-L12-H384-v1/`、`text2vec-base-chinese/` 三个目录存放 HuggingFace/sentence-transformers 模型权重与 tokenizer；每个子目录都带有 `.gitattributes`，说明这些大文件通过 Git LFS 跟踪。
- `chroma_db/` 和 `chroma_db_backup_dup/` 是 ChromaDB 的本地 SQLite + bin 索引数据，作为持久化向量存储随仓库提交。

## 2. 关键文件

- `requirements.txt` — 唯一的依赖清单，共 19 行，分为两段注释块：
  - 第 1–14 行：RAG 核心依赖（LangChain 全家桶、sentence-transformers、chromadb、pymupdf、fastapi、uvicorn、python-dotenv）。
  - 第 16–18 行：缓存层依赖 `redis>=5.0`，注释明确“不装也能跑 —— 连不上 Redis 时自动降级为进程内内存缓存”。
- `__pycache__/` — pip 安装后生成的字节码缓存，非源码。
- `bge-base-en-v1.5/.gitattributes`、`mmarco-mMiniLMv2-L12-H384-v1/.gitattributes`、`text2vec-base-chinese/.gitattributes` — Git LFS 属性文件，用于大模型权重的版本化。
- `.gitignore` — 忽略 `__pycache__/` 等常见 Python 产物。

## 3. 架构与约定

- **单一来源**：所有 Python 依赖集中在 `requirements.txt`，无多环境变体（无 `requirements-dev.txt`、`requirements-prod.txt`）。
- **宽松版本约束**：大部分包使用 `>=x.y` 或无版本号（如 `langchain-community`、`langchain-huggingface`、`langchain-deepseek`、`langchain-core`、`sentence-transformers`、`chromadb`、`pymupdf`、`fastapi`、`uvicorn`、`python-dotribute`），仅 `langchain>=1.0`、`langchain-chroma>=1.0`、`redis>=5.0` 指定了最低版本。这意味着构建可重现性较弱，每次 `pip install -r requirements.txt` 可能拉取不同次新版本。
- **可选依赖模式**：Redis 被设计为可选依赖——代码在连接失败时回退到内存缓存（见 `requirements.txt` 注释及 `CACHE_BACKEND=auto` 行为），因此即使未安装 `redis` 包，服务仍可启动。
- **模型即数据**：嵌入模型不作为 Python 包发布，而是以二进制权重形式直接放入仓库并通过 Git LFS 管理，由 `sentence-transformers` / `transformers` 在运行时按路径加载。
- **向量库即数据**：ChromaDB 的 `chroma_db/` 目录作为持久化状态随仓库提交，而非通过 Docker 卷或外部服务部署。

## 4. 约定与约束

- 新增 Python 依赖应追加到 `requirements.txt`，并遵循现有注释分段风格（核心依赖与缓存依赖分开）。
- 新增大型二进制资源（模型、数据集）应放在独立目录并添加 `.gitattributes` 以启用 Git LFS。
- 对 `redis` 的使用需保持“可选”语义：当 Redis 不可用时，应用必须能自动降级到内存缓存，不得因缺少该包而崩溃。
- 当前仓库**没有**锁定文件（无 `requirements.lock` / `poetry.lock` / `Pipfile.lock`），也没有私有 PyPI 镜像或 `setup.py` / `pyproject.toml` 中的依赖元数据，因此不存在强制的版本一致性约束。
- 未见任何 CI 脚本、Makefile 或容器定义来验证依赖安装，依赖安装的正确性主要依赖本地手动测试。