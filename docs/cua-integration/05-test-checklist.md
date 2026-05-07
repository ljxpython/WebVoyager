# 05 测试清单

这个清单用于每次改完适配代码后验收。测试分为不烧 token 的本地测试和会调用 CUA/模型的集成测试。

## T0：静态检查

- [x] Python 脚本能通过语法检查。

```bash
uv run python -m py_compile scripts/cua_eval/run_and_convert.py evaluation/auto_eval.py
```

- [x] CUA 编译产物存在。
- [x] 当前项目内 CUA eval config 存在。
- [x] CUA eval config 是合法 JSON。

```bash
uv run python -m json.tool config/cua_eval.json
```

通过标准：

```text
命令退出码为 0。
```

当前状态：已通过。

## T1：环境变量检查

- [x] `.env` 可以被 adapter 读取。
- [x] 不打印真实 API key。
- [x] `DOUBAO_API_URL`、`DOUBAO_API_MODEL` 可见。
- [x] `CUA_BIN`、`CUA_CONFIG_PATH` 可见。

命令：

```bash
uv run python scripts/cua_eval/run_and_convert.py \
  --print-config \
  --convert-only-run-dir /path/to/existing/cua/run \
  --limit 1
```

通过标准：

```text
adapter 的 --print-config 只输出 <redacted> key。
```

当前状态：已通过，且 key 已改为完全隐藏。

## T2：只转换已有 CUA run

输入：

```text
/path/to/cua/runs/<runId>/steps.json
```

命令：

```bash
uv run python scripts/cua_eval/run_and_convert.py \
  --tasks data/tasks_test.jsonl \
  --limit 1 \
  --convert-only-run-dir /path/to/cua/runs/<runId> \
  --converted-dir results/cua_webvoyager_test
```

检查：

- [x] `interact_messages.json` 存在。
- [x] 至少一个 `screenshotN.png` 存在，除非原 run 没截图。
- [x] 最后一条 assistant 消息包含 `Action: ANSWER;`。
- [x] `summary.jsonl` 存在。

通过标准：

```text
不调用 CUA、不调用模型，也能生成 WebVoyager evaluator 所需最小格式。
```

当前状态：已通过。

## T3：失败 run 转换

用一个 CUA 失败样本，例如截图失败或 max steps 失败。

检查：

- [x] 转换器不崩。
- [x] summary 里记录 `cua_success=false`。
- [x] final answer 标记为没有明确答案或包含 CUA failure reason。

通过标准：

```text
失败 run 也能转换，后续自动评测自然判失败。
```

当前状态：`max_steps_exceeded` 样本已能转换。

## T4：单任务 smoke run

这一步会调用 CUA 和模型，可能消耗 token。

命令：

```bash
uv run python scripts/cua_eval/run_and_convert.py \
  --tasks data/tasks_test.jsonl \
  --limit 1 \
  --max-steps 2 \
  --max-images 1 \
  --raw-runs-dir results/cua_raw_runs_smoke \
  --converted-dir results/cua_webvoyager_smoke
```

检查：

- [x] raw runs 目录生成一个 runId。
- [x] converted 目录生成 task 结果。
- [x] stdout/stderr log 已保存。
- [x] CUA 失败时也有 summary 记录。

通过标准：

```text
跑 2 步不要求任务完成，只要求调度和转换链路通。
```

当前状态：已通过。

## T5：自动评测输入检查

对 converted 目录检查：

- [x] 每个 task 目录有 `interact_messages.json`。
- [x] 截图命名符合 `screenshot1.png`。
- [x] `interact_messages.json` 第 2 条含 `Now given a task:`。
- [x] 最后一条含 `Action: ANSWER;`。

命令：

```bash
uv run python evaluation/auto_eval.py \
  --process_dir results/cua_webvoyager_30 \
  --scan_tasks \
  --dry_run \
  --summary_file results/cua_webvoyager_30/auto_eval_dry_run.jsonl
```

通过标准：

```text
evaluation/auto_eval.py 能读取目录，不因格式错误退出。
```

当前状态：已通过，`ok screenshots=19`。

## T6：单任务完整运行

这一步会调用 CUA 和模型，可能消耗 token。

命令：

```bash
uv run python scripts/cua_eval/run_and_convert.py \
  --tasks data/tasks_test.jsonl \
  --limit 1 \
  --max-steps 30 \
  --max-images 3 \
  --raw-runs-dir results/cua_raw_runs_30 \
  --converted-dir results/cua_webvoyager_30
```

检查：

- [x] CUA 生成 raw run。
- [x] 转换器生成 WebVoyager 结果目录。
- [x] `summary.jsonl` 记录 `cua_success`、`steps`、`tool_counts`。
- [x] dry-run auto_eval 能读取转换产物。

当前状态：

```text
cua_success=true
cua_reason=The easy Animals image quiz has been completed successfully, the final score is 2/6.
steps=24
screenshots=19
```

## T7：批量稳定性

命令：

```bash
uv run python scripts/cua_eval/run_and_convert.py \
  --tasks data/WebVoyager_data.jsonl \
  --include-web GitHub,Google Search \
  --limit 3 \
  --max-steps 3 \
  --max-images 1
```

检查：

- [ ] 3 条任务均写入 summary。
- [ ] 单条失败不阻断整个批次。
- [ ] 每条任务 raw run 目录隔离。

通过标准：

```text
批量 runner 具备继续执行能力。
```

当前状态：代码已支持，真实小批量还未跑。

## T8：安全检查

- [x] `.env` 没有进入 git。
- [x] `results/cua_*` 没有进入 git。
- [x] stdout/stderr log 里不写明文 API key。
- [x] summary 里不写明文 API key。

命令：

```bash
git status --short --ignored
```

通过标准：

```text
能看到 .env 被忽略，不能看到 key 文件被暂存。
```
