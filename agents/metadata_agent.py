"""数据清洗 & 变量映射 Agent

使用 LangChain LCEL 链 + Qwen 模型，将 Excel 数据的表头
映射为标准英文变量名，并识别变量角色。
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import pandas as pd
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_qwq import ChatQwen

from config import DASHSCOPE_API_BASE, DASHSCOPE_API_KEY, QWEN_TEXT_MODEL
from schemas import MetadataResult

logger = logging.getLogger("autostata.metadata")

SYSTEM_PROMPT = """\
你是一位资深计量经济学数据专家。你的任务是分析用户上传的 Excel 数据预览，完成以下工作：

1. 变量名映射
- 将所有列名映射为标准英文变量名。
- 如果原表头是中文，翻译为适合计量经济学与 Stata 使用的英文缩写变量名。
- 如果原表头本身已经是英文或常见英文缩写，则保留其语义并规范化命名。
- Stata 变量名要求：
  - 小写
  - 仅允许字母、数字、下划线
  - 不能以数字开头
  - 长度不超过 32 个字符

2. 数据结构识别
- 若存在 panel_id 和 time_var，则识别
- 若不是面板数据，可返回 null

3. 变量角色识别
根据变量语义和数据特征，判断：
- dep_var: 最可能的被解释变量
- indep_vars: 解释变量列表
- dep_type: "continuous" 或 "binary"
- control_vars: 控制变量
- alt_dep_var: 可用于稳健性检验的替代被解释变量（如有）
- group_var: 可用于异质性分析的分组变量（如有）
- endog_var: 可能存在内生性的变量（如有）
- instruments: 可能的工具变量（如有）

4. 重名约束
- mappings 的 value 绝对不能重复
- 每个原始列名都必须映射到唯一变量名

请严格输出 JSON，不要输出任何解释文字。

{format_instructions}
"""

HUMAN_PROMPT = """\
以下是上传数据的预览信息：

列名:
{columns}

数据类型:
{dtypes}

前5行数据:
{head}

基本统计:
{describe}

请输出 JSON 映射结果。
"""


def _build_chain() -> Any:
    """构建 LCEL 链"""
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("未检测到 DASHSCOPE_API_KEY，请先在 .env 中配置。")

    os.environ["DASHSCOPE_API_KEY"] = DASHSCOPE_API_KEY
    os.environ["DASHSCOPE_API_BASE"] = DASHSCOPE_API_BASE

    llm = ChatQwen(
        model=QWEN_TEXT_MODEL,
        api_key=DASHSCOPE_API_KEY,
        max_tokens=4000,
        temperature=0.1,
    )

    parser = JsonOutputParser(pydantic_object=MetadataResult)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", HUMAN_PROMPT),
    ]).partial(format_instructions=parser.get_format_instructions())

    return prompt | llm | parser


def _prepare_preview(df: pd.DataFrame) -> dict[str, str]:
    """将 DataFrame 转成 LLM 可读预览"""
    return {
        "columns": ", ".join(map(str, df.columns.tolist())),
        "dtypes": df.dtypes.to_string(),
        "head": df.head(5).to_string(index=False),
        "describe": df.describe(include="all").to_string(),
    }


def _sanitize_var_name(name: str) -> str:
    """规范化 Stata 变量名"""
    if not name:
        return "var"

    name = str(name).strip().lower()
    name = name.replace(" ", "_")
    name = re.sub(r"[^a-z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")

    if not name:
        name = "var"

    if name[0].isdigit():
        name = f"v_{name}"

    return name[:32]


def _make_unique_names(mappings: dict[str, str]) -> dict[str, str]:
    """确保映射结果中的变量名唯一"""
    used: dict[str, int] = {}
    new_mappings: dict[str, str] = {}

    for old_col, raw_new_name in mappings.items():
        base = _sanitize_var_name(raw_new_name)
        candidate = base

        if candidate not in used:
            used[candidate] = 1
            new_mappings[old_col] = candidate
            continue

        idx = used[candidate]
        while True:
            suffix = f"_{idx}"
            trimmed = base[: 32 - len(suffix)]
            candidate2 = f"{trimmed}{suffix}"
            if candidate2 not in used:
                used[candidate] += 1
                used[candidate2] = 1
                new_mappings[old_col] = candidate2
                break
            idx += 1

    return new_mappings


def _postprocess_metadata(df: pd.DataFrame, metadata: MetadataResult) -> MetadataResult:
    """对 LLM 输出做二次修正"""
    original_cols = set(map(str, df.columns.tolist()))

    mappings = {
        str(k): str(v)
        for k, v in metadata.mappings.items()
        if str(k) in original_cols
    }

    for col in df.columns:
        col = str(col)
        if col not in mappings:
            mappings[col] = _sanitize_var_name(col)

    mappings = _make_unique_names(mappings)
    metadata.mappings = mappings

    renamed_cols = set(mappings.values())
    reverse_guess = {k: v for k, v in mappings.items()}

    def _map_if_old_name(v: str | None) -> str | None:
        if not v:
            return None
        if v in reverse_guess:
            return reverse_guess[v]
        vv = _sanitize_var_name(v)
        if vv in renamed_cols:
            return vv
        return None

    def _safe_vars(vals: list[str]) -> list[str]:
        result: list[str] = []
        seen = set()
        for v in vals:
            vv = reverse_guess.get(v, v)
            vv = _sanitize_var_name(vv)
            if vv in renamed_cols and vv not in seen:
                result.append(vv)
                seen.add(vv)
        return result

    metadata.panel_id = _map_if_old_name(metadata.panel_id)
    metadata.time_var = _map_if_old_name(metadata.time_var)
    metadata.dep_var = _map_if_old_name(metadata.dep_var) or next(iter(renamed_cols), "y")

    metadata.indep_vars = _safe_vars(metadata.indep_vars)
    metadata.control_vars = _safe_vars(metadata.control_vars)
    metadata.alt_dep_var = _map_if_old_name(metadata.alt_dep_var)
    metadata.group_var = _map_if_old_name(metadata.group_var)
    metadata.endog_var = _map_if_old_name(metadata.endog_var)
    metadata.instruments = _safe_vars(metadata.instruments)

    metadata.indep_vars = [v for v in metadata.indep_vars if v != metadata.dep_var]
    metadata.control_vars = [v for v in metadata.control_vars if v != metadata.dep_var]

    if metadata.panel_id:
        metadata.indep_vars = [v for v in metadata.indep_vars if v != metadata.panel_id]
        metadata.control_vars = [v for v in metadata.control_vars if v != metadata.panel_id]

    if metadata.time_var:
        metadata.indep_vars = [v for v in metadata.indep_vars if v != metadata.time_var]
        metadata.control_vars = [v for v in metadata.control_vars if v != metadata.time_var]

    return metadata


def _looks_categorical(series: pd.Series, col_name: str) -> bool:
    """启发式判断变量是否更像分类变量，而非连续变量"""
    name = str(col_name).lower()

    categorical_keywords = {
        "gender", "sex", "city", "province", "region", "industry", "occupation",
        "marriage", "marital", "employment", "job", "education", "edu",
        "status", "type", "group", "category", "brand", "loyalty",
        "satisfaction", "perception", "expect", "health", "social_security"
    }

    # 名称命中
    if name in categorical_keywords:
        return True

    if any(k in name for k in categorical_keywords):
        return True

    non_null = series.dropna()
    if non_null.empty:
        return False

    # 原始字符串 / object 类型，通常优先视为分类
    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        unique_ratio = non_null.nunique(dropna=True) / max(len(non_null), 1)
        # 文本变量通常视为分类；若唯一值过多且像自由文本，可后续再细分
        if unique_ratio <= 0.8:
            return True

    # 数值但取值很少，也更像分类变量/量表变量
    numeric = pd.to_numeric(non_null, errors="coerce")
    if numeric.notna().sum() >= len(non_null) * 0.8:
        uniq = numeric.nunique(dropna=True)
        if uniq <= 10:
            return True

    return False


def _normalize_binary_or_ordered_categories(series: pd.Series) -> pd.Series:
    """将明显的二元/有序类别变量映射为数值，保留无法识别者原样"""
    s = series.copy()

    if s.dropna().empty:
        return s

    # 统一字符串表示
    s_str = s.astype(str).str.strip()
    non_null = s[s.notna()]
    non_null_str = s_str[s.notna()]

    unique_vals = set(non_null_str.unique().tolist())

    # 常见二元变量映射
    binary_maps = [
        {"是": 1, "否": 0},
        {"有": 1, "无": 0},
        {"已婚": 1, "未婚": 0},
        {"男": 1, "女": 0},
        {"true": 1, "false": 0},
        {"yes": 1, "no": 0},
        {"1": 1, "0": 0},
    ]

    for mp in binary_maps:
        if unique_vals.issubset(set(mp.keys())):
            return non_null_str.map(mp).reindex(s.index)

    # 若本身能安全转数字，直接转
    numeric = pd.to_numeric(s, errors="coerce")
    if numeric.notna().sum() >= len(non_null) * 0.8:
        return numeric

    return s


def _infer_categorical_vars(df: pd.DataFrame, metadata: MetadataResult) -> set[str]:
    """推断分类变量集合"""
    candidates: set[str] = set()

    for col in df.columns:
        if col in {metadata.panel_id, metadata.time_var, metadata.dep_var}:
            continue
        if _looks_categorical(df[col], col):
            candidates.add(col)

    # group_var 通常应保留为分类
    if metadata.group_var and metadata.group_var in df.columns:
        candidates.add(metadata.group_var)

    return candidates


def clean_dataframe(df: pd.DataFrame, metadata: MetadataResult) -> pd.DataFrame:
    """根据映射结果清洗 DataFrame

    关键修复：
    - 不再把所有变量都强制转成数值
    - 分类变量尽量保留或转成有限数值编码
    - 连续变量才强制转 numeric
    """
    df = df.copy()

    # 删除全空行 / 列
    df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)

    # 重命名列
    rename_map = {k: v for k, v in metadata.mappings.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    duplicated = df.columns[df.columns.duplicated()].tolist()
    if duplicated:
        raise RuntimeError(f"变量重名，清洗后存在重复列名: {duplicated}")

    # 处理时间列
    if metadata.time_var and metadata.time_var in df.columns:
        time_col = df[metadata.time_var]
        if pd.api.types.is_datetime64_any_dtype(time_col):
            df[metadata.time_var] = pd.to_datetime(time_col, errors="coerce").dt.year
        else:
            converted = pd.to_numeric(time_col, errors="coerce")
            if converted.notna().sum() >= len(df) * 0.5:
                df[metadata.time_var] = converted

    categorical_vars = _infer_categorical_vars(df, metadata)
    logger.info("识别为分类变量: %s", sorted(categorical_vars))

    # 分类变量：尽量保留；连续变量：转数值
    for col in df.columns:
        if col == metadata.panel_id or col == metadata.time_var:
            continue

        if col in categorical_vars:
            df[col] = _normalize_binary_or_ordered_categories(df[col])
            continue

        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 被解释变量必须能用于回归
    if metadata.dep_var in df.columns:
        df[metadata.dep_var] = pd.to_numeric(df[metadata.dep_var], errors="coerce")

    # 对主要回归变量做一次“可用样本”保护
    model_vars = [metadata.dep_var] + metadata.indep_vars
    model_vars = [v for v in model_vars if v in df.columns]

    if model_vars:
        # 仅检查主要连续变量缺失，不强制所有分类变量一起完整
        base_non_null = df[model_vars].notna().sum(axis=1)
        min_required = max(2, len(model_vars) // 3)
        df = df.loc[base_non_null >= min_required].copy()

    # 删除整体缺失值过多的行
    threshold = max(1, int(len(df.columns) * 0.3))
    df = df.dropna(thresh=threshold)

    return df


async def run_metadata_agent(df: pd.DataFrame) -> tuple[pd.DataFrame, MetadataResult]:
    """执行数据清洗 Agent：分析 → 映射 → 清洗"""
    chain = _build_chain()
    preview = _prepare_preview(df)

    logger.info("调用 Qwen 分析数据结构...")

    try:
        result = await chain.ainvoke(preview)
    except Exception as e:
        msg = str(e)
        if "Arrearage" in msg:
            raise RuntimeError("DashScope/阿里百炼账户欠费或余额异常，请先检查控制台账户状态。") from e
        raise

    if isinstance(result, MetadataResult):
        metadata = result
    else:
        if isinstance(result, str):
            result = json.loads(result)
        elif not isinstance(result, dict):
            raise RuntimeError(f"元数据解析失败，返回类型异常: {type(result)}")

        result.setdefault("panel_id", None)
        result.setdefault("time_var", None)
        result.setdefault("control_vars", [])
        result.setdefault("alt_dep_var", None)
        result.setdefault("group_var", None)
        result.setdefault("endog_var", None)
        result.setdefault("instruments", [])

        metadata = MetadataResult(**result)

    metadata = _postprocess_metadata(df, metadata)

    logger.info("变量映射: %s", metadata.mappings)
    logger.info("面板ID: %s, 时间变量: %s", metadata.panel_id, metadata.time_var)
    logger.info("被解释变量: %s (%s)", metadata.dep_var, metadata.dep_type)

    cleaned_df = clean_dataframe(df, metadata)
    return cleaned_df, metadata