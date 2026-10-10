# MolStructBench 复现

遵循 README 对应版本的安装命令。所有路径由当前仓库或用户参数确定，无个人绝对路径。
WITH_HARNESS 保留标准 OpenCode Agent Profile A；WITHOUT_HARNESS 不执行 Solver，
只提供 public messages、gold 和独立官方 scorer，允许使用自己框架生成标准预测文件。
两个版本 score 与科学数据一致。新实验不得把 gold 放入模型上下文；open-gold 无隐藏测试性质。

设置 DASHSCOPE_API_KEY 后 molstructbench score --predictions predictions.jsonl --output scores/model；
没有 key 且缺票时 pending，恢复只补缺失票。--offline 仅复用严格验证缓存。
python scripts/reproduce_history.py --output results/history 对五组历史答案逐题评分后比较归档断言，
完全没有 Solver / 新 Judge API 调用。已有科学分数与原版一致。所有历史证明文件仍保留旧 ID。
