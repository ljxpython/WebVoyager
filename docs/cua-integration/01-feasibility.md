# 01 可行性评估

## 目标

用 WebVoyager 的任务集和评测器，评估 CUA 这个 Computer Use Agent 在真实网页任务上的表现。

预期链路：

```text
WebVoyager JSONL 任务
  -> 当前项目里的 CUA runner
  -> 调用 CUA 编译产物
  -> CUA 操作浏览器/桌面
  -> 读取 CUA runs/<runId>/steps.json
  -> 转换成 WebVoyager results 格式
  -> 使用 WebVoyager auto_eval.py 或人工复盘
```

## 约束

本方案坚持：

- CUA 是黑盒 Agent。
- 当前项目只通过命令行调用 CUA。
- 当前项目不修改 CUA 源码、不改 CUA prompt、不改 CUA runtime。
- 当前项目负责评测任务调度、结果整理、格式转换和评测汇总。

也就是说，适配层只依赖 CUA 的稳定外部接口：

```bash
node dist/cli/bin.js run <task> ...
node dist/cli/bin.js result --run-id <id> --runs-dir <dir>
```

## 已确认的 CUA 能力

CUA 编译产物支持：

```bash
node dist/cli/bin.js --help
node dist/cli/bin.js run --help
node dist/cli/bin.js result --help
```

关键能力：

- `run <task>`：执行自然语言任务。
- `--runs-dir <dir>`：指定运行产物目录。
- `--max-steps <n>`：限制最大步数。
- `--max-images <n>`：限制上下文图片数。
- `--model <name>`、`--provider <name>`、`--base-url <url>`、`--api-key <key>`：覆盖模型配置。
- `--stream`：以 SSE 格式输出运行事件。
- `result --run-id <id> --runs-dir <dir>`：读取指定 run 的 `steps.json`。

CUA 运行目录结构：

```text
runs/<runId>/
├── steps.json
├── steps.jsonl
├── run.meta.json
├── step_001.png 或 step_001.jpg
├── step_001_after.png 或 step_001_after.jpg
└── ...
```

`steps.json` 里包含：

- `runId`
- `task`
- `success`
- `reason`
- `steps`
- 每步的 `screenshotPath`
- 每步的 `actionName`
- 每步的 `actionArgs`
- 每步的工具执行结果
- LLM token 使用量

这些信息足够转换成 WebVoyager 的评测格式。

## WebVoyager 评测器最低输入要求

当前 `evaluation/auto_eval.py` 的 `auto_eval_by_gpt4v(process_dir, ...)` 依赖：

```text
process_dir/
├── interact_messages.json
├── screenshot1.png
├── screenshot2.png
└── ...
```

其中：

- `interact_messages.json` 第 2 条消息要包含 `Now given a task: ... Please interact with ...`。
- 最后一条 assistant 消息要包含 `Action: ANSWER; ...`。
- 截图文件名要符合 `screenshot(\d+).png`。

这说明 CUA 结果不需要完全模拟 WebVoyager 的每一步，只要满足评测器的最低格式，就能进入自动评测。

## 可行性结论

可行，理由：

1. WebVoyager 任务本身是自然语言 + 起始 URL，CUA 可以直接接收拼接后的任务。
2. CUA 能独立操作浏览器和网页。
3. CUA 产物包含每步截图和最终完成原因。
4. WebVoyager 自动评测器只依赖最终答案和最后若干张截图，不依赖 Selenium 内部状态。
5. 轨迹格式转换可以完全放在当前项目，不需要动 CUA。

当前实测结论：

- `max-steps=2` smoke run 已验证调度和转换链路。
- `max-steps=15` 可以到达 Cambridge Dictionary Image Quizzes / Animals 页面，但未完成任务。
- `max-steps=30` 完成 Cambridge Dictionary Easy Animals quiz，CUA 返回最终分数 `2/6`。
- 转换后的 `results/cua_webvoyager_30` 已通过 `auto_eval.py --scan_tasks --dry_run` 格式检查。

## 不建议的方案

### 不建议把 CUA 塞进 `run.py`

WebVoyager 的 `run.py` 假设模型输出：

```text
Action: Click [5]
Action: Type [0]; query
```

CUA 的动作是：

```json
{"action":"mouse_click","x":100,"y":200}
{"action":"clipboard_type","text":"query"}
```

二者动作空间完全不同。强行接入会让 CUA 失去自己原生的桌面工具链，也会把 WebVoyager 的 Selenium 元素编号机制和 CUA 的屏幕坐标机制搅在一起，收益低，复杂度高。

### 不建议用 CUA 源码 API

虽然 CUA 暴露了 `CUARuntime`，但本次约束是“不改 CUA，只跑编译产物”。直接 import TS/JS API 会让当前项目和 CUA 内部实现耦合，后续 CUA 一改目录或类型，这边就跟着炸。

## 主要风险

### 1. 公平性风险

CUA 是桌面 Agent，不是 WebVoyager 的 Selenium Agent。它可能使用：

- `shell_exec`
- `osascript_exec`
- `app_open`
- 系统快捷键
- 本地浏览器状态

如果不限制工具能力，它和 WebVoyager baseline 不是同一评测档位。

建议至少分两档：

```text
vision-gui-only:
  允许截图、鼠标、键盘、滚动、等待、打开浏览器。

tool-augmented:
  允许 shell、osascript、openclaw、系统级工具。
```

两个档位结果不能混着比。

### 2. 起始状态风险

WebVoyager 每个任务由 Selenium 打开指定网页，浏览器状态相对干净。CUA 是桌面级 Agent，可能受当前系统状态影响：

- 默认浏览器是谁。
- 上次浏览器是否已有页面。
- 是否有登录态。
- 是否有弹窗。
- 屏幕权限是否正常。

评测前需要统一起始状态。最小做法是在任务文本中明确要求：

```text
Open this URL first: <web>
Then complete this task: <ques>
```

更稳的做法是在当前项目的 runner 里先用系统命令打开 URL，或者让 CUA 第一步打开 URL。

### 3. 截图格式风险

CUA 可能保存 `.jpg`，WebVoyager evaluator 当前只找：

```text
screenshot1.png
screenshot2.png
```

转换器需要把 CUA 截图复制或转换成 PNG 命名。

### 4. 最终答案风险

CUA 的 `done.reason` 不一定是可评测答案。比如：

```text
任务完成
```

这对 WebVoyager evaluator 不够。任务 prompt 里要强制要求：

```text
When done, include the final answer in the done reason.
```

### 5. 自动评测器写死原始任务目录

`evaluation/auto_eval.py` 当前 `main()` 写死了 15 个 WebVoyager 网站和 `0..45` 编号。需要在当前项目里改成扫描任意结果目录。

这个改动属于 WebVoyager 当前项目，不涉及 CUA。

## 推荐结论

推荐方案：

```text
不改 CUA
不接 CUA 内部 API
当前项目新增 scripts/cua_eval/
  1. 批量读取 WebVoyager 任务
  2. 调 CUA dist/cli/bin.js run
  3. 读取 CUA runs/<runId>/steps.json
  4. 转换为 WebVoyager results 格式
  5. 调 auto_eval.py 做评测
```

这是最稳、最少侵入、最容易回滚的方案。
