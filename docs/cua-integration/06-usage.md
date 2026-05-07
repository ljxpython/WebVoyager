# 06 使用说明

这份文档只说明当前 WebVoyager 项目里的 CUA 评测适配怎么用。CUA 项目仍然当黑盒编译产物使用，不改源码。

## 1. 准备环境变量

复制示例文件：

```bash
cp .env.example .env
```

至少填写：

```bash
DOUBAO_API_KEY=你的真实 key
DOUBAO_API_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_API_MODEL=doubao-seed-2-0-pro-260215
CUA_BIN=/path/to/cua/dist/cli/bin.js
CUA_CONFIG_PATH=config/cua_eval.json
```

`.env` 已加入 `.gitignore`，不要提交。

如果你本地 `.env` 已经使用 `OSWORLD_CUA_REPO_ROOT`、`OSWORLD_CUA_BIN`，适配器也会自动读取这些兼容键，不需要把真实路径提交到仓库。CUA 配置仍建议使用当前仓库的 `config/cua_eval.json`。

## 2. 检查脚本参数

```bash
uv run python scripts/cua_eval/run_and_convert.py --help
```

检查当前配置，API key 只会显示为 `<redacted>`：

```bash
uv run python scripts/cua_eval/run_and_convert.py \
  --print-config \
  --convert-only-run-dir /path/to/existing/cua/run \
  --limit 1
```

## 3. 只转换已有 CUA run

已有 CUA `steps.json` 或 `steps.jsonl` 时，可以不调用 CUA、不消耗模型 token：

```bash
uv run python scripts/cua_eval/run_and_convert.py \
  --tasks data/tasks_test.jsonl \
  --limit 1 \
  --convert-only-run-dir /path/to/cua/runs/<runId> \
  --converted-dir results/cua_webvoyager_test
```

输出：

```text
results/cua_webvoyager_test/taskCambridge Dictionary--29/
├── interact_messages.json
├── screenshot1.png
├── screenshot2.png
└── summary.jsonl 在父目录
```

## 4. 跑一条 smoke run

这一步会调用 CUA 和模型。`max-steps=2` 不要求任务完成，只验证调度、raw run、转换链路。

```bash
uv run python scripts/cua_eval/run_and_convert.py \
  --tasks data/tasks_test.jsonl \
  --limit 1 \
  --max-steps 2 \
  --max-images 1 \
  --raw-runs-dir results/cua_raw_runs_smoke \
  --converted-dir results/cua_webvoyager_smoke
```

## 5. 跑一条完整样例

当前 Cambridge Dictionary 样例用 `max-steps=30` 跑通过一次，返回分数 `2/6`：

```bash
uv run python scripts/cua_eval/run_and_convert.py \
  --tasks data/tasks_test.jsonl \
  --limit 1 \
  --max-steps 30 \
  --max-images 3 \
  --raw-runs-dir results/cua_raw_runs_30 \
  --converted-dir results/cua_webvoyager_30
```

查看汇总：

```bash
tail -n 1 results/cua_webvoyager_30/summary.jsonl
```

## 6. 验证 WebVoyager 评测输入

不调用评测模型，只检查目录格式：

```bash
uv run python evaluation/auto_eval.py \
  --process_dir results/cua_webvoyager_30 \
  --scan_tasks \
  --dry_run \
  --summary_file results/cua_webvoyager_30/auto_eval_dry_run.jsonl
```

成功时会看到类似：

```text
Found 1 task dirs under results/cua_webvoyager_30
[1] results/cua_webvoyager_30/taskCambridge Dictionary--29: ok screenshots=19
```

## 7. 调用自动评测模型

这一步会把任务文本、最终回答和截图发给 `.env` 中配置的 OpenAI-compatible 模型：

```bash
uv run python evaluation/auto_eval.py \
  --process_dir results/cua_webvoyager_30 \
  --scan_tasks \
  --max_attached_imgs 3 \
  --max_retries 3 \
  --summary_file results/cua_webvoyager_30/auto_eval_summary.jsonl
```

第一版建议先用 `--dry_run` 验证格式，再决定是否跑真实评测，免得格式错了还烧 token。

## 8. 输出说明

`summary.jsonl` 每行对应一个 WebVoyager task，重点字段：

- `cua_success`：CUA 自身是否认为完成。
- `cua_reason` / `final_answer`：CUA 的最终答案。
- `steps`：执行步数。
- `duration_ms`：步骤耗时汇总。
- `llm_tokens`：CUA 每步 LLM token 汇总。
- `tool_counts`：工具使用分布。
- `failed_tool_steps`：工具失败步数。
- `augmented_tools`：是否出现 shell、osascript、HTTP 等增强工具。
- `converted_dir`：WebVoyager evaluator 可读取的结果目录。
