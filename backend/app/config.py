"""全局配置：从项目根目录 .env 读取。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
load_dotenv(ROOT_DIR / ".env")

# ----- LLM -----
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
MOCK_LLM = os.getenv("MOCK_LLM", "0") == "1"

# ----- 嵌入去重 -----
# 默认 all-MiniLM-L6-v2：22M 参数，CPU 秒级完成，适合交互式流程；
# 追求去重质量且有 GPU 时可换 BAAI/bge-m3（568M，CPU 上每轮需数分钟）
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
HF_ENDPOINT = os.getenv("HF_ENDPOINT", "")
DEDUP_THRESHOLD = float(os.getenv("DEDUP_THRESHOLD", "0.93"))

# ----- 检索 / 流程控制 -----
S2_API_KEY = os.getenv("S2_API_KEY", "")
MIN_PAPERS = int(os.getenv("MIN_PAPERS", "8"))
MAX_RETRY = int(os.getenv("MAX_RETRY", "3"))
HTTP_TIMEOUT = 30

# ----- 路径 -----
DATA_DIR = BACKEND_DIR / "data"
CHECKPOINT_DB = DATA_DIR / "checkpoints.sqlite"
CHROMA_DIR = DATA_DIR / "chroma"
PDF_DIR = DATA_DIR / "pdfs"
EXPORT_DIR = DATA_DIR / "exports"
for _d in (DATA_DIR, CHROMA_DIR, PDF_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ----- Zotero -----
ZOTERO_USER_ID = os.getenv("ZOTERO_USER_ID", "")
ZOTERO_API_KEY = os.getenv("ZOTERO_API_KEY", "")

# ----- Langfuse（可选）-----
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")


def ensure_hf_mirror():
    """sentence-transformers 加载前调用；须在 import huggingface 相关模块前设置。"""
    if HF_ENDPOINT and not os.environ.get("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = HF_ENDPOINT
