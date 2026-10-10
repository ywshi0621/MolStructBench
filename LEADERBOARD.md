# MolStructBench Reference Leaderboard

Version 1.0 · 288 fixed questions · Profile A agent runs.

Scores are computed from six-question task-unit means, then domain means, then an equal-weight mean of Native3D, 3D→2D, and Pure2D. All models use the same official scorer.

| Model | MolStructBench Score | Native3D | 3D→2D | Pure2D |
| --- | ---: | ---: | ---: | ---: |
| GPT-6 Astra | 98.78 | 100.00 | 97.40 | 98.96 |
| Kimi K3 | 95.66 | 95.83 | 93.23 | 97.92 |
| DeepSeek V4 Pro 0813 | 93.92 | 91.67 | 91.15 | 98.96 |
| Qwen3.8-Max | 90.28 | 93.75 | 87.50 | 89.58 |
| GLM-5.3-Max | 87.38 | 85.42 | 85.42 | 91.32 |

Values are on a 0–100 scale. Deterministic, semantic, and micro averages are secondary metrics in [the complete results](examples/history/leaderboard.csv). The [48-task breakdown](examples/history/task_breakdown.csv) provides the detailed comparison.

These reference results use the packaged historical predictions and archived judge votes. Reproduce them without API calls:

```bash
python scripts/reproduce_history.py --output results/history
```

See the [technical report](docs/technical_report.md) for methods and task-level analysis.
