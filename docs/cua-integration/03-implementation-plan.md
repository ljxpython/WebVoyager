# 03 实施计划

## 阶段 0：约束确认

确认这些约束不变：

- CUA 项目只读，不改源码。
- 当前项目调用 CUA 编译产物。
- CUA 原始 runs 保留。
- 当前项目产出 WebVoyager evaluator 可读格式。

成功标准：

```text
能手动执行一条 CUA run，并在当前项目中转换出 task<id>/interact_messages.json + screenshotN.png
```

## 阶段 1：单任务 runner

新增脚本：

```text
scripts/cua_eval/run_and_convert.py
```

输入参数：

```bash
uv run python scripts/cua_eval/run_and_convert.py \
  --tasks data/tasks_test.jsonl \
  --limit 1 \
  --cua-bin /path/to/cua/dist/cli/bin.js \
  --raw-runs-dir results/cua_raw_runs \
  --converted-dir results/cua_webvoyager \
  --max-steps 3 \
  --max-images 1
```

内部流程：

1. 读取第一条任务。
2. 拼接 CUA task prompt。
3. 调用 `node <cua-bin> run ...`。
4. 找到新增 runId。
5. 读取 `steps.json`。
6. 复制/转换截图。
7. 生成 `interact_messages.json`。
8. 写入 `summary.jsonl`。

验证：

```text
results/cua_webvoyager/task<id>/interact_messages.json 存在
results/cua_webvoyager/task<id>/screenshot1.png 存在
```

## 阶段 2：转换器健壮性

要处理：

- CUA run 失败但有 steps。
- 没有 screenshotPath。
- screenshotPath 是相对路径。
- 源截图是 jpg。
- 多个 step 复用同一张截图。
- CUA 没有最终答案。

转换策略：

```text
能保留多少证据就保留多少证据
不要因为某一步截图缺失导致整个转换器崩掉
```

验证：

- 用已有 CUA `runs/35e4ea39/steps.json` 这种失败样本测试转换。
- 失败样本也应能生成 WebVoyager 格式，最终评测可以判失败。

## 阶段 3：自动评测器扫描模式

修改当前项目：

```text
evaluation/auto_eval.py
```

新增参数建议：

```bash
--scan_tasks
--summary_file results/cua_webvoyager/auto_eval_summary.jsonl
```

最小改动：

```python
if args.scan_tasks:
    scan all child dirs with interact_messages.json
else:
    keep original WebVoyager fixed-site behavior
```

这样兼容原逻辑，不把老评测流程搞炸。

## 阶段 4：批量任务

支持：

```bash
--limit 10
--start 0
--include_web GitHub,ArXiv
--exclude_web Booking,Google Flights
```

优先剔除：

- 时间敏感任务。
- 需要登录任务。
- 反爬严重网站。
- 需要视频播放任务。

第一批建议：

```text
GitHub
Google Search
ArXiv
Cambridge Dictionary
Wolfram Alpha
```

## 阶段 5：公平性配置

先定义两个 profile：

### profile: gui

目标是尽量接近 WebVoyager：

```text
允许：截图、鼠标、键盘、滚动、等待、打开浏览器
不鼓励：shell、osascript、HTTP 抓取
```

由于当前 CUA CLI 未确认能完全禁用 `shell_exec` 和 `osascript_exec`，第一版只能靠 prompt 约束和日志审计。

### profile: tool_augmented

保留 CUA 默认能力：

```text
允许：CUA 所有工具
```

这个档位用来评估 CUA 作为完整 Computer Use Agent 的能力，但不能和 WebVoyager baseline 直接公平对比。

## 阶段 6：汇总指标

至少输出：

- 总任务数。
- CUA 自身 success。
- 自动评测 success。
- 平均步数。
- 平均耗时。
- 平均 token。
- 无最终答案比例。
- 无截图比例。
- CUA 工具使用分布。

工具使用分布很重要。比如：

```json
{
  "mouse_click": 12,
  "clipboard_type": 5,
  "shell_exec": 3,
  "osascript_exec": 1,
  "done": 1
}
```

如果 `shell_exec` 很多，这批结果就不能叫纯网页 GUI 评测。

## 推荐第一步

第一步已经完成：单任务 CUA run、已有 run 转换、WebVoyager evaluator dry-run 都已跑通。

当前建议的下一步不是直接大批量烧 token，而是先挑 3 到 5 条低风险任务做小批量：

```bash
uv run python scripts/cua_eval/run_and_convert.py \
  --tasks data/WebVoyager_data.jsonl \
  --include-web GitHub,ArXiv,Cambridge Dictionary \
  --limit 3 \
  --max-steps 20 \
  --max-images 3
```

通过后再调用真实 `auto_eval.py`。原因很简单：转换格式错了，后面自动评测全是垃圾输入，烧 token 还没结论。
