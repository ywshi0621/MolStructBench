# Open-gold local distribution (v1.0)

- 更新英文技术报告和五模型榜单说明；科学数据、评分规则及模型分数保持不变。


- 合并完整 gold / accepted variants / scorer，官方 score 命令改为本地运行，无维护者评分服务依赖。
- 发布原始五模型答案与 Judge 归档票；统一 evidence snapshot 与 wire serializer，严格验证原始 request hash，不改票/不改规则/不重跑 Solver。
- 增加独立 Judge checkpoint/resume、pending 和可验证缓存；新增真实 OpenCode+工具的 HTTP fixture 验收、单 ZIP 新目录安装与离线复现。

# v1.0 (2026-10-09)

- 科学评分协议、Judge模型/参数/模板/三票median、private gold、accepted variants、三dataset等权聚合均不变。
- 使用现有1440条预测和1665条已完成Judge votes离线生成五模型正式分数；不调用Solver或Judge API。
- 沿用rc3运行预算，历史配置和provenance保留；公开包与私有评分端分别交付。
- 公开CLI/评分端、完整性、回归、gold和hash检查重新执行；未验证扩展事项独立列为限制。

# 1.0.0-rc3

- 用户授权统一放宽未来 Solver 时限：网络 300→1800 秒、整题 1800→7200 秒、科学工具 60→180 秒。
- 工具 CPU 限制跟随有效工具时限；MCP 返回/清理宽限 10 秒，不增加工具实际执行时间。
- 所有 provider 使用同一 Profile A；次数、token、内存、权限、题目、gold、scorer 与聚合不变。
- Judge 缺失票已补齐 1665/1665；私有评分端统一使用 1800 秒网络等待，不更改 high reasoning 科学请求。
- 现有五模型没有重新运行 Solver；其历史配置继续披露，不冒充新时限实验。

# 1.0.0-rc2

- 整理现有 OpenCode 1.2.27 loop；新增 scibench eval/score 与 Chat/Responses transport adapter。
- 固定 Core-288 public data 和48个 task catalogs；移除公开运行路径对940 FULL/个人绝对路径的依赖。
- 公开数据、题目、科学 scorer/Judge protocol 与 rc1 不变；不重跑已有五模型 Solver。
- 私有 accepted variants 通用清理 stale atom_mask/reference/source metadata，合法评分目标不变。
- conformer-energy 仅在 catalog/report 说明为 stored-energy comparison control，不改变题目及主榜权重。
