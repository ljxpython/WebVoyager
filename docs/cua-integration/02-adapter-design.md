# 02 适配设计

## 总体设计

所有适配代码放在当前 WebVoyager 项目下，不改 CUA。

当前第一版新增一个合并脚本，先不拆太细：

```text
scripts/cua_eval/
└── run_and_convert.py        # 调度 CUA、转换 run、写 summary
```

同时新增当前项目内的 CUA 专用配置：

```text
config/cua_eval.json
```

这个配置是完整 CUA config，不依赖 CUA 项目的 `config/default.json` 合并，重点固定：

- `agent.artifacts.pruneAfterRun=false`，保留截图。
- `agent.knowledge.enabled=false`。
- `agent.records.enabled=false`。
- `agent.brain.enabled=false`。
- `tools.shellSh.enabled=false`。

也可以先只写一个脚本：

```text
scripts/cua_eval/run_and_convert.py
```

老王建议先一把梭写小脚本，跑通后再拆。别一上来抽象一堆类，都是给自己挖坑。

## 输入

### 任务输入

沿用 WebVoyager JSONL：

```json
{"web_name":"GitHub","id":"GitHub--0","ques":"Search for ...","web":"https://github.com/"}
```

脚本参数建议：

```bash
uv run python scripts/cua_eval/run_and_convert.py \
  --tasks data/tasks_test.jsonl \
  --cua-bin /path/to/cua/dist/cli/bin.js \
  --cua-config config/cua_eval.json \
  --raw-runs-dir results/cua_raw_runs \
  --converted-dir results/cua_webvoyager \
  --max-steps 15 \
  --max-images 3
```

### 模型配置输入

复用当前项目 `.env`：

```bash
DOUBAO_API_KEY=...
DOUBAO_API_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_API_MODEL=doubao-seed-2-0-pro-260215
CUA_PROVIDER=openai
```

调用 CUA 时映射成：

```bash
node <cua-bin> run "<task>" \
  --provider openai \
  --base-url "$DOUBAO_API_URL" \
  --model "$DOUBAO_API_MODEL"
```

API key 不放在命令行里，由当前适配脚本注入子进程环境变量 `OPENAI_API_KEY=$DOUBAO_API_KEY`。CUA 同时支持 `--provider http`，但它的 OpenAI provider 已经支持 `baseURL`，且对 Ark endpoint 做了兼容。先用 `--provider openai` 更贴近现状。

## 任务 prompt 设计

WebVoyager 原始任务只有 `ques` 和 `web`。CUA 需要更明确的任务包装：

```text
You are being evaluated on a WebVoyager web browsing task.

Open this URL first:
<web>

Complete this task:
<ques>

Rules:
- Use the browser UI to complete the task.
- If the target website is already open or loading, do not repeatedly open the same URL in new tabs.
- For this benchmark, prefer continuing from the current page state over restarting navigation.
- Do not use shell, scripts, direct HTTP requests, or filesystem shortcuts to obtain the answer unless the evaluation profile explicitly allows tool augmentation.
- When the task is complete, call done with the final answer in the reason.
- The done reason must contain the answer, not just "task completed".
```

如果要做中文 prompt：

```text
你正在执行一个 WebVoyager 网页浏览评测任务。

请先打开这个网址：
<web>

然后完成任务：
<ques>

要求：
- 使用浏览器界面完成任务。
- 除非当前评测档位允许工具增强，否则不要用 shell、脚本、直接 HTTP 请求或文件系统捷径获取答案。
- 完成任务时，done 的 reason 里必须包含最终答案，不要只写“任务完成”。
```

## CUA 调用方式

最小命令：

```bash
node "/path/to/cua/dist/cli/bin.js" run "$TASK" \
  --runs-dir "$CUA_RUNS_DIR" \
  --max-steps 15 \
  --max-images 3 \
  --provider openai \
  --base-url "$DOUBAO_API_URL" \
  --model "$DOUBAO_API_MODEL" \
  --no-knowledge \
  --records-off \
  --brain-off \
  --no-prune-after-run
```

说明：

- `--runs-dir`：让 CUA 原始产物也落在当前 WebVoyager 项目下，方便追踪。
- `--no-knowledge`：减少 CUA knowledge 对网页任务的额外影响。
- `--records-off`、`--brain-off`：先降低变量，做更干净的 baseline。
- `--no-prune-after-run`：保留截图，方便转换和复盘。

是否禁用 shell/osascript 需要进一步确认。CUA CLI 有 `--shell-sh-off`，但 `shell_exec`、`osascript_exec` 是否能完全通过配置禁用，需要读工具注册逻辑或采用 prompt 约束。第一版可以先记录为 `tool-augmented` 或 `gui-biased`，不要声称是严格 vision-only。

## 如何识别 CUA runId

CUA CLI stdout 会打印日志，但不保证稳定机器可解析。更稳的方式：

1. 为每个任务指定一个独立 `--runs-dir` 子目录。
2. 执行前记录该目录已有子目录。
3. 执行后扫描新增子目录。
4. 新增的那个目录就是 runId。

目录设计：

```text
results/cua_raw_runs/
└── taskGitHub--0/
    └── 8f74b330/
        ├── steps.json
        ├── steps.jsonl
        └── step_001_after.jpg
```

这样不用解析 stdout，稳。

## CUA 到 WebVoyager 的结果转换

### 输入

```text
results/cua_raw_runs/task<id>/<runId>/steps.json
```

### 输出

```text
results/cua_webvoyager/task<id>/
├── interact_messages.json
├── screenshot1.png
├── screenshot2.png
└── ...
```

### 截图转换

从 `steps.json["steps"]` 中按顺序读取 `screenshotPath`：

```json
{
  "step": 1,
  "screenshotPath": "runs/xxx/step_001_after.jpg"
}
```

转换规则：

- 过滤空路径。
- 去重连续重复路径。
- 按出现顺序复制到 `screenshot1.png`、`screenshot2.png`。
- 如果源是 JPEG，用 Pillow 转成 PNG。
- 如果源路径是相对路径，按 CUA 项目 cwd 或 run dir 解析。

### interact_messages.json 生成

最低可用格式：

```json
[
  {
    "role": "system",
    "content": "Converted CUA run for WebVoyager evaluation."
  },
  {
    "role": "user",
    "content": "Now given a task: <ques>  Please interact with <web> and get the answer.Observation: Converted from CUA trajectory."
  },
  {
    "role": "assistant",
    "content": "Thought: CUA trajectory step 1.\nAction: <action summary>"
  },
  {
    "role": "assistant",
    "content": "Thought: CUA finished the task.\nAction: ANSWER; <final answer>"
  }
]
```

更好的格式是把每个 CUA step 都转成 assistant 消息：

```text
Thought: CUA selected action mouse_click with args {...}
Action: CUA_ACTION; mouse_click {...}
```

注意：WebVoyager evaluator 只强依赖最后一条 `Action: ANSWER`。中间动作不需要完全符合 WebVoyager action schema。

### 最终答案提取

优先级：

1. `steps.json["reason"]`
2. 最后一个 `done` action 的 `actionArgs.reason`
3. 最后一个 step 的 `llmResponse`
4. 如果没有明确答案，写：

```text
CUA did not provide a final answer.
```

但第 4 种会导致自动评测大概率失败，这是合理结果。

## 自动评测适配

当前 `evaluation/auto_eval.py` 的 `main()` 写死：

```python
webs = [...]
for web in webs:
    for idx in range(0, 46):
        file_dir = os.path.join(args.process_dir, 'task'+web+'--'+str(idx))
```

建议在当前项目改成扫描模式：

```python
for name in sorted(os.listdir(args.process_dir)):
    file_dir = os.path.join(args.process_dir, name)
    if os.path.exists(os.path.join(file_dir, "interact_messages.json")):
        auto_eval_by_gpt4v(file_dir, client, args.api_model, args.max_attached_imgs)
```

这不影响 CUA，属于 WebVoyager 评测器通用化。

## 输出汇总

第一版至少生成：

```text
results/cua_webvoyager/summary.jsonl
```

每行：

```json
{
  "task_id": "GitHub--0",
  "web_name": "GitHub",
  "web": "https://github.com/",
  "cua_run_id": "8f74b330",
  "cua_success": true,
  "cua_reason": "...",
  "steps": 12,
  "duration_ms": 120000,
  "llm_tokens": {"prompt": 1000, "completion": 100, "total": 1100},
  "tool_counts": {"mouse_click": 8, "done": 1},
  "failed_tool_steps": 0,
  "augmented_tools": [],
  "converted_dir": "results/cua_webvoyager/taskGitHub--0"
}
```

自动评测后再补：

```json
{
  "auto_eval": 1,
  "auto_eval_text": "SUCCESS ..."
}
```

## 暂不做的事

第一版不做：

- 不接 CUA HTTP SSE 服务。
- 不实时控制 CUA pause/resume/cancel。
- 不把 WebVoyager Selenium 页面交给 CUA。
- 不强行把 CUA action 转成 WebVoyager `Click [n]`。
- 不在 CUA 项目里加任何代码。

这些都等第一版跑通后再说。
