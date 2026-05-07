# CUA 评测适配调研

这个目录记录如何在 **不修改 CUA 项目代码** 的前提下，用当前 WebVoyager 项目评测 CUA 的网页操作能力。

核心约束：

- 不改 CUA 项目的源码。
- 不 import CUA 的 TypeScript 内部模块。
- 只运行 CUA 已编译产物：`node dist/cli/bin.js ...`。
- 所有适配、调度、格式转换、评测汇总都放在当前 WebVoyager 项目里完成。

当前结论：**可行，推荐采用黑盒 Runner + 轨迹转换方案。**

当前第一版已经跑通：

- CUA 编译产物可由当前项目脚本调用。
- CUA raw run 可以转换成 WebVoyager evaluator 需要的 `interact_messages.json` 和 `screenshotN.png`。
- `evaluation/auto_eval.py --scan_tasks --dry_run` 可以读取转换后的目录。
- 单条 Cambridge Dictionary 任务在 `max-steps=30` 下跑通，CUA 返回最终分数 `2/6`。

## 文档顺序

1. [可行性评估](01-feasibility.md)：明确能不能做、为什么能做、主要风险是什么。
2. [适配设计](02-adapter-design.md)：说明 WebVoyager 侧需要新增哪些脚本、输入输出怎么映射。
3. [实施计划](03-implementation-plan.md)：拆成可验证的小步骤。
4. [计划清单](04-plan-checklist.md)：编码任务拆解和完成标准。
5. [测试清单](05-test-checklist.md)：每个阶段要验证什么，怎么判定过关。
6. [使用说明](06-usage.md)：用 uv 跑适配器、转换器和评测器。
