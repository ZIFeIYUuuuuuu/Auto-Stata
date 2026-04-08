"""通用工具函数"""

from __future__ import annotations

import logging
from pathlib import Path

from config import INPUT_DIR, OUTPUT_DIR

logger = logging.getLogger("autostata")


def ensure_dirs() -> None:
    """确保 input/ 和 output/ 目录存在"""
    INPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)


def find_latest_excel() -> Path | None:
    """扫描 input/ 目录，按修改时间排序，返回最新的 Excel 文件路径

    支持 .xlsx 和 .xls 格式。若目录为空或无 Excel 文件则返回 None。
    """
    excel_files: list[Path] = []
    for ext in ("*.xlsx", "*.xls"):
        excel_files.extend(INPUT_DIR.glob(ext))

    if not excel_files:
        return None

    # 按文件修改时间降序排列，取最新的
    excel_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return excel_files[0]


def read_log(log_path: Path) -> str:
    """读取 Stata 日志文件内容"""
    if log_path.exists():
        return log_path.read_text(encoding="utf-8", errors="replace")
    return ""
