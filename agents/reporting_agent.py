"""多模态报告生成 Agent

使用 Qwen-VL 模型解读 Stata 回归表格和图片，生成 AI 解读文本，
然后通过 word_formatter 输出符合学术规范的 Word 文档。
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_qwq import ChatQwen

from config import DASHSCOPE_API_KEY, QWEN_VL_MODEL, QWEN_TEXT_MODEL
from schemas import AnalysisStepResult
from word_formatter import build_report_docx

logger = logging.getLogger("autostata.reporting")

REPORT_SYSTEM_PROMPT = """\
你是一位资深计量经济学研究员，擅长撰写学术实证分析报告。

请根据提供的 Stata 回归输出日志和统计图表，撰写一份完整的学术分析解读。

报告结构要求：
## 一、描述性统计分析
- 解读各变量的均值、标准差、极值
- 分析变量分布特征

## 二、相关性分析
- 解读相关系数矩阵
- 指出显著相关的变量对
- 初步判断多重共线性风险

## 三、多重共线性检验 (VIF)
- 解读 VIF 值，判断是否存在严重多重共线性（VIF > 10 为警戒线）

## 四、基准回归结果
- 重点解读核心解释变量的系数符号、大小和统计显著性（P值）
- 解释经济含义
- 评价模型拟合度（R²）

## 五、面板数据分析
- 报告固定效应和随机效应结果
- 解读 Hausman 检验结果，说明最优模型选择依据
- 对比 FE/RE 结果的一致性

## 六、稳健性检验
- 说明替换变量的合理性
- 对比基准回归结果，判断结论是否稳健

## 七、异质性分析
- 解读分组回归差异
- 分析不同组别间系数差异的经济含义

## 八、内生性处理 (2SLS)
- 解读第一阶段 F 统计量（F > 10 表示工具变量有效）
- 解读过度识别检验结果
- 解读内生性检验结果
- 对比 OLS 与 2SLS 结果

## 九、研究结论与局限
- 总结核心发现
- 指出研究局限和未来方向

写作要求：
- 使用学术论文的规范表述
- 对每个回归系数给出经济学解释
- P值标注：***p<0.01, **p<0.05, *p<0.1
- 如果某个分析步骤的数据缺失或出错，请注明并跳过该部分
"""


def _encode_image(image_path: str) -> str | None:
    """将本地图片编码为 base64 data URI"""
    p = Path(image_path)
    if not p.exists():
        return None
    data = base64.b64encode(p.read_bytes()).decode("utf-8")
    suffix = p.suffix.lstrip(".").lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
        suffix, "image/png"
    )
    return f"data:{mime};base64,{data}"


def _build_content_blocks(
    results: list[AnalysisStepResult],
) -> list[dict]:
    """将分析结果组装为多模态 content 块"""
    blocks: list[dict] = []

    for r in results:
        if r.error:
            blocks.append({
                "type": "text",
                "text": f"\n### {r.step} (执行出错)\n错误信息: {r.error}\n",
            })
            continue

        if r.log:
            blocks.append({
                "type": "text",
                "text": f"\n### {r.step} 输出日志\n```\n{r.log}\n```\n",
            })

        for img_path in r.graphs:
            encoded = _encode_image(img_path)
            if encoded:
                blocks.append({
                    "type": "image_url",
                    "image_url": {"url": encoded},
                })

    return blocks


async def generate_report(
    results: list[AnalysisStepResult],
    output_dir: Path,
) -> Path:
    """生成学术分析报告（Word 格式）

    流程：
    1. 调用 Qwen-VL 生成 AI 解读文本
    2. 将解读文本 + Stata 表格结果合并为 Word 文档（三线表样式）

    Args:
        results: 各步骤分析结果列表
        output_dir: 输出目录

    Returns:
        Word 报告文件路径
    """
    llm = ChatQwen(
        model=QWEN_TEXT_MODEL,
        api_key=DASHSCOPE_API_KEY,
        max_tokens=8000,
        temperature=0.3,
    )

    content_blocks = _build_content_blocks(results)

    # 生成 AI 解读文本
    ai_report = ""
    if content_blocks:
        messages = [
            ("system", REPORT_SYSTEM_PROMPT),
            HumanMessage(content=[
                {"type": "text", "text": "请根据以下 Stata 分析输出撰写完整的学术报告："},
                *content_blocks,
            ]),
        ]

        logger.info("调用 Qwen-VL 生成报告（%d 个内容块）...", len(content_blocks))
        chain = llm | StrOutputParser()
        ai_report = await chain.ainvoke(messages)
    else:
        ai_report = "未获取到有效的分析结果，无法生成 AI 解读。"

    # 同时保存 Markdown 版本
    md_path = output_dir / "report.md"
    md_path.write_text(ai_report, encoding="utf-8")

    # 生成 Word 文档（三线表样式）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    docx_path = output_dir / f"分析报告_{timestamp}.docx"
    build_report_docx(results, ai_report, docx_path)

    logger.info("Word 报告已生成: %s", docx_path)
    return docx_path
