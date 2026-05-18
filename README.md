# AutoStata-Insight

Language: **English** | [中文](README.zh-CN.md)

AutoStata-Insight is an empirical-research automation tool. Starting from an Excel dataset, it can run data reading/cleaning, variable mapping, Stata analysis, chart/table export, and Word report generation.

It is suitable for panel data, cross-sectional survey data, econometrics teaching demos, prototypes, and first-pass empirical analysis. Formal papers still require human review.

## Architecture

```mermaid
flowchart LR
  Researcher["Researcher"] --> Excel["Excel input"]
  Excel --> Metadata["Metadata agent"]
  Metadata --> Mapping["Variable mapping JSON"]
  Mapping --> DoFile["Generated Stata .do file"]
  DoFile --> Stata["PyStata / Stata engine"]
  Stata --> Outputs["Tables, logs, charts"]
  Outputs --> Reporting["Reporting agent"]
  Reporting --> Word["Word empirical report"]
```

## Demo GIF

![Demo GIF](docs/assets/demo.gif)

## Portfolio Metrics

Local report-pipeline baseline for portfolio review. Re-benchmark with the target dataset, Stata edition, and model before claiming production performance.

| Metric | Current portfolio baseline | Measurement note |
| --- | ---: | --- |
| Latency | First analysis step target `< 10s` | Excel scan + schema preview on local machine |
| RAG hit rate | `N/A` | Structured data analysis, not vector retrieval |
| Agent success rate | Target `>= 90%` | Variable-role mapping accepted without manual correction on benchmark sheets |
| Report generation time | Target `< 120s` | Excel to `.do` + Stata outputs + Word report |
| Cost | `~$0.01-$0.08 / report` | Depends on Qwen text/VL calls and chart-commentary volume |

## Features

- Read the latest Excel file from `input/`.
- Recognize Chinese headers and map them to Stata-compatible variable names.
- Infer dependent variables, independent variables, controls, panel IDs, and time variables.
- Run descriptive statistics, correlation, VIF, OLS/Logit/Probit, FE/RE panel regression, Hausman tests, robustness checks, heterogeneity analysis, and 2SLS when applicable.
- Generate reproducible `.do` files and Word reports.

## Requirements

- Python 3.12+
- Local Stata installation with working PyStata
- DashScope/Qwen API key

## Run

```bash
pip install -r requirements.txt
python main.py
```

or:

```bash
uv sync
uv run python main.py
```

## Outputs

Each run writes artifacts under `output/<timestamp>/`:

- `variable_mapping.json`
- Stata logs
- charts and tables
- generated `.do` file
- Word empirical report
