"""pystata 驱动的计量经济学分析引擎"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd

from schemas import AnalysisStepResult, DepType

logger = logging.getLogger("autostata.engine")


class StataEngine:
    """Stata 分析引擎"""

    def __init__(self, edition: str, output_dir: Path) -> None:
        self.edition = edition
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._do_lines: list[str] = []

        try:
            import pystata  # noqa: F401
            from pystata import config as st_config
        except ImportError as e:
            raise RuntimeError(
                "pystata 未找到。请确保本地已安装 Stata，并且 pystata 已加入 Python 环境。"
            ) from e

        self._config = st_config

        if not self._config.is_stata_initialized():
            try:
                logger.info("初始化 PyStata: edition=%s", edition)
                self._config.init(edition, splash=False)
            except Exception as e:
                raise RuntimeError(
                    f"PyStata 初始化失败，edition={edition}。原始错误: {e}"
                ) from e

        from pystata import stata as st
        self._stata = st

        self._config.set_graph_format("png")
        self._config.set_graph_size(width="5.5in", height="4in")
        self._config.set_streaming_output_mode("off")

        self._loaded_df_columns: list[str] = []
        self._string_vars: set[str] = set()
        self._encoded_map: dict[str, str] = {}

    def _log_path(self, step: str) -> Path:
        return self.output_dir / f"{step}.log"

    @contextmanager
    def _capture(self, step: str):
        log_file = self._log_path(step)
        self._config.set_output_file(str(log_file), replace=True)
        try:
            yield log_file
        finally:
            self._config.close_output_file()

    def _run(self, cmd: str) -> None:
        self._do_lines.append(cmd)
        self._stata.run(cmd, quietly=False)

    def _get_ereturn(self) -> dict[str, Any]:
        try:
            return self._stata.get_ereturn()
        except Exception:
            return {}

    def _get_return(self) -> dict[str, Any]:
        try:
            return self._stata.get_return()
        except Exception:
            return {}

    def _read_log(self, step: str) -> str:
        log_file = self._log_path(step)
        if log_file.exists():
            return log_file.read_text(encoding="utf-8", errors="replace")
        return ""

    def _collect_graphs(self, prefix: str) -> list[str]:
        return [str(p) for p in self.output_dir.glob(f"{prefix}*.png")]

    def save_do_file(self, task_id: str) -> Path:
        do_path = self.output_dir / f"{task_id}.do"
        do_path.write_text("\n".join(self._do_lines), encoding="utf-8")
        return do_path

    def load_data(self, df: pd.DataFrame) -> None:
        """将 DataFrame 载入 Stata，并预处理字符串分类变量"""
        self._loaded_df_columns = df.columns.tolist()

        # 记录字符串变量
        self._string_vars = {
            col for col in df.columns
            if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col])
        }

        self._stata.pdataframe_to_data(df, force=True)
        self._do_lines.insert(0, f"* Data loaded: {len(df)} obs, {len(df.columns)} vars")

        # 将字符串分类变量 encode 为数值类别变量
        for col in sorted(self._string_vars):
            safe_new = f"{col}_cat"
            if len(safe_new) > 32:
                safe_new = f"{col[:28]}_cat"

            self._run(f'capture confirm string variable {col}')
            self._run(f'if _rc == 0 encode {col}, gen({safe_new})')
            self._encoded_map[col] = safe_new

        logger.info("字符串变量: %s", sorted(self._string_vars))
        logger.info("编码后的分类变量映射: %s", self._encoded_map)

    def _is_string_var(self, var: str) -> bool:
        return var in self._string_vars

    def _stata_var_for_summary(self, var: str) -> str | None:
        """描述统计/相关性分析用：字符串变量不参与"""
        if self._is_string_var(var):
            return None
        return var

    def _stata_var_for_model(self, var: str) -> str:
        """回归模型用：字符串分类变量转 i.xxx_cat"""
        if self._is_string_var(var):
            encoded = self._encoded_map.get(var)
            if not encoded:
                raise RuntimeError(f"字符串变量 {var} 未成功编码。")
            return f"i.{encoded}"
        return var

    def _filter_numeric_vars(self, vars: list[str]) -> list[str]:
        result: list[str] = []
        for v in vars:
            vv = self._stata_var_for_summary(v)
            if vv:
                result.append(vv)
        return result

    def _build_model_varlist(self, vars: list[str]) -> str:
        return " ".join(self._stata_var_for_model(v) for v in vars)

    def run_descriptive(self, vars: list[str]) -> AnalysisStepResult:
        step = "descriptive"
        try:
            numeric_vars = self._filter_numeric_vars(vars)
            if not numeric_vars:
                return AnalysisStepResult(step=step, error="无可用于描述统计的数值变量。")

            var_str = " ".join(numeric_vars)

            with self._capture(step):
                self._run(f"summarize {var_str}")
                if len(numeric_vars) >= 2:
                    self._run(f"pwcorr {var_str}, star(0.05)")
                    graph_name = str(self.output_dir / "scatter_matrix.png")
                    self._run(f"graph matrix {var_str}, half msize(small)")
                    self._run(f'graph export "{graph_name}", replace')

            return AnalysisStepResult(
                step=step,
                log=self._read_log(step),
                ereturn=self._get_return(),
                graphs=self._collect_graphs("scatter"),
            )
        except SystemError as e:
            logger.error("描述性统计失败: %s", e)
            return AnalysisStepResult(step=step, error=str(e))

    def run_vif(self, dep: str, indeps: list[str]) -> AnalysisStepResult:
        step = "vif"
        try:
            dep_var = self._stata_var_for_summary(dep)
            if dep_var is None:
                return AnalysisStepResult(step=step, error=f"因变量 {dep} 不是可用于回归的数值变量。")

            indep_str = self._build_model_varlist(indeps)

            with self._capture(step):
                self._run(f"reg {dep_var} {indep_str}")
                self._run("estat vif")

            return AnalysisStepResult(
                step=step,
                log=self._read_log(step),
                ereturn=self._get_return(),
            )
        except SystemError as e:
            logger.error("VIF 检验失败: %s", e)
            return AnalysisStepResult(step=step, error=str(e))

    def run_baseline_regression(
        self, dep: str, indeps: list[str], dep_type: DepType
    ) -> AnalysisStepResult:
        step = "baseline_regression"
        try:
            dep_var = self._stata_var_for_summary(dep)
            if dep_var is None:
                return AnalysisStepResult(step=step, error=f"因变量 {dep} 不是可用于回归的数值变量。")

            indep_str = self._build_model_varlist(indeps)

            with self._capture(step):
                if dep_type == DepType.CONTINUOUS:
                    self._run(f"reg {dep_var} {indep_str}, robust")
                else:
                    self._run(f"logit {dep_var} {indep_str}, robust")
                    self._run(f"probit {dep_var} {indep_str}, robust")

                if dep_type == DepType.CONTINUOUS:
                    graph_name = str(self.output_dir / "residual_plot.png")
                    self._run("predict resid, residuals")
                    self._run("predict yhat, xb")
                    self._run('scatter resid yhat, yline(0) title("Residual Plot")')
                    self._run(f'graph export "{graph_name}", replace')
                    self._run("drop resid yhat")

            return AnalysisStepResult(
                step=step,
                log=self._read_log(step),
                ereturn=self._get_ereturn(),
                graphs=self._collect_graphs("residual"),
            )
        except SystemError as e:
            logger.error("基准回归失败: %s", e)
            return AnalysisStepResult(step=step, error=str(e))

    def run_panel_analysis(
        self, dep: str, indeps: list[str], panel_id: str, time_var: str
    ) -> AnalysisStepResult:
        step = "panel"
        try:
            dep_var = self._stata_var_for_summary(dep)
            if dep_var is None:
                return AnalysisStepResult(step=step, error=f"因变量 {dep} 不是可用于回归的数值变量。")

            indep_str = self._build_model_varlist(indeps)

            with self._capture(step):
                self._run(f"xtset {panel_id} {time_var}")
                self._run(f"xtreg {dep_var} {indep_str}, fe robust")
                self._run("estimates store fe_model")
                self._run(f"xtreg {dep_var} {indep_str}, re robust")
                self._run("estimates store re_model")
                self._run(f"xtreg {dep_var} {indep_str}, fe")
                self._run("estimates store fe_for_hausman")
                self._run(f"xtreg {dep_var} {indep_str}, re")
                self._run("estimates store re_for_hausman")
                self._run("hausman fe_for_hausman re_for_hausman")

            return AnalysisStepResult(
                step=step,
                log=self._read_log(step),
                ereturn=self._get_return(),
            )
        except SystemError as e:
            logger.error("面板分析失败: %s", e)
            return AnalysisStepResult(step=step, error=str(e))

    def run_robustness(
        self, dep: str, indeps: list[str], alt_dep: str
    ) -> AnalysisStepResult:
        step = "robustness"
        try:
            alt_dep_var = self._stata_var_for_summary(alt_dep)
            if alt_dep_var is None:
                return AnalysisStepResult(step=step, error=f"替代因变量 {alt_dep} 不是可用于回归的数值变量。")

            indep_str = self._build_model_varlist(indeps)

            with self._capture(step):
                self._run(f"* 稳健性检验: 替换被解释变量 {dep} -> {alt_dep}")
                self._run(f"reg {alt_dep_var} {indep_str}, robust")

            return AnalysisStepResult(
                step=step,
                log=self._read_log(step),
                ereturn=self._get_ereturn(),
            )
        except SystemError as e:
            logger.error("稳健性检验失败: %s", e)
            return AnalysisStepResult(step=step, error=str(e))

    def run_heterogeneity(
        self, dep: str, indeps: list[str], group_var: str
    ) -> AnalysisStepResult:
        step = "heterogeneity"
        try:
            dep_var = self._stata_var_for_summary(dep)
            if dep_var is None:
                return AnalysisStepResult(step=step, error=f"因变量 {dep} 不是可用于回归的数值变量。")

            if self._is_string_var(group_var):
                g = self._encoded_map.get(group_var)
                if not g:
                    return AnalysisStepResult(step=step, error=f"分组变量 {group_var} 未成功编码。")
            else:
                g = group_var

            indep_str = self._build_model_varlist(indeps)

            with self._capture(step):
                self._run(f"tab {g}")
                self._run(f"bysort {g}: reg {dep_var} {indep_str}, robust")

            return AnalysisStepResult(
                step=step,
                log=self._read_log(step),
                ereturn=self._get_ereturn(),
            )
        except SystemError as e:
            logger.error("异质性分析失败: %s", e)
            return AnalysisStepResult(step=step, error=str(e))

    def run_iv_2sls(
        self,
        dep: str,
        indeps: list[str],
        endog: str,
        instruments: list[str],
    ) -> AnalysisStepResult:
        step = "iv_2sls"
        try:
            dep_var = self._stata_var_for_summary(dep)
            if dep_var is None:
                return AnalysisStepResult(step=step, error=f"因变量 {dep} 不是可用于回归的数值变量。")

            if self._is_string_var(endog):
                return AnalysisStepResult(step=step, error=f"内生变量 {endog} 为字符串变量，当前 2SLS 暂不支持。")

            exog = [v for v in indeps if v != endog]
            exog_str = self._build_model_varlist(exog)

            iv_terms = []
            for iv in instruments:
                if self._is_string_var(iv):
                    encoded = self._encoded_map.get(iv)
                    if not encoded:
                        return AnalysisStepResult(step=step, error=f"工具变量 {iv} 未成功编码。")
                    iv_terms.append(encoded)
                else:
                    iv_terms.append(iv)
            iv_str = " ".join(iv_terms)

            with self._capture(step):
                self._run(
                    f"ivregress 2sls {dep_var} {exog_str} ({endog} = {iv_str}), robust first"
                )
                self._run("estat firststage")
                if len(instruments) > 1:
                    self._run("estat overid")
                self._run("estat endogenous")

            return AnalysisStepResult(
                step=step,
                log=self._read_log(step),
                ereturn=self._get_ereturn(),
            )
        except SystemError as e:
            logger.error("2SLS 分析失败: %s", e)
            return AnalysisStepResult(step=step, error=str(e))