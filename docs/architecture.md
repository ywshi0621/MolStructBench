# MolStructBench 架构

公共 benchmark_core/io 和 limiter 不依赖 Agent；evaluator 与 local_score 是两版共享的
独立官方评分组件。WITH_HARNESS 的 runner 保留 OpenCode CLI + provider adapters +
scientific_shell；WITHOUT_HARNESS 不包含 runner、MCP、OpenCode 或任何 Solver 执行代码。
两版读取完全相同 public data、gold、accepted variants、Judge prompt/config 和 evidence snapshot。
显示名称的更改不进入 frozen Solver/Judge 科学请求；旧 IDs 和兼容 CLI alias 保留。
