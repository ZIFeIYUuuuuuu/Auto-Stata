"""AutoStata-Insight 全局配置"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

# 显式加载项目根目录下的 .env，避免 uv / IDE / 不同工作目录导致读取失败
ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE, override=False)

INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"

# Stata 配置
STATA_EDITION: str = os.getenv("STATA_EDITION", "mp")

# Qwen 模型配置
DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "").strip()
DASHSCOPE_API_BASE: str = os.getenv(
    "DASHSCOPE_API_BASE",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
).strip()
QWEN_TEXT_MODEL: str = os.getenv("QWEN_TEXT_MODEL", "qwen-plus").strip()
QWEN_VL_MODEL: str = os.getenv("QWEN_VL_MODEL", "qwen-vl-max-latest").strip()