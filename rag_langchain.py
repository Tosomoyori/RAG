"""
RAG —— LangChain 版核心管道（在无缓存版基础上加入缓存层）

与无缓存版的差异只有"缓存"这一块，管道本身逐行不变：
  无缓存版：问题 -> 召回20 -> 精排5 -> 调 DeepSeek      （每次都全跑一遍）
  缓存版：问题 -> 【问答缓存命中？】是 -> 直接返回
                              └ 否 -> 召回20【向量缓存】-> 精排5【分数缓存】
                                      -> 调 DeepSeek -> 写入问答缓存

三种缓存各自解决一件事：
  问答缓存：同一个问题不重复走完整链路（省 DeepSeek 调用、省 5~15 秒等待）
  向量缓存：同一段文本不重复做模型前向（上传重复内容、重复提问时收益明显）
  精排缓存：(问题,片段) 的 cross-encoder 分数不重复算（cross-encoder 是最慢的一环）

对应关系（早期手写版 main.py）：
  load_pdf() / 打开 .md           -> PyMuPDFLoader 或直接读文本
  split_by_chunk_size()           -> split_by_tokens()（按 token 切，两个语种口径一致）
  SentenceTransformer 嵌入         -> HuggingFaceEmbeddings（底层仍是 sentence-transformers）
  chromadb 客户端/集合/入库        -> langchain_chroma.Chroma + store.add_texts()
  retrieve()                     -> store.as_retriever(search_kwargs={"k": 20})
  rerank()                       -> make_retriever() 内用 HuggingFaceCrossEncoder.score()
  OpenAI(base_url=deepseek)       -> ChatDeepSeek
  手拼 prompt / 解析返回 content  -> PromptTemplate + StrOutputParser，整条链用 LCEL
"""
import os
import inspect
import math
import threading
import time
import warnings
import hashlib
import json
from pathlib import Path
from retrieval import expand_context, retrieve_candidates
from document_loader import load_sections, chunk_sections
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv

# langchain-community 已被官方标记为 sunset（正迁移到独立包），导入时会打印
# DeprecationWarning；当前版本功能不受影响，这里按消息内容屏蔽该噪音。
warnings.filterwarnings("ignore", message=".*langchain-community is being sunset.*")

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_deepseek import ChatDeepSeek
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_community.cross_encoders import HuggingFaceCrossEncoder

import cache

load_dotenv()

# ---------- 常量 ----------
# 按语种分模型与 collection。
#
# 关键约束：不同 embedding 模型的向量属于**不同的向量空间**，绝不能放进同一个
# collection。两者虽然都是 768 维，但跨模型算余弦相似度得到的是噪声——而且噪声值
# 可能高于真实匹配，检索会**静默出错而不报错**。所以按语种分开，保证
# "入库用的模型" 与 "检索用的模型" 始终是同一个。
LANG_MODELS = {
    "zh": "./text2vec-base-chinese",
    "en": "./bge-base-en-v1.5",
}

# 各语种模型的最大输入长度（token）。★ 必须显式写死，不能靠模型自带的默认值。
#
# 为什么：超长输入会被 sentence-transformers **静默截断**——不报错、不警告，
# 模型只是默默只读了块的前半段，你以为整块都进了向量。
# 实测 this project：`text2vec-base-chinese` 自带的 `sentence_bert_config.json`
# 里 max_seq_length=128，而按 300 字符切出来的中文块中位就有 **250 token**，
# 于是 **186/188 个块被截断**——这是真金白银的召回质量损失。
#
# 两个模型的 backbone 都是 BERT，`max_position_embeddings` 均为 512，
# 所以取 512 不会超出位置编码的范围。
#
# 改动这个值会改变所有向量的取值，所以它同时参与 embedding 缓存的 cache_tag
# （见 get_embedding_model）——否则旧向量会在 TTL 内继续命中。
LANG_MAX_SEQ = {"zh": 512, "en": 512}
# collection 名有硬性约束：3~512 字符，只能用 [a-zA-Z0-9._-] 且首尾必须是字母数字。
# 所以不能用 "zh" / "en"（2 个字符，Chroma 会抛 InvalidArgumentError）。
LANG_COLLECTIONS = {"zh": "rag_zh", "en": "rag_en"}
DEFAULT_LANG = "zh"

# bge-*-v1.5 官方建议：检索时给 **query** 加指令，passage 不加。
# 官方 README 称 v1.5 不加指令只有"轻微下降"（slight degradation），
# 所以做成环境变量可关，方便自己 A/B 对比。
LANG_QUERY_PREFIX = {
    "en": os.getenv("BGE_QUERY_PREFIX",
                    "Represent this sentence for searching relevant passages: "),
}

RERANK_MODEL = "./mmarco-mMiniLMv2-L12-H384-v1"
# 用绝对路径而不是 "./chroma_db"：chromadb 的 SharedSystemClient 是按
# persist_directory 的**字符串**做进程内实例注册的，同一个目录用不同写法
# （相对 vs 绝对、不同 CWD）会被当成两个库，各自开一份 SQLite 连接和 HNSW 索引，
# 叠在同一个目录上——轻则设置冲突报错，重则数据不一致。
CHROMA_DB_PATH = str(Path(os.getenv("RAG_INDEX_DIR", str(
    Path(__file__).resolve().parent / "chroma_db"))).expanduser().resolve())


# 默认文档：本目录下的 doc.pdf（注意不是 ".doc.pdf"，那个前导点是笔误，
# 会去找一个隐藏文件，直接回车就会报 "is not a valid file or url"）
DEFAULT_SOURCE = "doc.pdf"

# 检索参数提到模块级：它们要参与缓存 key 计算（改参数不应命中旧口径的答案）
RETRIEVE_K = 20     # 向量召回条数
RERANK_TOP_N = 5    # 精排后保留条数

RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "language")
CONTEXT_NEIGHBORS = int(os.getenv("CONTEXT_NEIGHBORS", "1"))
CONTEXT_MAX_CHUNKS = int(os.getenv("CONTEXT_MAX_CHUNKS", "10"))
CONTEXT_MAX_TOKENS = int(os.getenv("CONTEXT_MAX_TOKENS", "2560"))
if RETRIEVAL_MODE not in ("vector", "hybrid", "language"):
    raise ValueError("RETRIEVAL_MODE must be vector, hybrid or language")
if CONTEXT_NEIGHBORS < 0 or CONTEXT_MAX_CHUNKS < 1 or CONTEXT_MAX_TOKENS < 1:
    raise ValueError("Invalid context expansion budgets")

# 切块按 token 计（见 split_by_tokens）。
# 256 是"模型上限 512 的一半"——留足余量，避免将来换模型或改配置时又踩到静默截断。
# 40/256 ≈ 16% 重叠。两个值都可用环境变量覆盖，方便做 A/B 对比。
CHUNK_TOKENS = int(os.getenv("CHUNK_TOKENS", 256))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", 40))

# 语义缓存开关（默认关闭，见 SemanticCache 注释）
SEMANTIC_CACHE_ENABLED = os.getenv("SEMANTIC_CACHE", "0") == "1"
SEMANTIC_THRESHOLD = float(os.getenv("SEMANTIC_THRESHOLD", "0.95"))


# ---------- 0. 语种判断（决定用哪个模型、进哪个 collection） ----------
def detect_lang(text: str) -> str:
    """判断文本语种，返回 "zh" 或 "en"（本项目只可能有这两类文档/问题）。

    判据只有一个：**汉字占非空白字符的比例 >= 5%**。
    不看词频、不查词典、不引依赖——中英文在字符层面就分得开，没必要上模型。

    为什么阈值取 5% 这么低：
      - 中文文档里混着大量不翻译的英文（ReAct / LLM / ICLR / 作者名），
        汉字占比依然远高于 5%
      - 英文文档里偶尔出现汉字（作者名、被引用的中文术语）占比远低于 5%
      实测 5%~30% 之间取任何值都能分开这两类，取 5% 是给中文一侧留最大余量。

    已知边界（可接受）：英文句式里夹少量中文词，例如
    "the paper says 推理 and 行动 are interleaved" 汉字占比 0.121 → 判为 zh。
    这类混写在真实提问里很少见，且用户能从响应里的 lang 字段看出路由结果。

    实测：中文译本整篇 CJK 占比 78%，逐块 187/188 判为 zh；
    13 条真实问题回归 12/13 符合预期（唯一例外的就是上面这类混写）。
    """
    total = sum(1 for ch in text if not ch.isspace())
    if not total:
        return DEFAULT_LANG
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    return "zh" if cjk / total >= 0.05 else "en"


# ---------- 1. 嵌入模型（原 embed_chunk）+ 向量缓存 ----------

def _embed_documents_cached(raw_embed_documents, texts: List[str],
                            model_tag: str = "") -> List[List[float]]:
    """批量嵌入 + 向量缓存：命中的文本不送进模型，只算未命中的。

    这是缓存与"模型单例"最大的区别：模型单例保证模型只加载一次，
    但每次请求的文本仍然要过一遍前向计算；向量缓存则是连计算都省了。

    model_tag 标识用的是哪个模型——必须区分，否则两个语种的模型会互相覆盖向量。
    """
    if not texts:
        return []

    cached = cache.get_embeddings(texts, model_tag)         # {文本hash: 向量}
    miss_texts = [t for t in texts if cache.embedding_key(t) not in cached]

    fresh: Dict[str, List[float]] = {}
    if miss_texts:
        vectors = raw_embed_documents(miss_texts)
        fresh = {cache.embedding_key(t): v for t, v in zip(miss_texts, vectors)}
        cache.set_embeddings(list(zip(miss_texts, vectors)), model_tag)

    # 按原始顺序拼回：缓存命中 + 新计算
    merged = {**cached, **fresh}
    return [merged[cache.embedding_key(t)] for t in texts]


def _embed_query_cached(raw_embed_query, text: str,
                        model_tag: str = "") -> List[float]:
    """单条查询向量 + 缓存（同一问题重复提问时直接复用）。"""
    key = cache.embedding_key(text)
    cached = cache.get_embeddings([text], model_tag).get(key)
    if cached is not None:
        return cached
    vector = raw_embed_query(text)
    cache.set_embeddings([(text, vector)], model_tag)
    return vector


class CachedHuggingFaceEmbeddings(HuggingFaceEmbeddings):
    """带向量缓存的 HuggingFaceEmbeddings。

    为什么用子类覆写，而不是给实例贴方法（原来的写法）？
    langchain-huggingface 1.x 起 HuggingFaceEmbeddings 改成了 pydantic BaseModel，
    `embeddings.embed_documents = xxx` 会被 pydantic 的 __setattr__ 拦下并抛
    ValueError: object has no field "embed_documents"。
    改成子类覆写后，Chroma 与 retriever 拿到的仍然是同一个 embedding_function，
    缓存照常生效，也不再依赖 monkey patch 这种脆弱写法。

    两个新字段（必须是 pydantic 字段，普通实例属性会被 pydantic 拦下）：
      lang          —— 语种，作为向量缓存的 model_tag，避免两个模型互相覆盖
      query_prefix  —— 只加在 query 侧的前缀（bge 系列的检索指令）
    """

    lang: str = ""
    cache_tag: str = ""
    query_prefix: str = ""
    max_seq_length: int = 0          # 0 = 不改，沿用模型自带值

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.max_seq_length:
            # 只能"构造后再设"：sentence-transformers 5.x 起，
            # SentenceTransformer.__init__ 不再接受 max_seq_length 参数
            # （传 model_kwargs={"max_seq_length": ...} 会直接 TypeError）。
            # 它现在是类上的一个 property，setter 会把值下发给内部的 Transformer 模块。
            self._client.max_seq_length = self.max_seq_length

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return _embed_documents_cached(super().embed_documents, texts, self.cache_tag)

    def embed_query(self, text: str) -> List[float]:
        # 前缀只加在查询侧，passage 侧不加（bge 官方要求）
        if self.query_prefix:
            text = self.query_prefix + text
        return _embed_query_cached(super().embed_query, text, self.cache_tag)


_embeddings_by_lang: Dict[str, CachedHuggingFaceEmbeddings] = {}
_embeddings_lock = threading.Lock()


def get_embedding_model(lang: str) -> CachedHuggingFaceEmbeddings:
    """按语种懒加载 embedding 模型。

    不在 import 时构造：那样两个模型会在启动时同时占内存，而多数请求只用到其中一种。
    （reranker 早就用了同样的懒加载思路，见 _get_cross_encoder。）

    加锁是必要的：FastAPI 把同步的 /ask 丢进线程池，两个并发的首次请求会
    同时走到这里，各自加载一份 400MB 的模型，峰值内存翻倍、还白扔一份。
    cache._get_backend 用的是同样的双检锁写法，保持一致。
    """
    if lang not in _embeddings_by_lang:                 # 无锁快路径
        with _embeddings_lock:
            if lang not in _embeddings_by_lang:         # 双检
                _embeddings_by_lang[lang] = CachedHuggingFaceEmbeddings(
                    model_name=LANG_MODELS[lang],
                    # 显式指定最大输入长度：模型自带默认值可能远小于我们的块长度，
                    # 而超长会被静默截断（见 LANG_MAX_SEQ 的注释）。
                    max_seq_length=LANG_MAX_SEQ[lang],
                    encode_kwargs={"normalize_embeddings": True},  # 对应 normalize_embeddings=True
                    lang=lang,
                    # 缓存标签要覆盖**所有会改变向量取值的因素**：语种、模型、最大长度。
                    # 只写语种的话，换模型或改 max_seq_length 之后，旧向量会在
                    # 24h TTL 内继续命中并被写进新库——那正是这个标签要防的事。
                    cache_tag=f"{lang}|{LANG_MODELS[lang]}|seq{LANG_MAX_SEQ[lang]}",
                    query_prefix=LANG_QUERY_PREFIX.get(lang, ""),
                )
    return _embeddings_by_lang[lang]


_chroma_client = None
_chroma_client_lock = threading.Lock()


def _get_chroma_client():
    """两个语种的 collection 共享同一个 PersistentClient。

    同一目录下多开客户端没有意义，还容易踩并发/句柄问题；
    共享之后 Chroma(client=..., collection_name=...) 就能拿到同一份底层数据。

    ★ 注意：不要对共享出去的 client 调 close()。chromadb 的 SharedSystemClient
      按引用计数管理，close() 会把计数减到 0 并停掉底层 system，
      连带作废其它持有者的所有句柄。
    """
    global _chroma_client
    if _chroma_client is None:
        with _chroma_client_lock:
            if _chroma_client is None:
                import chromadb
                _chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    return _chroma_client


def _chroma_persist_kwargs() -> dict:
    """兼容 langchain-chroma 新旧版本，并让两个 collection 共享客户端。

    新版（>=1.0）支持 client= 参数——实测本项目的 langchain-chroma 1.1.0 支持；
    旧版没有该参数，退回 persist_directory= / path= 的写法。"""
    params = inspect.signature(Chroma.__init__).parameters
    if "client" in params:
        return {"client": _get_chroma_client()}
    key = "path" if "path" in params else "persist_directory"
    return {key: CHROMA_DB_PATH}


# ---------- 2. 文档加载与切块 ----------
def load_raw_text(path: str) -> str:
    """读取支持的文档格式，返回按阅读顺序拼接的纯文本。"""
    # 先把"文件不存在"挑出来给人话提示：PyMuPDFLoader 对不存在的路径只会抛
    # ValueError: File path xxx is not a valid file or url，看不出是路径写错了还是格式不支持。
    if not path.lower().startswith(("http://", "https://")) and not os.path.isfile(path):
        here = os.path.dirname(os.path.abspath(__file__))
        raise FileNotFoundError(
            f"找不到文档：{path!r}（当前目录：{os.getcwd()}）\n"
            f"  - 若用默认值，请确认 {os.path.join(here, DEFAULT_SOURCE)} 存在；\n"
            f"  - 也可以直接输入绝对路径，例如 {os.path.join(here, 'doc.pdf')}"
        )
    return "\n\n".join(section.text for section in load_sections(path))


_tokenizers: Dict[str, Any] = {}
_tokenizers_lock = threading.Lock()


def _get_tokenizer(lang: str):
    """按语种懒加载 tokenizer（只读词表，不加载模型权重，很轻）。"""
    if lang not in _tokenizers:
        with _tokenizers_lock:
            if lang not in _tokenizers:
                from transformers import AutoTokenizer
                _tokenizers[lang] = AutoTokenizer.from_pretrained(LANG_MODELS[lang])
    return _tokenizers[lang]


def split_by_tokens(text: str, lang: str = DEFAULT_LANG,
                    chunk_size: int = CHUNK_TOKENS,
                    overlap: int = CHUNK_OVERLAP_TOKENS) -> List[str]:
    """按 **token** 切块，tokenizer 用该语种 embedding 模型自己的那一个。

    为什么从"按字符"改成"按 token"：
      同样 300 个字符，中文约 250 token、英文约 52 token——差近 5 倍。
      拿同一个字符数切两种语言，"一个块"在中英两侧承载的信息量完全不可比，
      英文块会薄得离谱（检索精度和送进 LLM 的上下文都受影响）。
      按 token 切，"块"在两个库里才是同一量级的东西。

    为什么用 offset 对齐、而不是 decode 回文本：
      实测 tok.decode(ids) **不能**还原原文——中文会被规整、英文会丢字符。
      所以这里只用 tokenizer 算 token 的字符边界，再按字符位置切**原文**，
      保证每个块都是原文的逐字子串（评测脚本依赖这个性质做逐字节比对）。

    为什么 chunk_size 默认 256 而不是模型上限 512：
      取一半留足余量；块本身不含特殊 token，但有余地就不会在
      换模型/改配置时再次撞上静默截断。
    """
    if not text:
        return []
    offsets = _get_tokenizer(lang)(
        text, return_offsets_mapping=True, add_special_tokens=False)["offset_mapping"]
    n = len(offsets)
    if n == 0:
        return []
    step = max(chunk_size - overlap, 1)      # 防止 overlap >= chunk_size 时原地打转
    chunks, start = [], 0
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[offsets[start][0]:offsets[end - 1][1]])
        if end >= n:
            break
        start += step
    return chunks


# ---------- 3. 向量库（原 chromadb 客户端/集合/入库/加载全部被 Chroma 封装） ----------
def load_store(lang: str = DEFAULT_LANG) -> Chroma:
    """打开（不存在则创建）指定语种的持久化向量库。

    每个语种一个 collection、一个 embedding 模型——见 LANG_MODELS 上方的约束说明。
    """
    return Chroma(
        collection_name=LANG_COLLECTIONS[lang],
        embedding_function=get_embedding_model(lang),
        **_chroma_persist_kwargs(),
    )


def build_index(source_file: str, lang: Optional[str] = None,
                force: bool = False) -> Chroma:
    """重建或追加索引：切块 -> 嵌入 -> 入库。lang 不给则按文档语种自动判断。"""
    sections = load_sections(source_file)
    text = "\n\n".join(section.text for section in sections)
    if lang is None:
        lang = detect_lang(text)
        print(f"检测到文档语种：{lang}（模型 {LANG_MODELS[lang]}）")
    store = load_store(lang)
    if force:
        # 清空已有块，而不是 delete_collection()。
        # delete_collection() 会让**所有**已存在的 Chroma 实例句柄失效（它们共享
        # 同一个 client 和 collection UUID），之后 app 里缓存的 _stores /
        # _retrievers / _chains 会抛 NotFoundError，且无法自动恢复。
        # 删块能达到同样的"重建"效果，且不碰 collection 本身。
        # （注意：若换成不同维度的模型，删块改不了 collection 的维度——
        #   那种情况需要停服后手动删掉 chroma_db/ 再重建，本来也要重启进程。）
        try:
            old_ids = store.get()["ids"]
            if old_ids:
                store.delete(ids=old_ids)
        except Exception:
            pass  # 集合不存在时忽略
    chunks, metadata = chunk_sections(sections, lang, split_by_tokens,
                                      os.path.basename(source_file))
    if chunks:
        store.add_texts(  # 一次批量嵌入 + 入库；嵌入过程自动走向量缓存
            chunks,
            metadatas=metadata,
        )
    print(f"已索引 {len(chunks)} 个文本块 -> {CHROMA_DB_PATH}[{LANG_COLLECTIONS[lang]}]")
    return store


def get_all_chunks_in_order(store: Chroma) -> List[str]:
    """按 metadata['index'] 还原入库顺序（对应原 get_all_chunks_from_existed_collection）。"""
    data = store.get(include=["documents", "metadatas"])
    pairs = sorted(zip(data["metadatas"], data["documents"]),
                   key=lambda md_doc: md_doc[0].get("index", 0))
    return [doc for _, doc in pairs]


# ---------- 4 + 5. 检索 + 重排（原 retrieve() + rerank()）+ 精排分数缓存 ----------
_cross_encoder = None


def _get_cross_encoder():
    """懒加载 cross-encoder（模型 ~470MB，避免模块导入/建库时白白加载）。"""
    global _cross_encoder
    if _cross_encoder is None:
        _cross_encoder = HuggingFaceCrossEncoder(model_name=RERANK_MODEL)
    return _cross_encoder


def rerank_cached(query: str, docs: List[str]) -> List[float]:
    """cross-encoder 打分 + 分数缓存。

    为什么这里特别值得缓存？cross-encoder 要把 (问题, 片段) 成对送进模型，
    召回 20 条就要前向 20 次，是整个链路里最慢的一步（本地 CPU 上百毫秒级）。
    缓存键是 (问题, 片段) 的内容哈希，所以同一问题换文档、同一文档换问题都能复用。
    """
    if not docs:
        return []

    hitting = cache.get_rerank_scores(query, docs)          # {下标: 分数}
    miss_idx = [i for i in range(len(docs)) if i not in hitting]

    fresh: Dict[int, float] = {}
    if miss_idx:
        pairs = [(query, docs[i]) for i in miss_idx]
        scores = [float(s) for s in _get_cross_encoder().score(pairs)]
        fresh = dict(zip(miss_idx, scores))
        cache.set_rerank_scores(query, [docs[i] for i in miss_idx], scores)

    merged = {**hitting, **fresh}
    return [merged[i] for i in range(len(docs))]


def retrieval_mode(lang: str) -> str:
    if RETRIEVAL_MODE == "language":
        return "hybrid" if lang == "zh" else "vector"
    return RETRIEVAL_MODE


def make_retriever(store: Chroma, k: int = RETRIEVE_K, top_n: int = RERANK_TOP_N,
                   lang: Optional[str] = None):
    """Retrieve and rerank candidates, with configurable bounded context expansion."""
    def _retrieve_and_rerank(query: str):
        language = lang or detect_lang(query)
        docs = retrieve_candidates(store, query, k, retrieval_mode(language))
        scores = rerank_cached(query, [d.page_content for d in docs])
        ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
        seeds = [d for d, _ in ranked[:top_n]]
        if CONTEXT_NEIGHBORS:
            return expand_context(store, seeds, _get_tokenizer(language),
                                  radius=CONTEXT_NEIGHBORS, max_chunks=CONTEXT_MAX_CHUNKS,
                                  max_tokens=CONTEXT_MAX_TOKENS)
        return seeds

    return RunnableLambda(_retrieve_and_rerank)


# ---------- 6. 生成（原 generate()） ----------
PROMPT_VERSION = os.getenv("RAG_PROMPT_VERSION", "legacy")
PROMPT_TEMPLATES = json.loads(Path(__file__).with_name("prompts.json").read_text(encoding="utf-8"))
if PROMPT_VERSION not in PROMPT_TEMPLATES:
    raise ValueError(f"Unsupported RAG_PROMPT_VERSION: {PROMPT_VERSION}")
prompt = PromptTemplate.from_template(PROMPT_TEMPLATES[PROMPT_VERSION])
PROMPT_FINGERPRINT = hashlib.sha256(prompt.template.encode("utf-8")).hexdigest()[:16]
llm = ChatDeepSeek(model="deepseek-chat", temperature=0.7)   # 原 OpenAI(base_url=...)


def format_docs(docs) -> str:
    return "\n\n".join(d.page_content for d in docs)


def make_chain(retriever):
    """LCEL 一条链：检索 -> 拼上下文 -> prompt -> DeepSeek -> 纯文本。

    输入两种形态，都返回模型答案字符串：
      - 传字符串：链内自己召回（等价原来的写法，适合一次性调用）；
      - 传 {"question", "context"}：**跳过召回**，直接用给好的 context。

    为什么要支持第二种？query() 需要先把召回结果拿出来做向量缓存/精排缓存，
    再调模型。如果这里无条件再召回一次，就等于：
      1. 白跑一遍检索 + 精排（慢一倍）；
      2. 更糟的是——传进去的是 {"question","context"} 字典，retriever 会把这个
         字典当成 query 去 embed_query，直接抛
         AttributeError: 'dict' object has no attribute 'encode'。
    所以召回改成"按需触发"：给了 context 就不再召回。
    """
    def _context_and_question(payload):
        if isinstance(payload, dict):
            question, context = payload["question"], payload["context"]
        else:
            question = payload
            context = format_docs(retriever.invoke(question))
        return {"question": question, "context": context,
                "answer_language": "English" if detect_lang(question) == "en" else "简体中文"}

    return (
        RunnableLambda(_context_and_question)
        | prompt
        | llm
        | StrOutputParser()
    )


# ============================================================
# 语义缓存（选配，默认关闭）：把"问法不同但意思相同"的问题也救回来
# ============================================================
class SemanticCache:
    """用嵌入向量做近似问题匹配。

    精确缓存（question 原文当 key）能挡住"重复问同一句话"，但挡不住
    「这篇论文的主要贡献是什么」和「论文主要贡献有哪些」这种换了个说法的问法。
    语义缓存就是把历史问题的向量存下来，新问题先算向量、比余弦相似度，
    超过阈值就复用旧答案。

    为什么默认关闭？
      1. 阈值调高（0.95+）收益有限，调低（0.85）会误命中、答非所问，
         而 RAG 场景下"答错"比"慢一点"严重得多；
      2. 近似匹配天然有误判风险——这正是"缓存丢了系统应该变慢，
         而不是变错"要警惕的地方：缓存可以加速，但绝不能改变正确答案。

    打开方式：.env 里设 SEMANTIC_CACHE=1、SEMANTIC_THRESHOLD=0.95。
    这里用手写向量比较，不引入 Redis 向量检索，保持依赖最小。
    """

    def __init__(self, max_size: int = 256, threshold: float = SEMANTIC_THRESHOLD):
        self.max_size = max_size
        self.threshold = threshold
        self._entries: "OrderedDict[str, Tuple[List[float], Dict[str, Any]]]" = OrderedDict()

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    def lookup(self, vector: List[float]) -> Optional[Tuple[Dict[str, Any], float]]:
        best, best_score = None, 0.0
        for _, (vec, payload) in self._entries.items():
            score = self._cosine(vector, vec)
            if score > best_score:
                best, best_score = payload, score
        if best is not None and best_score >= self.threshold:
            return best, best_score
        return None

    def store(self, question: str, vector: List[float], payload: Dict[str, Any]) -> None:
        self._entries[question] = (vector, payload)
        self._entries.move_to_end(question)
        while len(self._entries) > self.max_size:
            self._entries.popitem(last=False)      # 简单 LRU

    def clear(self) -> None:
        self._entries.clear()


_semantic_caches: Dict[str, SemanticCache] = {}


def get_semantic_cache(lang: str) -> SemanticCache:
    """语义缓存**按语种各一份**。

    不能共用：它比较的是嵌入向量的余弦相似度，而两个语种用的是两个不同的模型，
    向量分属不同的空间，混在一起比对得到的只是噪声——与"把两个模型的向量塞进
    同一个 collection"是同一种错误。
    """
    if lang not in _semantic_caches:
        _semantic_caches[lang] = SemanticCache()
    return _semantic_caches[lang]


# ---------- 7. 带缓存的问答入口（新增的核心函数） ----------
def query(question: str, retriever, chain,
          use_cache: bool = True,
          k: int = RETRIEVE_K, top_n: int = RERANK_TOP_N,
          lang: str = DEFAULT_LANG) -> Dict[str, Any]:
    """一次问答的完整入口：先查缓存，未命中再走 RAG 链路并回写缓存。

    lang 只用于语义缓存（要用对应语种的模型算问题向量）；检索与生成走注入的
    retriever / chain，本身与语种无关。

    返回 dict（接口/前端直接消费）：
      answer / sources / cache_hit / cache_type / elapsed_ms
    """
    started = time.perf_counter()
    index_namespace = hashlib.sha256(CHROMA_DB_PATH.encode("utf-8")).hexdigest()[:16]
    cache_lang = f"{lang}|index:{index_namespace}|prompt:{PROMPT_FINGERPRINT}"
    if RETRIEVAL_MODE != "vector" or CONTEXT_NEIGHBORS:
        cache_lang = (f"{cache_lang}|retrieval-v1|{RETRIEVAL_MODE}|{CONTEXT_NEIGHBORS}"
                      f"|{CONTEXT_MAX_CHUNKS}|{CONTEXT_MAX_TOKENS}")

    if use_cache:
        # ① 精确缓存：问题原文一致
        exact = cache.get_answer(question, top_n, k, cache_lang)
        if exact is not None:
            return {"answer": exact["answer"], "sources": exact["sources"],
                    "cache_hit": True, "cache_type": "exact",
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}

        # ② 语义缓存（选配）：问题不同但语义相近
        if SEMANTIC_CACHE_ENABLED:
            # 走 embed_query 而不是裸的 _embed_query_cached：它已经带缓存，
            # 且会按语种套上 bge 的查询前缀（旧代码这里少传了参数，一开就抛 TypeError）
            vector = get_embedding_model(lang).embed_query(question)
            similar = get_semantic_cache(lang).lookup(vector)
            if similar is not None:
                payload, score = similar
                return {"answer": payload["answer"], "sources": payload["sources"],
                        "cache_hit": True, "cache_type": f"semantic({score:.3f})",
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}

    # ③ 真实链路：这里召回一次，然后把结果连同问题一起交给 chain。
    #    注意必须传 dict —— chain 收到 context 后就不再自己召回，
    #    否则会重复检索，并且把整个 dict 当 query 送进 embedding 而报错。
    sources = retriever.invoke(question)
    answer = chain.invoke({"question": question, "context": format_docs(sources)})
    source_texts = [d.page_content for d in sources]

    if use_cache:
        cache.set_answer(question, top_n, k, answer, source_texts, cache_lang)
        if SEMANTIC_CACHE_ENABLED:
            get_semantic_cache(lang).store(
                question,
                get_embedding_model(lang).embed_query(question),
                {"answer": answer, "sources": source_texts})

    return {"answer": answer, "sources": source_texts,
            "cache_hit": False, "cache_type": "miss",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}


def invalidate_caches() -> int:
    """文档变更后调用：问答/精排缓存全清 + 语义缓存清空 + 版本号提升。

    语义缓存按语种各一份，这里全部清掉。多清是安全的（只是下次要重算），
    少清才会让用户拿到基于旧文档的答案。
    """
    for sc in _semantic_caches.values():
        sc.clear()
    deleted = cache.clear(["qa", "rerank"])
    cache.bump_version()
    return deleted


# ---------- 8. 评测（Hit Rate / MRR）----------
def evaluate_retrieval(questions, true_indices, chunks, reranked_results):
    """
    questions: List[str]
    true_indices: List[int]  每个问题对应的标准答案块索引
    chunks: List[str]        按入库顺序的全文块
    reranked_results: List[List[str]]  已重排序的结果，和 questions 一一对应
    返回 (hit_rate, mrr)
    """
    # 提前挡住"标注与文档不是同一份"这个最常发生、又最难看懂的错误：
    # true_indices 是针对**某一份特定文档**标注的块号，换了文档就不再指向标准答案。
    # 越界时 chunks[true_idx] 会抛 IndexError，信息很含糊，这里给出能看懂的原因。
    if true_indices and max(true_indices) >= len(chunks):
        raise ValueError(
            f"true_indices 最大值 {max(true_indices)} 超出当前文档的块数 {len(chunks)}："
            f"这批标注不是针对当前文档的，换文档后需要重新出题并标注"
            f"（见 __main__ 里的说明）。")

    hits = 0
    reciprocal_ranks = []

    for q, true_idx, reranked_chunks in zip(questions, true_indices, reranked_results):
        true_chunk = chunks[true_idx]
        found = False
        rank = 0

        for i, chunk in enumerate(reranked_chunks, start=1):
            if chunk == true_chunk:
                found = True
                rank = i
                break

        if found:
            hits += 1
            reciprocal_ranks.append(1 / rank)
            print(f"[命中] {q} -> 排名第 {rank}")
        else:
            reciprocal_ranks.append(0)
            print(f"[未命中] {q}")

    hit_rate = hits / len(questions) if questions else 0
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0
    return hit_rate, mrr


def save_chunks_to_file(chunks: List[str], output_file: str) -> None:
    """把文本块和索引保存到 Markdown 文件，方便人工标注标准答案。

    output_file 不给默认值是有意的：分语种后必须写明是哪一个库的预览
    （`chunks_preview_zh.md` / `chunks_preview_en.md`），留个通用默认值
    容易让人不小心把两个库的预览写到同一个文件里互相覆盖。
    """
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# 文本块预览\n\n")
        for idx, chunk in enumerate(chunks):
            f.write(f"## Chunk {idx}\n\n")
            f.write(chunk)
            f.write("\n\n---\n\n")
    print(f"已保存到 {output_file}")


# ============================================================
# 离线主流程
# ============================================================
if __name__ == "__main__":
    rebuild = input("是否重新构建向量库？(y/N): ").strip().lower() == "y"
    source = input(f"文档路径（默认 {DEFAULT_SOURCE}）: ").strip() or DEFAULT_SOURCE

    # 语种决定用哪个模型、进哪个 collection（见 LANG_MODELS 上方的约束说明）
    lang = detect_lang(load_raw_text(source))
    print(f"文档语种：{lang}（模型 {LANG_MODELS[lang]}，collection {LANG_COLLECTIONS[lang]}）")

    store = build_index(source, lang=lang, force=rebuild) if rebuild else load_store(lang)
    chunks = get_all_chunks_in_order(store)
    print(f"向量库中共 {len(chunks)} 个文本块。")
    save_chunks_to_file(chunks, f"./chunks_preview_{lang}.md")

    # 测试问题与标准答案索引：与旧版完全一致，可直接对比 Hit Rate / MRR
    #
    # ⚠️ 下面这套题与 true_indices 是**针对那份中文毕业论文**标注的
    #    （块号对应 300/50 切块下的具体位置）。换成别的文档后，这 12 个下标
    #    指向的就不是"标准答案"了，跑出来的 Hit Rate / MRR 没有意义。
    #    注意：不会"静默给错数字"——max(true_indices)=226 超出当前文档的块数时，
    #    evaluate_retrieval 会直接抛 ValueError（那里有明确的越界提示）。
    #    换文档时请重新出题并标注。
    test_questions = [
        "该系统在硬件层面由哪两个主要节点构成？它们分别负责哪些具体功能？",
        "系统依据什么算法和置信度区间来区分家庭成员与陌生人？具体划分标准是什么？",
        "火焰检测模块采用了哪两种手段来抑制误报？其置信度阈值设为多少？",
        "烟雾传感器的报警触发条件是什么？该阈值是如何通过实验确定的？",
        "温度传感器的报警阈值是多少？该值的设定依据是什么？",
        "ESP32-CAM 模块最终选用了哪种图像分辨率？为何不选用更高或更低的分辨率？",
        "系统对人脸图像、火焰检测图像和传感器数据分别设定了怎样的上传间隔？这样设计有何考虑？",
        "在对已知人员的人脸识别测试中，是否出现过将本人误判为陌生人的情况？统计结果如何？",
        "在抗干扰测试中，系统面对阳光和台灯直射时的表现如何？是否产生了误报？",
        "系统后端数据库包含哪些数据表？请分别说明其存储内容。",
        "作者对于任课老师和同学的情感是什么样的",
        "人脸识别误报率是多少？",
    ]
    true_indices = [1, 120, 153, 144, 144, 133, 173, 177, 181, 161, 226, 179]

    # 第一次跑：精排分数全部未命中（真实计算）；再跑同一批就是缓存命中
    retriever = make_retriever(store)
    print(f"\n缓存后端：{cache.backend_name()}")

    t0 = time.perf_counter()
    reranked_results = [
        [d.page_content for d in retriever.invoke(q)] for q in test_questions
    ]
    t1 = time.perf_counter()
    print(f"[第一次] 检索+精排耗时 {t1 - t0:.2f}s")

    t0 = time.perf_counter()
    _ = [[d.page_content for d in retriever.invoke(q)] for q in test_questions]
    t1 = time.perf_counter()
    print(f"[第二次] 检索+精排耗时 {t1 - t0:.2f}s（精排分数命中缓存）")

    hit_rate, mrr = evaluate_retrieval(test_questions, true_indices,
                                       chunks, reranked_results)
    print(f"\nHit Rate: {hit_rate:.2%}")
    print(f"MRR: {mrr:.2f}")

    print(f"\n缓存统计：{cache.get_stats()}")

    if input("是否调用 DeepSeek 生成一段示例回答？(y/N): ").strip().lower() == "y":
        chain = make_chain(retriever)
        q = test_questions[10]
        first = query(q, retriever, chain, lang=lang)      # 未命中 -> 调 DeepSeek
        print(f"\n问题：{q}\n最终回答：\n{first['answer']}")
        print(f"（cache_hit={first['cache_hit']}, 耗时 {first['elapsed_ms']}ms）")
        second = query(q, retriever, chain, lang=lang)     # 命中 -> 秒回
        print(f"再问一次：cache_hit={second['cache_hit']}, 耗时 {second['elapsed_ms']}ms")
