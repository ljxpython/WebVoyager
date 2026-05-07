# 04 Agent 评测接入指南

这一篇重新讲清楚：你的项目也是一个 Agent，不是普通 Web 应用。我们要做的是用 WebVoyager 的任务集、浏览器环境、轨迹格式和评测器，评测你这个 Agent 的网页操作能力。

老王先把核心目标钉死：

```text
WebVoyager benchmark task -> 你的 Agent 操作网页 -> 保存可复盘轨迹 -> 自动/人工判断任务是否成功
```

## WebVoyager 能评什么 Agent 能力

适合评测：

- 真实网页导航能力。
- 截图理解能力。
- 元素定位能力。
- 搜索、筛选、排序、翻页、回退等交互能力。
- 多步任务规划能力。
- 最终答案是否由网页证据支持。
- 遇到弹窗、加载、点击失败时的恢复能力。

不适合只靠它评测：

- 纯文本问答能力。
- 不需要浏览器的工具调用能力。
- 后端 API agent。
- 需要登录、验证码、支付、隐私数据输入的高风险流程。

## 当前 WebVoyager 的评测资产

这个仓库里有四块东西可以复用：

1. `data/WebVoyager_data.jsonl`：任务集。
2. `run.py`：Selenium 浏览器环境和动作执行器。
3. `results/<timestamp>/task...`：轨迹保存格式。
4. `evaluation/auto_eval.py`：基于最终回答和截图的自动评测器。

评测你的 Agent 时，不一定要复用全部。关键是让你的 Agent 产出能被评测器复盘的轨迹。

## 两种接入路线

### 路线 A：把你的 Agent 接进 WebVoyager Runner

这是最推荐的路线，尤其当你的 Agent 能接收“截图 + 元素编号文本”，并输出类似 WebVoyager 的动作。

你保留 `run.py` 里的：

- 任务读取。
- Selenium 启动。
- 元素标注。
- 截图保存。
- 动作执行。
- 轨迹保存。

你替换的是：

```text
call_gpt4v_api(...) -> call_your_agent(...)
```

也就是说，WebVoyager 负责环境，你的 Agent 负责决策。

你的 Agent 需要输出同样的动作协议：

```text
Thought: ...
Action: Click [5]
```

支持动作：

```text
Click [Numerical_Label]
Type [Numerical_Label]; [Content]
Scroll [Numerical_Label or WINDOW]; [up or down]
Wait
GoBack
Google
ANSWER; [content]
```

优点：

- 最公平，环境、动作空间、截图、最大步数都一致。
- 能直接复用 `interact_messages.json` 和截图保存逻辑。
- 能直接接 `evaluation/auto_eval.py`。

缺点：

- 你的 Agent 必须适配 WebVoyager 的 observation 和 action schema。
- 如果你的 Agent 原本有自己的浏览器控制协议，需要写一层 adapter。

### 路线 B：你的 Agent 独立运行，转换轨迹格式

如果你的 Agent 已经有自己的 browser runner、planner、tool executor，那就不强行塞进 `run.py`。让它独立跑 WebVoyager 任务，然后写一个 converter，把结果转换成 WebVoyager evaluator 能读的格式。

评测器最低依赖这些文件：

```text
results/<run_id>/task<task_id>/
├── interact_messages.json
├── screenshot1.png
├── screenshot2.png
└── ...
```

`evaluation/auto_eval.py` 主要读取：

- `interact_messages.json` 第 2 条消息里的任务文本。
- 最后一条 assistant 消息里的 `Action: ANSWER`。
- 最后若干张 `screenshotN.png`。

所以转换后的 `interact_messages.json` 至少要长这样：

```json
[
  {
    "role": "system",
    "content": "..."
  },
  {
    "role": "user",
    "content": "Now given a task: <任务内容>  Please interact with <起始URL> and get the answer.Observation: ..."
  },
  {
    "role": "assistant",
    "content": "Thought: ...\nAction: Click [5]"
  },
  {
    "role": "assistant",
    "content": "Thought: ...\nAction: ANSWER; <最终答案>"
  }
]
```

优点：

- 不破坏你现有 Agent 架构。
- 能评测更复杂的自定义动作空间。
- 只要保留截图和最终答案，就能复用自动评测。

缺点：

- 环境不完全一致，公平性要自己控制。
- 如果你的 Agent 使用 DOM、网络请求、数据库直连等特权工具，结果不能和纯视觉/浏览器 Agent 直接横向比较。

## 推荐评测流程

### 1. 先固定任务集

可以先抽一个小集合，例如：

```text
data/agent_eval_smoke.jsonl
```

格式沿用 WebVoyager：

```json
{"web_name":"GitHub","id":"GitHub--0","ques":"Search for an open-source project related to 'climate change data visualization' on GitHub and report the project with the most stars.","web":"https://github.com/"}
```

字段说明：

- `web_name`：网站类别。
- `id`：任务唯一 ID。
- `ques`：任务说明。
- `web`：起始 URL。

建议先选 5 到 10 条任务做 smoke test，别一上来 643 条全压上去。这个项目调试一次浏览器链路就够烦，别给自己找罪受。

### 2. 固定运行条件

为了评测公平，至少固定：

- `max_iter`。
- 浏览器窗口大小。
- 是否 headless。
- 起始 URL。
- 任务文本。
- 模型/agent 配置。
- 是否允许外部搜索。
- 是否允许 DOM/API/网络抓取等额外工具。

WebVoyager 默认窗口是：

```text
1024 x 768
```

默认动作上限常用：

```text
max_iter = 15
```

### 3. 运行你的 Agent

路线 A 示例命令仍然走 `run.py`，只是内部决策函数换成你的 Agent：

```bash
uv run python -u "run.py" \
  --test_file "data/agent_eval_smoke.jsonl" \
  --output_dir "results" \
  --headless \
  --max_iter 15 \
  --max_attached_imgs 3 \
  --fix_box_color \
  --seed 42
```

路线 B 则由你的 Agent 自己跑，但输出目录要能转换为：

```text
results/<run_id>/task<id>/
```

每个任务目录必须保存最后评测要用的截图和最终答案。

### 4. 人工复盘一小批

自动评测之前，先人工看 3 到 5 个任务：

- `screenshotN.png` 是否按步骤保存。
- `interact_messages.json` 是否包含每轮决策。
- 最后一条是否包含 `Action: ANSWER; ...`。
- 最终答案是否能从截图看出来。

这一步别省。自动评测器输入格式一歪，它不会替你擦屁股。

### 5. 跑自动评测

当前 `evaluation/auto_eval.py` 的 `main()` 写死了原始 WebVoyager 的 15 个网站和 `0..45` 编号区间。评测你的 Agent 时，建议改成扫描结果目录。

推荐逻辑：

```python
for name in sorted(os.listdir(args.process_dir)):
    file_dir = os.path.join(args.process_dir, name)
    if os.path.exists(os.path.join(file_dir, "interact_messages.json")):
        response = auto_eval_by_gpt4v(
            file_dir,
            client,
            args.api_model,
            args.max_attached_imgs,
        )
```

这样只要目录里有合法轨迹，任意 Agent 的结果都能评。

## Agent Adapter 需要做什么

如果走路线 A，你需要写一层 adapter，把 WebVoyager 的 observation 转给你的 Agent，再把你的 Agent 输出转回 WebVoyager action。

### 输入给你的 Agent 的信息

视觉模式下，每轮有：

- 任务文本。
- 当前截图 base64 或截图路径。
- 元素编号和文本摘要。
- 历史消息。
- 上轮错误提示。
- PDF 辅助结果，少数任务才有。

文本模式下，每轮有：

- 任务文本。
- accessibility tree。
- 历史消息。
- 上轮错误提示。

### 你的 Agent 输出

最省事的输出格式：

```text
Thought: <简短推理>
Action: <WebVoyager动作>
```

例如：

```text
Thought: The search box is labeled [5], so I should submit the query there.
Action: Type [5]; climate change data visualization
```

如果你的 Agent 原生输出是结构化 JSON，可以在 adapter 里转换：

```json
{"action":"type","target":5,"text":"climate change data visualization"}
```

转成：

```text
Thought: ...
Action: Type [5]; climate change data visualization
```

## 评测指标

不要只看成功率，太粗。建议至少记录：

- `success_rate`：自动评测或人工评测成功率。
- `avg_steps`：平均完成步数。
- `timeout_rate`：达到 `max_iter` 还没回答的比例。
- `format_error_rate`：输出无法解析的比例。
- `action_error_rate`：Selenium 执行动作失败的比例。
- `answer_without_evidence_rate`：最终答案截图里看不出证据的比例。
- `avg_runtime`：每个任务平均耗时。
- `avg_cost`：如果你的 Agent 调模型，记录平均成本。

失败分类也要做，不然成功率掉了你不知道该修哪：

```text
perception_error     看错截图或元素
grounding_error      找到目标但点错编号
planning_error       多步计划错
execution_error      浏览器动作失败
recovery_error       失败后不会修正
answer_error         页面做对了但最终答错
evaluator_error      自动评测误判
```

## 公平性要求

评测 Agent 最怕作弊式对比。老王把规矩写明白：

- 如果 WebVoyager baseline 只用截图，你的 Agent 也别偷偷读 DOM。
- 如果你的 Agent 能用 DOM/API，那就单独标成 tool-augmented setting。
- 每个 Agent 使用同一批任务。
- 每个 Agent 使用同样的 `max_iter`。
- 每个 Agent 从同样起始 URL 开始。
- 对时间敏感任务，要统一更新日期或剔除。
- 遇到网站临时弹窗、反爬、网络失败，要记录为环境问题，别混进能力问题。

可以分两个评测档位：

```text
vision-only setting:
  screenshot + element labels -> action

tool-augmented setting:
  screenshot/DOM/API/search tools -> action
```

这两个档位不要混着比。

## 结果目录规范

建议每次评测用清晰 run id：

```text
results/
└── my-agent-20260507-vision-only/
    ├── taskGitHub--0/
    │   ├── agent.log
    │   ├── interact_messages.json
    │   ├── screenshot1.png
    │   └── screenshot2.png
    └── taskArXiv--11/
        ├── agent.log
        ├── interact_messages.json
        └── screenshot1.png
```

后续汇总时，一眼能知道：

- 哪个 Agent。
- 哪天跑的。
- 是 vision-only 还是 tool-augmented。
- 对应哪些任务。

## 当前项目需要优先改造的点

为了更好评测你的 Agent，建议按这个顺序改：

1. 抽出 `call_gpt4v_api(...)` 为通用 `agent_client` 接口。
2. 增加 `--agent_type`，支持 `openai_baseline`、`your_agent`、`replay`。
3. 改 `evaluation/auto_eval.py`，支持扫描任意结果目录。
4. 记录结构化任务结果，例如 `summary.jsonl`。
5. 把 action parse failure 和 Selenium execution failure 单独计数。
6. 增加人工复核清单，抽样校准自动评测误差。

最小可行版本只需要做第 1 和第 3 步。

## 下一步落地建议

先别急着大改。老王建议下一步做一个最小 Agent 接入实验：

1. 选 5 条 WebVoyager 任务。
2. 让你的 Agent 在路线 A 或路线 B 下跑通。
3. 确认每个任务都有截图和 `interact_messages.json`。
4. 改自动评测扫描目录。
5. 产出第一版 `success_rate + avg_steps + failure_type`。

这样就能开始客观评估你的 Agent，而不是凭感觉吹牛。
