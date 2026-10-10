# MolStructBench

**Molecular Structure Understanding and Grounding Benchmark** · 分子结构理解与定位评测

v1.0 · 带 Harness 完整版 · open-gold · 本地自动评分

覆盖 Native3D、3D→2D、Pure2D，固定 288 道题、48 个 dataset×task units、每 unit 6 题。
包含分子属性、功能团、结构定位/grounding、立体化学、药化与结构知识任务。
本次只改发布名称和工程打包；题目、gold、选样、科学评分规则与五模型历史答案均不变。

[English technical report](docs/technical_report.md) · [Reference leaderboard](LEADERBOARD.md)

## 选择版本

| 版本 | 数据/gold/官方 Scorer | OpenCode Agent + scientific_shell |
|---|---|---|
| WITH_HARNESS | 完整 | 包含 |
| WITHOUT_HARNESS | 完整 | 不包含，接入自己的框架 |

两版的科学数据与评分相同，分别使用独立虚拟环境。详见 docs/EDITION.md。

## 安装（Linux / WSL，Python 3.10）

解压 ZIP 或 clone 相应仓库后进入目录。带 Harness 版须安装 python3.10-venv、
bubblewrap 和 curl；安装依赖需要网络。评分版只需 Python 依赖，无维护者评分服务。

```bash
bash scripts/install_environment.sh
source .runtime/venv/bin/activate
molstructbench --help
python scripts/verify_release.py
```

## 运行模型

复制 configs/chat.json、configs/responses.json 或 configs/local.json 为自己的
my_model.json，编辑 provider endpoint / model 参数，并设置对应 api_key_env。
原始发布文件受 hash 校验，不直接编辑。统一 Profile A 预算不得按模型改变。

```bash
cp configs/chat.json my_model.json
# 编辑副本；不要把密钥写入文件
export OPENAI_API_KEY='YOUR_SOLVER_KEY'
molstructbench eval --model MODEL_ID --config my_model.json --output runs/model
molstructbench eval --model MODEL_ID --config my_model.json --output runs/model --resume
```

OpenCode 原生 function tool calling + scientific_shell；无原生工具能力的接口明确拒绝。
源码仓库不含大型预编译程序，安装脚本按固定 v1.2.27 和 SHA256 获取 OpenCode。
测试脚本 scripts/test_cli_transport.py 可用本地 HTTP fixture 驱动真实工具多轮，
但 fixture 不是模型、不能证明任意供应商科学能力。完整宿主 Agent OS 审计未完成。

## 本地官方评分

```bash
export DASHSCOPE_API_KEY='YOUR_JUDGE_KEY'
molstructbench score --predictions predictions.jsonl --output scores/model
# 自动恢复同输入 checkpoint，只补缺失票
molstructbench score --predictions predictions.jsonl --output scores/model --resume
```

Deterministic 本地运行；semantic 使用冻结 qwen3.8-max、high reasoning、temperature
0.6、固定 prompt，三次独立匿名 Judge 取中位数。用户使用自己的 key，不需要官方
URL、token 或联系维护者。Judge 不看模型身份、轨迹、reasoning 或 tool history。
任务依据、等价表达、额外正确事实与矛盾处理遵守原冻结协议。

支持 --judge-cache PATH 和 --offline；缓存严格校验 request / prompt / 参数 hash，
失败 pending、不记 0。完整成功返回 0，pending 返回 3、官方总分 null，输入/hash
错误返回 2。输入改变须使用新输出目录。输出 final_results.json、per_sample_scores.jsonl、
48-task 和三数据集 breakdown、Judge 使用统计。

官方 headline：task-unit mean → dataset mean → 三 dataset 等权平均；
deterministic、semantic、micro 仅作 secondary metrics。

## 测试与历史复现（不调用任何 Solver 或付费 Judge）

```bash
python -m unittest discover -s tests -v
python scripts/gold_selftest.py
python scripts/reproduce_history.py --output results/history
```

包内 1440 条历史预测、1665 个原始 Judge 票可由同一 scorer 复现。expected 文件仅用于
结果比较，不作为计算输入。历史数据中的 scibench_ IDs、dataset IDs、Python 内部包名
与 scibench 命令别名保留兼容性，不改变 frozen prompt 或历史 request hash。

## 数据与评分隔离

完整 gold 在 data/benchmark_288_gold.jsonl；accepted variants、48-task specs、固定
selection、Judge public-evidence 快照和 hashes 全部包含。gold 公开后不再是隐藏测试集。
Solver 阶段只读取 public input；gold 和评分事实仅在本地评分阶段使用。
本仓库不附个人运行目录、缓存、机器日志或身份映射。

公开交付物经过姓名/账号/机器路径/API 密钥清理与扫描；通用 sandbox 路径如 /workspace
和 /home/agent 为运行协议，不是个人路径。详情见 docs/PRIVACY_AUDIT.json。
见 docs/technical_report.md、docs/ACCEPTANCE.json、PUBLIC_HASHES.json 和 SCORER_FREEZE.json。
软件源代码 MIT；第三方与数据权利说明见 LICENSE / NOTICE。
