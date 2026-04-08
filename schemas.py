"""Pydantic 数据模型"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DepType(str, Enum):
    CONTINUOUS = "continuous"
    BINARY = "binary"


from typing import Optional

class MetadataResult(BaseModel):
    mappings: dict[str, str] = Field(description="中文列名 → 英文变量名映射")
    panel_id: Optional[str] = Field(default=None, description="面板个体标识变量")
    time_var: Optional[str] = Field(default=None, description="时间变量")
    dep_var: Optional[str] = Field(default=None, description="被解释变量（英文名）")
    indep_vars: Optional[list[str]] = Field(default_factory=list, description="解释变量列表（英文名）")
    dep_type: Optional[DepType] = Field(default=DepType.CONTINUOUS, description="被解释变量类型")
    control_vars: Optional[list[str]] = Field(default_factory=list, description="控制变量")
    alt_dep_var: Optional[str] = Field(default=None, description="替代被解释变量（稳健性检验）")
    group_var: Optional[str] = Field(default=None, description="分组变量（异质性分析）")
    endog_var: Optional[str] = Field(default=None, description="内生变量（2SLS）")
    instruments: Optional[list[str]] = Field(default_factory=list, description="工具变量（2SLS）")


class AnalysisStepResult(BaseModel):
    """单步分析结果"""
    step: str
    log: str = ""
    ereturn: dict = Field(default_factory=dict)
    graphs: list[str] = Field(default_factory=list)
    error: Optional[str] = None
