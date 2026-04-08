"""AutoStata-Insight — 命令行入口

自动扫描 input/ 目录中最新的 Excel 文件，执行完整的计量经济学分析流水线。
用法: python main.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from config import INPUT_DIR, OUTPUT_DIR, STATA_EDITION
from utils import ensure_dirs, find_latest_excel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("autostata")


async def run_pipeline(excel_path: Path) -> None:
    """完整分析流水线"""
    # 延迟导入，避免在缺少依赖时立即报错
    import pandas as pd

    from agents.metadata_agent import run_metadata_agent
    from agents.reporting_agent import generate_report
    from engine.stata_engine import StataEngine
    from schemas import AnalysisStepResult

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[AnalysisStepResult] = []

    # ── 1. 读取 Excel ──
    logger.info("=" * 60)
    logger.info("读取数据文件: %s", excel_path.name)
    df = pd.read_excel(excel_path, engine="openpyxl")
    logger.info("数据维度: %d 行 × %d 列", len(df), len(df.columns))
    logger.info("列名: %s", ", ".join(df.columns.tolist()))

    # ── 2. AI 清洗 & 变量映射 ──
    logger.info("-" * 60)
    logger.info("[步骤 1/7] AI 分析数据结构与变量映射...")
    cleaned_df, metadata = await run_metadata_agent(df)

    mapping_path = out_dir / "variable_mapping.json"
    mapping_path.write_text(
        json.dumps(metadata.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("变量映射已保存: %s", mapping_path.name)
    logger.info("被解释变量: %s (%s)", metadata.dep_var, metadata.dep_type.value)
    logger.info("解释变量: %s", ", ".join(metadata.indep_vars))
    logger.info("面板结构: %s × %s", metadata.panel_id, metadata.time_var)

    # ── 3. 初始化 Stata 引擎 ──
    logger.info("-" * 60)
    logger.info("初始化 Stata/MP 引擎...")
    engine = StataEngine(edition=STATA_EDITION, output_dir=out_dir)
    engine.load_data(cleaned_df)

    all_vars = [metadata.dep_var] + metadata.indep_vars

    # ── 4. 描述性统计 ──
    logger.info("-" * 60)
    logger.info("[步骤 2/7] 描述性统计与相关性分析...")
    r = engine.run_descriptive(all_vars)
    results.append(r)
    _log_step_result(r)

    # ── 5. VIF 检验 ──
    logger.info("-" * 60)
    logger.info("[步骤 3/7] VIF 多重共线性检验...")
    r = engine.run_vif(metadata.dep_var, metadata.indep_vars)
    results.append(r)
    _log_step_result(r)

    # ── 6. 基准回归 ──
    logger.info("-" * 60)
    logger.info("[步骤 4/7] 基准回归分析...")
    r = engine.run_baseline_regression(
        metadata.dep_var, metadata.indep_vars, metadata.dep_type
    )
    results.append(r)
    _log_step_result(r)

    # ── 7. 面板数据分析 ──
    # ── 7. 面板数据分析（仅在识别到 panel_id 和 time_var 时执行） ──
    if metadata.panel_id and metadata.time_var:
        logger.info("-" * 60)
        logger.info("[步骤 5/7] 面板数据分析 (FE/RE + Hausman)...")
        r = engine.run_panel_analysis(
            metadata.dep_var,
            metadata.indep_vars,
            metadata.panel_id,
            metadata.time_var,
        )
        results.append(r)
        _log_step_result(r)
    else:
        logger.info("-" * 60)
        logger.info("[步骤 5/7] 跳过面板分析：当前数据未识别到有效的 panel_id/time_var，视为非面板数据。")

    # ── 8. 稳健性检验（可选） ──
    if metadata.alt_dep_var:
        logger.info("-" * 60)
        logger.info("[步骤 6a/7] 稳健性检验（替换被解释变量: %s）...", metadata.alt_dep_var)
        r = engine.run_robustness(
            metadata.dep_var, metadata.indep_vars, metadata.alt_dep_var
        )
        results.append(r)
        _log_step_result(r)

    # ── 9. 异质性分析（可选） ──
    if metadata.group_var:
        logger.info("-" * 60)
        logger.info("[步骤 6b/7] 异质性分析（分组变量: %s）...", metadata.group_var)
        r = engine.run_heterogeneity(
            metadata.dep_var, metadata.indep_vars, metadata.group_var
        )
        results.append(r)
        _log_step_result(r)

    # ── 10. 2SLS 工具变量法（可选） ──
    # ── 10. 2SLS 工具变量法（可选） ──
    valid_instruments = []
    if metadata.instruments:
        valid_instruments = [iv for iv in metadata.instruments if iv not in metadata.indep_vars]

    if metadata.endog_var and valid_instruments:
        logger.info("-" * 60)
        logger.info("[步骤 6c/7] 2SLS 工具变量分析...")
        r = engine.run_iv_2sls(
            metadata.dep_var,
            metadata.indep_vars,
            metadata.endog_var,
            valid_instruments,
        )
        results.append(r)
        _log_step_result(r)
    else:
        logger.info("-" * 60)
        logger.info("[步骤 6c/7] 跳过 2SLS：无有效的排除型工具变量。")

    # ── 11. 保存 .do 文件 ──
    do_path = engine.save_do_file(timestamp)
    logger.info("Stata .do 文件已保存: %s", do_path.name)

    # ── 12. 生成报告 ──
    logger.info("-" * 60)
    logger.info("[步骤 7/7] AI 生成分析报告...")
    report_path = await generate_report(results, out_dir)

    # ── 完成 ──
    logger.info("=" * 60)
    logger.info("分析完成！所有结果已保存至: %s", out_dir)
    logger.info("Word 报告: %s", report_path.name)
    logger.info("=" * 60)


def _log_step_result(r) -> None:
    """打印单步结果摘要"""
    if r.error:
        logger.warning("  ⚠ %s 执行出错: %s", r.step, r.error)
    else:
        logger.info("  ✓ %s 完成 (日志 %d 字符, %d 张图)", r.step, len(r.log), len(r.graphs))


def main() -> None:
    """程序入口"""
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║       AutoStata-Insight 自动化实证分析系统       ║")
    print("╚══════════════════════════════════════════════════╝")
    print()

    ensure_dirs()

    excel_path = find_latest_excel()
    if excel_path is None:
        print(f"错误：在 {INPUT_DIR} 目录中未找到 Excel 文件（.xlsx 或 .xls）。")
        print(f"请将待分析的 Excel 数据文件放入 {INPUT_DIR} 目录后重新运行。")
        sys.exit(1)

    logger.info("找到最新数据文件: %s", excel_path.name)

    try:
        asyncio.run(run_pipeline(excel_path))
    except RuntimeError as e:
        logger.error("运行失败: %s", e)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("用户中断运行。")
        sys.exit(0)


if __name__ == "__main__":
    main()
