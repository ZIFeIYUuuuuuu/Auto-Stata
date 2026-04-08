from __future__ import annotations

import re
from pathlib import Path


def _extract_r2(log_text: str) -> str | None:
    patterns = [
        r"R-squared\s*=\s*([0-9.]+)",
        r"Within\s*=\s*([0-9.]+)",
        r"Overall\s*=\s*([0-9.]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, log_text)
        if m:
            return m.group(1)
    return None


def _extract_prob_f(log_text: str) -> str | None:
    patterns = [
        r"Prob > F\s*=\s*([0-9.]+)",
        r"Prob > chi2\s*=\s*([0-9.]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, log_text)
        if m:
            return m.group(1)
    return None


def _infer_vars_from_log(log_text: str) -> list[str]:
    vars_found: list[str] = []
    lines = log_text.splitlines()
    for line in lines:
        striped = line.strip()
        if not striped:
            continue
        # 简单从变量结果表中抽变量名
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s+\|", striped):
            v = striped.split("|")[0].strip()
            if v not in {"_cons"} and v not in vars_found:
                vars_found.append(v)
    return vars_found[:6]


def _scatter_matrix_caption(vars_found: list[str]) -> tuple[str, str]:
    if vars_found:
        var_text = "、".join(vars_found)
        title = "图1 主要变量散点矩阵图"
        caption = f"该图展示了 {var_text} 等主要变量之间的两两散点分布关系，用于初步观察变量间的线性趋势、离散程度及潜在异常值。"
    else:
        title = "图1 主要变量散点矩阵图"
        caption = "该图展示了主要变量之间的两两散点分布关系，用于初步观察变量间的线性趋势、离散程度及潜在异常值。"
    return title, caption


def _scatter_matrix_commentary(log_text: str) -> str:
    vars_found = _infer_vars_from_log(log_text)
    if vars_found:
        var_text = "、".join(vars_found)
        return (
            f"从散点矩阵图可以对 {var_text} 等变量之间的关系进行直观判断。"
            "若散点呈现较明显的斜向带状分布，通常意味着变量之间可能存在一定线性相关；"
            "若散点分布较为分散，则说明简单线性关系可能较弱。"
            "此外，散点矩阵还可用于识别潜在极端值和异常观测。"
            "需要指出的是，图形证据仅用于描述性判断，变量之间的真实影响方向与显著性仍应以回归分析结果为准。"
        )
    return (
        "从散点矩阵图可以对主要变量之间的关系进行直观判断。"
        "若散点呈现较明显的斜向带状分布，通常意味着变量之间可能存在一定线性相关；"
        "若散点分布较为分散，则说明简单线性关系可能较弱。"
        "此外，散点矩阵还可用于识别潜在极端值和异常观测。"
        "需要指出的是，图形证据仅用于描述性判断，变量之间的真实影响方向与显著性仍应以回归分析结果为准。"
    )


def _residual_plot_caption() -> tuple[str, str]:
    title = "图2 残差与拟合值散点图"
    caption = "该图展示了回归模型残差与拟合值之间的关系，用于检验模型设定是否合理，以及是否存在异方差、非线性或异常点等问题。"
    return title, caption


def _residual_plot_commentary(log_text: str) -> str:
    r2 = _extract_r2(log_text)
    pval = _extract_prob_f(log_text)

    parts = [
        "从残差图看，若样本点大体围绕零线随机分布，通常表明模型设定基本合理，未出现明显系统性偏误。"
        "若残差随着拟合值增大而呈现扩张或收缩趋势，则提示可能存在异方差；"
        "若残差表现出明显曲线轨迹，则说明模型可能遗漏了非线性项或关键解释变量。"
    ]

    if r2:
        parts.append(f"结合回归结果可知，当前模型的拟合优度 R² 约为 {r2}。")
    if pval:
        parts.append(f"模型整体显著性对应的概率值约为 {pval}。")

    parts.append(
        "因此，残差图的作用主要在于提供模型诊断层面的辅助证据，"
        "最终仍需结合稳健标准误、系数显著性与理论逻辑综合判断模型有效性。"
    )
    return "".join(parts)


def _generic_plot_caption(step: str, filename: str) -> tuple[str, str]:
    if step == "baseline_regression":
        return (
            "图X 回归诊断图",
            "该图用于辅助检验基准回归模型的设定是否合理，并观察样本点分布及潜在异常值情况。",
        )
    if step == "panel":
        return (
            "图X 面板分析辅助图",
            "该图用于辅助呈现面板模型估计结果或模型诊断信息，为固定效应或随机效应模型的结果解释提供图形支持。",
        )
    return (
        "图X 实证分析辅助图",
        f"该图为 {Path(filename).name} 对应的分析结果图，用于辅助展示模型估计结果和样本分布特征。",
    )


def _generic_plot_commentary(step: str) -> str:
    if step == "baseline_regression":
        return (
            "该图主要用于辅助解释基准回归模型的拟合特征与样本分布情况。"
            "在实证研究中，图形证据可以帮助研究者识别异常值、潜在异方差以及模型设定偏误。"
            "不过，图形本身并不直接提供显著性检验结论，因此仍需结合回归系数、标准误和显著性水平进行综合判断。"
        )
    if step == "panel":
        return (
            "该图用于补充面板模型的估计结果。"
            "面板数据分析的重点在于识别个体差异与时间变化带来的影响，因此图形结果主要起到辅助说明作用。"
            "在解释图形时，应重点结合固定效应、随机效应及 Hausman 检验结果进行整体分析。"
        )
    return (
        "该图为模型结果的辅助展示。"
        "图形分析有助于从直观层面理解变量之间的关系及模型拟合特征，"
        "但正式结论仍应建立在统计检验与理论解释基础之上。"
    )


def build_chart_commentary(step: str, graph_path: str, log_text: str) -> dict[str, str]:
    """
    根据步骤名称 + 图片文件名 + 日志文本，生成图题、图注和专业解读
    返回:
    {
        "title": "...",
        "caption": "...",
        "commentary": "..."
    }
    """
    filename = Path(graph_path).name.lower()

    if "scatter" in filename or "matrix" in filename:
        vars_found = _infer_vars_from_log(log_text)
        title, caption = _scatter_matrix_caption(vars_found)
        commentary = _scatter_matrix_commentary(log_text)
        return {
            "title": title,
            "caption": caption,
            "commentary": commentary,
        }

    if "residual" in filename:
        title, caption = _residual_plot_caption()
        commentary = _residual_plot_commentary(log_text)
        return {
            "title": title,
            "caption": caption,
            "commentary": commentary,
        }

    title, caption = _generic_plot_caption(step, filename)
    commentary = _generic_plot_commentary(step)
    return {
        "title": title,
        "caption": caption,
        "commentary": commentary,
    }