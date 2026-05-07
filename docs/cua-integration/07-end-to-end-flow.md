# 07 端到端流程讲解

这份文档从整体视角解释当前项目如何在 **不修改 CUA 源码** 的前提下，用 WebVoyager 任务集评测 CUA 的网页操作能力。

核心结论：

```text
WebVoyager 负责提供任务和自动评测格式。
CUA 负责作为黑盒 Agent 执行网页操作。
当前项目新增的适配层负责调度 CUA、转换轨迹、汇总结果。
auto_eval.py 负责用视觉模型判断任务是否真正完成。
```

## 1. 总体链路

完整链路如下：

```text
WebVoyager JSONL 任务
  -> scripts/cua_eval/run_and_convert.py
  -> node <CUA_BIN> run <task prompt>
  -> CUA 操作 Google Chrome
  -> CUA 生成 raw run: steps.json / steps.jsonl / screenshots
  -> run_and_convert.py 转换为 WebVoyager 结果目录
  -> evaluation/auto_eval.py --dry_run 检查格式
  -> evaluation/auto_eval.py 调用视觉模型做真实判定
  -> summary.jsonl / auto_eval_summary_real.jsonl 汇总结果
```

这条链路里，CUA 项目只被当成命令行黑盒：

```text
node <CUA_BIN> run ...
```

当前 WebVoyager 项目不 import CUA 内部模块，不改 CUA TypeScript 源码，也不依赖 CUA 的内部类型。

## 2. 每个模块负责什么

### WebVoyager 任务文件

任务输入是 JSONL，每行一个任务：

```json
{"web_name":"GitHub","id":"GitHub--16","ques":"Find the GitHub Skill section and how many courses are under the 'First day on GitHub' heading.","web":"https://github.com/"}
```

适配层主要依赖这些字段：

- `id`：生成结果目录名，例如 `taskGitHub--16`。
- `web_name`：记录网站名称，主要用于筛选和汇总。
- `web`：任务起始 URL。
- `ques`：自然语言任务指令。

### `scripts/cua_eval/run_and_convert.py`

这是当前适配的核心脚本，做两件事：

1. 调用 CUA 执行任务。
2. 把 CUA raw run 转成 WebVoyager evaluator 能读的格式。

它支持两种模式：

```text
run 模式：
读取 WebVoyager task -> 调 CUA -> 转换结果。

convert-only 模式：
不调 CUA，只把已有 CUA run 转成 WebVoyager 结果。
```

### `config/cua_eval.json`

这是当前项目里的 CUA 专用配置，不放在 CUA 项目里。

它的作用是固定评测边界：

- 保留截图：`artifacts.pruneAfterRun=false`。
- 关闭 CUA knowledge / records / brain，减少额外变量。
- 关闭 `shellSh`。
- 保留工具使用日志，方便审计是否出现增强工具。

注意：第一版仍是 `gui-biased`，不是严格的 `vision-only`。因为 CUA 的 `shell_exec` / `osascript_exec` 是否能完全禁用，还需要继续读 CUA 工具注册逻辑或增加更强约束。

### `evaluation/auto_eval.py`

这是 WebVoyager 原项目的自动评测器。我们做了兼容增强：

- 支持 `.env`。
- 支持 OpenAI-compatible `api_base`。
- 支持 `--scan_tasks`，扫描任意包含 `interact_messages.json` 的结果目录。
- 支持 `--dry_run`，只检查格式，不调用模型。
- 支持 `--summary_file` 输出 JSONL 汇总。
- 支持有限重试，避免接口错误时无限卡住。

## 3. CUA 任务 prompt 如何构造

WebVoyager 原始任务只有 URL 和自然语言问题。CUA 需要更明确的执行边界，所以适配器会包装成类似这样的 prompt：

```text
You are being evaluated on a WebVoyager web browsing task.

Open this URL first:
<web>

Complete this task:
<ques>

Rules:
- Use the browser UI to complete the task.
- Use Google Chrome as the browser for this benchmark.
- Treat this task as independent from any previous task.
- At the start of the task, focus Google Chrome and navigate the active tab to the exact URL above using the browser address bar.
- Do not rely on pages, forms, answers, or browser state left from previous tasks.
- Focus only on the current task instruction; do not continue or reuse goals from any previous task.
- Do not use shell, scripts, direct HTTP requests, or filesystem shortcuts to obtain the answer unless the evaluation profile explicitly allows tool augmentation.
- When the task is complete, call done with the final answer in the reason.
- The done reason must contain the answer, not just "task completed".
```

这里最关键的是三条：

- 强制使用 Google Chrome。
- 每条任务都当成独立任务。
- 开始时必须用地址栏导航到指定 URL。

原因是正式验证时发现，如果不固定浏览器，CUA 可能打开 Safari 并触发 Cloudflare 人机验证；如果不强调独立任务，浏览器残留状态可能污染下一条任务。

## 4. CUA raw run 是什么

CUA 每跑一条任务，会生成一个 raw run 目录：

```text
results/cua_validation_raw_v4/
└── taskGitHub--16/
    └── <runId>/
        ├── steps.json
        ├── steps.jsonl
        ├── run.meta.json
        ├── step_001_after.jpg
        ├── step_002_after.jpg
        └── ...
```

其中最重要的是：

- `steps.json`：完整结构化结果。
- `steps.jsonl`：逐步增量日志。
- `step_*.jpg`：每步或关键步骤截图。

每个 step 通常包含：

- `actionName`：CUA 选择的动作，例如 `mouse_click`、`clipboard_type`、`done`。
- `actionArgs`：动作参数。
- `tool.success`：工具是否执行成功。
- `screenshotPath`：该步对应截图。
- `llm.usage`：token 使用量。
- `durationMs`：步骤耗时。

## 5. 为什么要转换格式

WebVoyager 原始 evaluator 不认识 CUA 的 `steps.json`。它只认这种目录：

```text
results/<run>/
└── task<id>/
    ├── interact_messages.json
    ├── screenshot1.png
    ├── screenshot2.png
    └── ...
```

所以 `run_and_convert.py` 会做转换：

```text
CUA steps.json / steps.jsonl
  -> interact_messages.json

CUA step_*.jpg
  -> screenshot1.png / screenshot2.png / ...

CUA done.reason
  -> WebVoyager 最后一条 Action: ANSWER
```

转换后的目录示例：

```text
results/cua_validation_webvoyager_v4/
└── taskGitHub--16/
    ├── interact_messages.json
    ├── cua_steps.json
    ├── screenshot1.png
    ├── screenshot2.png
    └── ...
```

## 6. `interact_messages.json` 里有什么

这个文件是 WebVoyager evaluator 的核心输入之一。

转换器会写入：

1. system 消息：说明这是 CUA 转换轨迹。
2. user 消息：包含原始任务，格式保持 WebVoyager evaluator 期待的 `Now given a task: ...`。
3. assistant 消息：每个 CUA step 的动作摘要。
4. 最后一条 assistant 消息：`Action: ANSWER; <final_answer>`。

WebVoyager evaluator 最依赖的是：

```text
第 2 条消息能解析出任务。
最后一条消息能解析出最终答案。
截图文件能按 screenshotN.png 找到。
```

中间的 CUA step 不需要伪造成 WebVoyager 的 Selenium 动作编号。

## 7. dry-run 和真实 auto_eval 的区别

### dry-run

命令：

```bash
uv run python evaluation/auto_eval.py \
  --process_dir results/cua_validation_webvoyager_v4 \
  --scan_tasks \
  --dry_run \
  --summary_file results/cua_validation_webvoyager_v4/auto_eval_dry_run.jsonl
```

dry-run 只检查：

- `interact_messages.json` 是否存在。
- 第 2 条消息是否有任务标记。
- 最后一条消息是否有 `Action: ANSWER`。
- 是否存在 `screenshotN.png`。

dry-run 不调用外部模型，不上传截图，不消耗 token。

### 真实 auto_eval

命令：

```bash
uv run python evaluation/auto_eval.py \
  --process_dir results/cua_validation_webvoyager_v4 \
  --scan_tasks \
  --max_attached_imgs 3 \
  --summary_file results/cua_validation_webvoyager_v4/auto_eval_summary_real.jsonl
```

真实 auto_eval 会把以下内容发给 `.env` 里配置的视觉模型：

- 任务文本。
- CUA 最终回答。
- 最后几张截图。

模型会输出：

```text
SUCCESS
```

或：

```text
NOT SUCCESS
```

这就是 WebVoyager 项目的自动评测方式。它本质上是“视觉模型裁判”，不是人工标注真值，所以正式报告最好再抽样人工复核。

## 8. 输出结果怎么看

### CUA 自身汇总

`run_and_convert.py` 会写：

```text
results/cua_validation_webvoyager_v4/summary.jsonl
```

每行一个任务，重点字段：

- `task_id`：任务 ID。
- `cua_success`：CUA 自己是否认为完成。
- `cua_reason`：CUA 的完成原因。
- `final_answer`：交给 WebVoyager evaluator 的最终答案。
- `steps`：CUA 执行步数。
- `duration_ms`：步骤耗时汇总。
- `llm_tokens.total`：CUA 执行阶段 token 汇总。
- `screenshots`：转换出的截图数量。
- `tool_counts`：工具使用分布。
- `failed_tool_steps`：工具失败次数。
- `augmented_tools`：是否使用 shell、osascript、HTTP 等增强工具。

### 自动评测汇总

真实 auto_eval 会写：

```text
results/cua_validation_webvoyager_v4/auto_eval_summary_real.jsonl
```

每行一个任务：

```json
{"task_dir":"results/cua_validation_webvoyager_v4/taskGitHub--16","auto_eval_res":1,"dry_run":false,"reason":null}
```

字段含义：

- `auto_eval_res=1`：视觉模型判定成功。
- `auto_eval_res=0`：视觉模型判定失败。
- `auto_eval_res=null`：评测模型输出异常或接口失败。
- `reason`：异常原因，正常成功时通常是 `null`。

## 9. 我们当前验证过什么

当前已完成一轮 3 条任务的小批量验证：

```text
Cambridge Dictionary--0
ArXiv--10
GitHub--16
```

v4 结果：

```text
任务数：3
CUA 自评成功：3/3
auto_eval 真实评测成功：3/3
平均步数：12.67
增强工具：无 shell / osascript / HTTP
工具失败：2 次，均为 GitHub 任务里的 mouse_scroll 失败，CUA 用 PageDown 恢复
```

这说明当前适配链路已经可用于继续扩大验证规模。

## 10. 当前边界和风险

### 1. CUA success 不能单独当最终成功率

`cua_success=true` 只是 CUA 自己认为完成。最终评测应优先看 `auto_eval_res`，必要时人工复核截图。

### 2. auto_eval 是模型裁判

视觉模型裁判可能误判。它适合批量自动化，但关键结论最好抽样人工复核。

### 3. 浏览器状态仍可能影响结果

我们已经通过 prompt 要求每条任务重新用 Chrome 地址栏导航，但浏览器登录态、扩展、弹窗、Cookie、地区设置仍可能影响网页表现。

### 4. macOS 滚动工具有失败风险

验证中出现过 `mouse_scroll` 失败。CUA 可以用 `PageDown` 恢复，但这仍应记录在 `failed_tool_steps` 里。

### 5. 目前不是严格 vision-only

当前 profile 是 `gui-biased`。结果里会审计 `augmented_tools`，如果出现 shell、osascript 或 HTTP，就不能和纯 GUI baseline 混在一起比较。

## 11. 推荐后续流程

下一步建议这样扩大验证：

1. 先选 10 条低风险任务。
2. 跑 CUA + 转换。
3. 跑 dry-run。
4. 跑真实 auto_eval。
5. 抽样人工看 2 到 3 条成功样本和所有失败样本。
6. 再扩大到 30 条或更多。

示例命令：

```bash
uv run python scripts/cua_eval/run_and_convert.py \
  --tasks data/WebVoyager_data.jsonl \
  --include-web GitHub,ArXiv,Cambridge Dictionary \
  --limit 10 \
  --max-steps 20 \
  --max-images 3 \
  --raw-runs-dir results/cua_validation_raw_10 \
  --converted-dir results/cua_validation_webvoyager_10
```

格式检查：

```bash
uv run python evaluation/auto_eval.py \
  --process_dir results/cua_validation_webvoyager_10 \
  --scan_tasks \
  --dry_run \
  --summary_file results/cua_validation_webvoyager_10/auto_eval_dry_run.jsonl
```

真实自动评测：

```bash
uv run python evaluation/auto_eval.py \
  --process_dir results/cua_validation_webvoyager_10 \
  --scan_tasks \
  --max_attached_imgs 3 \
  --summary_file results/cua_validation_webvoyager_10/auto_eval_summary_real.jsonl
```

## 12. 一句话总结

当前 CUA 适配不是把 CUA 改造成 WebVoyager Agent，而是在 WebVoyager 外面加了一层黑盒评测适配：

```text
WebVoyager 出题和评分，CUA 负责执行，适配层负责把两边格式接上。
```

这让我们能在不改 CUA 的情况下，用 WebVoyager 的任务和自动评测流程评估 CUA 的网页操作能力。
