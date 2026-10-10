# MolStructBench

**Molecular Structure Understanding and Grounding Benchmark**

MolStructBench evaluates molecular reasoning through explanations, graph analysis, and precise localization of atoms, bonds, and three-dimensional regions. It contains **288 questions across 48 task units**, spanning Native3D, 3D→2D, and Pure2D. Tasks cover functional groups, stereochemistry, conformational geometry, molecular properties, scaffolds, and medicinal chemistry.

[Technical report](docs/technical_report.md) · [Full results](LEADERBOARD.md)

| Domain | Task units | Questions |
|---|---:|---:|
| Native3D | 8 | 48 |
| 3D→2D | 16 | 96 |
| Pure2D | 24 | 144 |

## Benchmark editions

| Repository | Data and local scorer | Agent harness |
|---|---|---|
| [MolStructBench](https://github.com/ywshi0621/MolStructBench) | Complete questions, gold, and official scoring | OpenCode + scientific_shell |
| [MolStructBench-Core](https://github.com/ywshi0621/MolStructBench-Core) | The same questions, gold, and official scoring | Integrate an external runner |

## Five-model results

![Five-model official scores](assets/leaderboard_overall.svg)

| Model | MolStructBench Score | Native3D | 3D→2D | Pure2D |
|---|---:|---:|---:|---:|
| GPT-6 Astra | 98.78 | 100.00 | 97.40 | 98.96 |
| Kimi K3 | 95.66 | 95.83 | 93.23 | 97.92 |
| DeepSeek V4 Pro 0813 | 93.92 | 91.67 | 91.15 | 98.96 |
| Qwen3.8-Max | 90.28 | 93.75 | 87.50 | 89.58 |
| GLM-5.3-Max | 87.38 | 85.42 | 85.42 | 91.32 |

Scores are reported on a 0–100 scale. The headline score gives equal weight to the three structural domains.

![Scores by structural domain](assets/leaderboard_domains.svg)

## Install

Linux or WSL with Python 3.10:

```bash
sudo apt-get update
sudo apt-get install -y python3.10-venv bubblewrap curl
bash scripts/install_environment.sh
source .runtime/venv/bin/activate
molstructbench --help
```

The environment includes OpenCode and a sandboxed scientific_shell with RDKit, NumPy, SciPy, pandas, and NetworkX.

## Evaluate a model

Choose an adapter configuration: `configs/chat.json` for Chat Completions, `configs/responses.json` for Responses, or `configs/local.json` for a local OpenAI-compatible endpoint. Configure the model and endpoint in a copy of the example. The harness uses native tool calling and multi-turn continuation under Profile A.

```bash
cp configs/chat.json my_model.json
export OPENAI_API_KEY='YOUR_SOLVER_KEY'
molstructbench eval --model MODEL_ID --config my_model.json --output runs/model
```

To continue from a checkpoint:

```bash
molstructbench eval --model MODEL_ID --config my_model.json --output runs/model --resume
```

Each sample has a separate session and workspace. The run writes `predictions.jsonl`, trajectories, tool statistics, and token usage. Use `runs/model/predictions.jsonl` as the input to local scoring.

## Local scoring

The official scorer combines deterministic evaluation with a frozen Qwen3.8-Max semantic judge. Semantic answers receive three independent, anonymous grades; the median determines the sample score. The judge uses high reasoning effort and temperature 0.6, following the published task contract and structured chemical facts.

```bash
export DASHSCOPE_API_KEY='YOUR_JUDGE_KEY'
molstructbench score --predictions predictions.jsonl --output scores/model
```

Resume an interrupted scoring run with `--resume`. Completed, validated votes can also be reused with `--judge-cache PATH`; `--offline` scores from a complete cache. Failed API requests remain pending for subsequent resume.

The scorer produces `final_results.json`, per-sample scores, three-domain and 48-task breakdowns, and judge usage statistics. The official score averages the six samples in each task unit, then the units in each domain, then the three domains with equal weight. Deterministic, semantic, and micro averages are provided as secondary metrics.

## Reference results and tests

The release includes 1,440 predictions and 1,665 archived judge votes from the five reference runs. Reproduce their scores locally:

```bash
python scripts/reproduce_history.py --output results/history
python -m unittest discover -s tests -v
python scripts/gold_selftest.py
```

## Data and task specifications

| Asset | Contents |
|---|---|
| `data/benchmark_288_public.jsonl` | Questions and solver input messages |
| `data/benchmark_288_gold.jsonl` | Complete scoring targets and structured facts |
| `data/task_specifications.json` | Contracts for all 48 task units |
| `data/selection_288_ids.txt` | Fixed evaluation IDs |
| `examples/history/` | Reference predictions, judge votes, and result breakdowns |

MolStructBench uses an open-gold release: questions and answers are available for scientific inspection and local evaluation. Solver execution reads the public inputs; gold and scoring facts are loaded in the separate scoring stage. The [technical report](docs/technical_report.md) describes the benchmark design, execution protocol, scoring, and task-level results.
