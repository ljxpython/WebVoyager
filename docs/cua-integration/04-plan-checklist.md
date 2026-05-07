# 04 计划清单

本清单用于后续逐项编码。原则不变：不改 CUA，所有适配工作在当前 WebVoyager 项目完成。

## P0：配置和边界

- [x] 创建 `docs/cua-integration` 调研目录。
- [x] 明确 CUA 只作为黑盒编译产物运行。
- [x] 新增 `.env.example`，声明 CUA 适配所需环境变量。
- [x] 确认 `.env`、`.venv/`、`.idea/` 不进入 git。
- [x] 确认当前 `.env` 里的 `CUA_BIN`、`CUA_CONFIG_PATH` 可用。

完成标准：

```bash
uv run python scripts/cua_eval/run_and_convert.py --help
```

状态：已通过。

## P1：单任务转换器

- [x] 新增 `scripts/cua_eval/run_and_convert.py`。
- [x] 支持读取 WebVoyager JSONL 任务。
- [x] 支持 `--convert-only-run-dir`，不调用 CUA，只转换已有 CUA run。
- [x] 支持从 CUA `steps.json` / `steps.jsonl` 提取 step、截图、最终 reason。
- [x] 支持 JPEG/PNG 截图统一转换成 `screenshotN.png`。
- [x] 支持生成 `interact_messages.json`。
- [x] 支持生成 `summary.jsonl`。

完成标准：

```text
给一个已有 CUA runs/<runId>/steps.json，不调用模型，也能生成：
results/cua_webvoyager/task<id>/interact_messages.json
results/cua_webvoyager/task<id>/screenshot1.png
```

状态：已通过已有 CUA run 转换验证。

## P2：单任务 CUA Runner

- [x] 支持调用 `node <CUA_BIN> run <task>`。
- [x] 支持 `--raw-runs-dir` 指定每个任务独立 raw run 目录。
- [x] 支持从 `.env` 读取：
  - `DOUBAO_API_KEY`
  - `DOUBAO_API_URL`
  - `DOUBAO_API_MODEL`
  - `CUA_BIN`
  - `CUA_CONFIG_PATH`
- [x] 支持 `--max-steps`、`--max-images`。
- [x] 支持执行前后扫描目录识别新 runId。
- [x] CUA 执行失败时仍尝试转换已生成 run。

完成标准：

```text
limit=1、max_steps=2 的 smoke run 能生成 raw CUA run 和 converted WebVoyager result。
```

状态：已通过 smoke run。

## P3：批量任务调度

- [x] 支持 `--start`、`--limit`。
- [x] 支持 `--include-web`、`--exclude-web`。
- [x] 支持跳过已转换任务。
- [x] 支持每个任务单独写 stdout/stderr log。
- [x] 支持失败任务继续执行下一条。
- [ ] 用 3 条真实任务做小批量验证。

完成标准：

```text
连续跑 3 条任务，其中一条失败不影响其他任务产物生成。
```

状态：代码已具备，真实 3 任务批量还没跑。

## P4：评测器通用化

- [x] 修改 `evaluation/auto_eval.py`，新增扫描目录模式。
- [x] 保留原始 WebVoyager 固定网站评测模式。
- [x] 支持输出 `auto_eval_summary.jsonl`。
- [x] 支持读取 `results/cua_webvoyager/task...`。
- [x] 支持 `--dry_run`，不调用评测模型只校验输入格式。

完成标准：

```text
auto_eval.py 可以评测任意包含 interact_messages.json 的子目录。
```

状态：`results/cua_webvoyager_30` dry-run 已通过。

## P5：指标汇总

- [x] 汇总 CUA 自身 success。
- [ ] 汇总自动评测 success。
- [x] 统计步数、耗时、token。
- [x] 统计工具使用分布。
- [x] 标记是否出现 `shell_exec`、`osascript_exec` 等增强工具。

完成标准：

```text
summary.jsonl 足够回答：
CUA 跑了几条、成功几条、失败原因是什么、用了哪些工具。
```

状态：CUA 侧 summary 已具备；自动评测结果暂由 `auto_eval.py --summary_file` 单独输出，后续可再合并。

## 暂缓事项

- [ ] 严格禁用 CUA 的 shell/osascript 工具。
- [ ] 接入 CUA HTTP SSE 服务。
- [ ] 实时 pause/resume/cancel。
- [ ] 将 CUA action 映射成 WebVoyager `Click [n]`。

这些都不是第一版闭环需要的东西，先别加复杂度。
