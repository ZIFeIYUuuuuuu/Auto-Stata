# AutoStata-Insight 自动化实证分析系统

AutoStata-Insight 是一个面向实证研究场景的自动化分析工具，支持从 Excel 数据出发，自动完成：

- 数据读取与清洗
- 变量映射与语义识别
- Stata 实证分析
- 图表与结果导出
- Word 报告自动生成

适用于企业面板数据、横截面问卷数据、基础计量分析教学演示等场景。

---

## 功能特性

- 自动读取 `input/` 目录下最新的 Excel 文件
- 自动识别中文表头，并映射为 Stata 兼容变量名
- 自动判断变量角色，如：
  - 被解释变量
  - 解释变量
  - 控制变量
  - 面板标识变量
  - 时间变量
- 自动调用 Stata 执行：
  - 描述性统计
  - 相关性分析
  - VIF 检验
  - 基准回归
  - 面板分析（如适用）
  - 稳健性检验
  - 异质性分析
  - 2SLS 工具变量分析（如适用）
- 自动生成 `.do` 文件，便于复现
- 自动生成 Word 实证分析报告
- 报告中支持插入图表、表格及专业解读文字

---

## 项目结构

```text
AutoStata-Insight/
├─ agents/
│  ├─ metadata_agent.py
│  ├─ reporting_agent.py
│  └─ chart_commentary_agent.py
├─ engine/
│  ├─ __init__.py
│  └─ stata_engine.py
├─ input/
├─ output/
├─ config.py
├─ main.py
├─ schemas.py
├─ utils.py
├─ word_formatter.py
├─ requirements.txt
├─ pyproject.toml
├─ .env.example
├─ .gitignore
└─ README.md
运行流程

程序的标准流程如下：

扫描 input/ 目录中的最新 Excel 文件
读取数据并展示维度、列名
调用大语言模型分析表头与变量结构
自动清洗数据并映射变量名
调用 PyStata / Stata 执行实证分析
保存分析日志、图表与 .do 文件
自动生成 Word 报告
环境要求
1. Python

推荐版本：

Python 3.12+
2. Stata

需要本地安装 Stata，并确保 pystata 可正常调用。

推荐版本：

Stata 17 / 18
Stata/MP 更佳
3. 阿里百炼 / DashScope

项目使用 Qwen 模型进行：

变量映射
数据结构识别
报告撰写
图表解读

因此需要配置 DashScope API Key。

安装步骤
1. 克隆项目
git clone https://github.com/yourname/AutoStata-Insight.git
cd AutoStata-Insight
2. 创建虚拟环境
python -m venv .venv

Windows:

.venv\Scripts\activate

macOS / Linux:

source .venv/bin/activate
3. 安装依赖

如果你使用 pip：

pip install -r requirements.txt

如果你使用 uv：

uv sync
配置环境变量

在项目根目录创建 .env 文件。

可参考 .env.example：

DASHSCOPE_API_KEY=your_api_key_here
DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_TEXT_MODEL=qwen-plus
QWEN_VL_MODEL=qwen-vl-max-latest
STATA_EDITION=mp
参数说明
DASHSCOPE_API_KEY：阿里百炼 API Key
DASHSCOPE_API_BASE：DashScope OpenAI 兼容接口地址
QWEN_TEXT_MODEL：文本模型，建议用于变量识别与报告生成
QWEN_VL_MODEL：多模态模型，可用于图像/图表识别
STATA_EDITION：Stata 版本，如 mp、se
数据输入

将待分析的 Excel 文件放入：

input/

程序会默认读取该目录下最新修改的 Excel 文件。

支持格式：

.xlsx
.xls
运行方式
python main.py

或使用你当前的 uv 方式：

uv run python main.py
输出结果

程序运行后，会在 output/时间戳目录/ 下生成：

variable_mapping.json：变量映射结果
*.log：各分析步骤日志
*.png：图表文件
*.do：Stata 可复现脚本
分析报告_时间戳.docx：最终 Word 报告
支持的数据类型
1. 面板数据

例如：

企业-年份
城市-年份
省份-年份

若系统成功识别 panel_id 和 time_var，则可自动执行面板分析。

2. 横截面数据

例如：

问卷调查
居民消费调查
单期样本企业数据

若未识别到时间变量，则自动跳过面板分析。

当前分析模块

已实现：

描述性统计
Pearson 相关分析
VIF 检验
OLS / Logit / Probit 基准回归
FE / RE 面板回归
Hausman 检验
替代因变量稳健性检验
分组异质性分析
2SLS 工具变量分析
Word 报告自动写作
图表自动解读
注意事项
1. 不同数据类型并不都适合面板分析

如果是横截面问卷数据，没有时间变量，程序会跳过面板分析。

2. 并不是所有数据都适合 2SLS

若工具变量不满足识别条件，2SLS 可能失败或被自动跳过。

3. 分类变量处理

对于 gender、city、edu 等分类变量，程序会尽量保留并在 Stata 中编码处理。

4. 模型输出需要人工复核

自动化结果适合：

初步分析
教学演示
项目原型
辅助实证研究

正式论文或高要求项目中，仍建议研究者手动复核模型设定、变量定义与解释逻辑。

常见问题
1. 提示 DASHSCOPE_API_KEY 未配置

请检查 .env 文件是否存在，并确认 Key 正确。

2. 提示 Arrearage

说明阿里百炼账户欠费或余额不足，请先检查账户状态。

3. 提示 access_denied

说明当前账号对某个模型没有权限，建议切换到可用模型或检查模型权限。

4. Stata 初始化失败

请确认：

本机已安装 Stata
pystata 可导入
STATA_EDITION 与本机版本匹配
5. string variables not allowed in varlist

说明字符串变量直接进入了 Stata 数值分析流程，通常需要编码或使用因子变量。

开发计划

后续可继续扩展：

自动识别分类变量并生成更优模型公式
自动筛选控制变量
自动判断更适合的模型类型
更专业的学术图表解读
更强的报告模板定制能力
FastAPI 接口封装
Web 前端交互界面
安全说明

请不要上传以下内容到 GitHub：

.env
真实 API Key
原始数据文件
output/ 分析结果
本地虚拟环境 .venv/

建议使用 .gitignore 进行排除，并提供 .env.example 作为示例配置。

License

可根据你的需要填写，例如：

MIT License

或者暂时写：

All rights reserved.