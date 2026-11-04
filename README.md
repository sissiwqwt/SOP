# SOP-UQ 学生项目

任务介绍见 [题面](docs/problem_statement.pdf)，项目介绍和操作说明见 [考生操作手册](docs/candidate_manual.pdf)。

首次使用：准备好环境与连接信息，打开 [quick_start_cn.ipynb](scripts/quick_start_cn.ipynb) 或 [quick_start.ipynb](scripts/quick_start.ipynb)，使用试用 token 运行示例。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [题面](docs/problem_statement.pdf) | 任务定义、研究目标和提交要求 |
| [考生操作手册](docs/candidate_manual.pdf) | 项目介绍、正式操作步骤、CSV 格式、工具与预算、业务规则和评分细则 |
| Quick Start：[quick_start_cn.ipynb](scripts/quick_start_cn.ipynb) / [quick_start.ipynb](scripts/quick_start.ipynb) | 连接服务、读取数据、运行 baseline，完成采集、拟合与提交 |
| [Baseline 示例](scripts/baseline_example.ipynb) | 离线比较六种风险方法与转人工阈值；另附可选的模型部署说明 |

## 准备环境与连接

助教会提供五项连接信息：考官地址、试用 token、正式 token、模型地址、模型 token。已有模型 API 时直接连接即可，无需自行部署千问。

使用 conda（Miniconda、Miniforge 或 Anaconda）时，在仓库根目录的 bash 或 zsh 中运行（Windows 请用 WSL）。将下面的占位文字替换为收到的完整地址和 token：

```bash
source conda_env.sh   # 首次按 environment.yml 创建环境 sii_uq，以后只激活
export SOP_EXAMINER_URL="助教提供的完整考官 URL"
export SOP_EXAMINER_TOKEN="本队试用 token"
export SOP_MODEL_URL="助教提供的完整模型 URL"
export SOP_MODEL_TOKEN="模型 token"
jupyter notebook scripts/quick_start_cn.ipynb
```

试用 token 用于熟悉流程，测试提交只检查格式，不评分、不占正式提交次数；正式 token 用于计分。用正式 token 跑示例会占用后续提交次数。正式运行步骤见操作手册。

不用 conda 时，需要 Python 3.11 及以上（Debian/Ubuntu 另装 `python3-venv`）：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e "./src[notebook]"
```

之后配置上面的连接信息并打开 Notebook。服务协议为 **3.0**，主数据格式为 **2.1**。

## 数据文件

JSONL 文件使用 UTF-8 编码，每行一个 JSON 对象；三类业务在每个划分中数量相等。

| 文件（相对于 `data/`） | 题数 | 用途 |
| --- | ---: | --- |
| `train/train.jsonl` | 360 | 学习风险模型、历史错误率 |
| `train/cal_fit.jsonl` | 120 | 概率校准 |
| `train/cal_select.jsonl` | 60 | 选择查询与转人工阈值 |
| `train/dev.jsonl` | 120 | 验证、误差分析和调参 |
| `test/cases.jsonl` | 360 | 无标签测试输入，其中 72 题允许交互 |
| `test/initial_M9.jsonl` | 360 | 同一批测试题的冻结初始作答、四次采样、工具历史和对话 |
| `manifest.json` | — | 数据批次、行数与 SHA-256 |

前四份文件共 **660 道有标签练习题**，包含标准答案 `label` 和老师提供的 Qwen 初始作答 `answer`、风险、采样与轨迹，其中 659 条完成、1 条失败。

两份测试文件按 `case_id` 对应同一批 **360 道题**。冻结的初始作答是模型回答，**不是标准答案**；学生端不包含测试题的标准答案。`dev` 与测试题均包含一半标准条件、一半偏移条件，单题不标注条件。

### 可选：直接使用老师提供的初始作答

Quick Start 演示完整采集流程。若希望省去重新生成初始作答，可以直接整理已有记录、拟合查询前风险：

```bash
python data/view_data.py data/train/train.jsonl
python scripts/prepare_labeled.py
sop-candidate fit --data data --trajectories .runs/provided_initials --output .runs/provided_calibrator.json
```

这些记录只有查询前轨迹。需要训练查询后的风险模型时，仍按 Quick Start 第 5 节采集有标签题的查询后轨迹。

## 代码入口

| 入口 | 用途 |
| --- | --- |
| `scripts/run_test.py` | 提交 CSV；`--local` 为有标签结果本地评分，`--submissions` 查看提交历史 |
| `scripts/prepare_labeled.py` | 将随数据提供的初始作答导出为风险拟合所用的轨迹文件 |
| `sop-candidate` | 命令行：`collect`、`fit`、`run`、`score`、`submit` |
| `src/test_client/` | 考官与模型客户端、CSV 格式、评分规则 |
| `src/baselines/` | agent、风险估计、查询与转人工策略、运行器 |
| `src/baselines/resources/` | 各业务的 SOP、工具参数和 [业务规则](src/baselines/resources/business_rules.md) |
| `src/qwen_server/` | 可选的模型服务；`profiles/` 和 `runtime.*.json` 为部署配置 |

## 提交与成绩

- 每份 `results.csv` 每道测试题一行。列名、填写要求和提交步骤见操作手册。
- 每队最多 **5 次有效提交**。格式错误或重复提交同一已评分文件不占次数。
- 初始风险取首次正式测试 oracle 查询之前的最佳 p 成绩。首次成功查询后，**p 不再更新，只更新 q/r 和决策成绩**。
- q/r 和决策成绩使用本次提交的结果及当时费用；三项等权平均，最终取各次有效提交的最高总成绩。
- 测试题的工具和 oracle 费用累计，换方法或重跑不会清零；有标签题可以重新打开练习。计费和评分细则见操作手册，考官 `/spec` 返回当前配置。

学生向考官提交 CSV 后，成绩自动同步到大屏；大屏展示当次成绩和历史最高成绩。教师仍会结合细分指标、报告和答辩进行最终评价。

评分反馈用于评估方法，不得用来推断测试标签；试用 token 读到的测试真值只用于熟悉流程，不用于正式提交。

提交并保存完整报告，或仅查看历史：

```bash
python scripts/run_test.py results.csv --output .runs/submission-report.json
python scripts/run_test.py --submissions --output .runs/submission-history.json
```

第一条会提交 CSV，第二条只查询历史。`report.grades` 是本次有效成绩，`report.submission_grades` 是该份 CSV 独立换算的成绩；原始细分指标保留在报告中。
