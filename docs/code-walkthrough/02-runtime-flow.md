# 02 运行主链路

这一篇按 `run.py` 的真实执行顺序走。别被 README 的宣传图迷惑，真跑起来就是下面这条链。

## 1. 参数解析

`main()` 里通过 `argparse` 定义参数：

```text
--test_file              任务 JSONL
--max_iter               每个任务最多交互轮数
--api_key                OpenAI API key
--api_model              决策模型
--output_dir             结果目录
--seed                   API seed
--max_attached_imgs      上下文最多保留几张截图
--temperature            当前定义了，但主调用没传，基本是摆设
--download_dir           浏览器下载目录
--text_only              使用 accessibility tree，不用视觉截图
--headless               Chrome 无头模式
--save_accessibility_tree 保存可访问性树
--force_device_scale     强制 device scale factor = 1
--window_width           浏览器宽度
--window_height          浏览器高度
--fix_box_color          元素标注框固定为黑色
```

直接运行示例：

```bash
rtk python -u "run.py" \
  --test_file "data/tasks_test.jsonl" \
  --api_key "$OPENAI_API_KEY" \
  --headless \
  --max_iter 15 \
  --max_attached_imgs 3 \
  --fix_box_color \
  --seed 42
```

## 2. 配置浏览器

`driver_config(args)` 创建 `webdriver.ChromeOptions()`。

关键点：

- `--save_accessibility_tree` 会隐式开启 `--force_device_scale`。
- `--force_device_scale` 会设置 Chrome 参数 `--force-device-scale-factor=1`。
- `--headless` 会开启无头模式并设置 Linux Chrome user-agent。
- 下载目录被设置为 `args.download_dir`。
- PDF 被设置为外部下载，不在浏览器里打开。

注意：`run.py` 每个任务开始时会删除 `download_dir` 下已有普通文件。艹，这不是玩笑，别把重要文件放 `downloads/`。

## 3. 读取任务

`args.test_file` 是 JSONL 文件，每行解析成一个任务对象。主循环按顺序处理：

```json
{
  "web_name": "GitHub",
  "id": "GitHub--0",
  "ques": "Search for ...",
  "web": "https://github.com/"
}
```

实际代码至少依赖：

- `task["id"]`：用于结果目录名。
- `task["ques"]`：放进模型输入。
- `task["web"]`：浏览器初始 URL。

`web_name` 主要给人看，核心逻辑里基本不依赖。

## 4. 初始化单个任务

每个任务会创建自己的目录：

```text
results/<timestamp>/task<task["id"]>/
```

随后：

1. 重置 logger 到当前任务的 `agent.log`。
2. 新建 Chrome driver。
3. 设置窗口大小。
4. 打开 `task["web"]`。
5. 尝试点击 `body` 激活页面。
6. 注入 JS 禁止空格键导致页面误滚动。
7. 清空下载目录。

## 5. 选择观测模式

### 视觉模式，默认

消息系统提示词来自 `SYSTEM_PROMPT`。

每轮会调用：

```python
get_web_element_rect(driver_task, fix_color=args.fix_box_color)
driver_task.save_screenshot(img_path)
encode_image(img_path)
format_msg(...)
```

模型看到的是：

- 当前网页截图。
- 可交互元素上的数字编号。
- 元素编号和文本摘要，例如 `[5]: <input> "Search or jump to...";`。

### 文本模式，`--text_only`

消息系统提示词来自 `SYSTEM_PROMPT_TEXT_ONLY`。

每轮会调用：

```python
get_webarena_accessibility_tree(driver_task, accessibility_tree_path)
format_msg_text_only(...)
```

模型看到的是 accessibility tree，不看图片。

文本模式更便宜，但对复杂视觉布局、图片按钮、画布页面会弱一些。

## 6. 单轮 agent loop

每轮循环逻辑是：

```text
1. 获取网页观测
2. 保存截图或 accessibility tree
3. 拼接 user message
4. 裁剪历史消息
5. 调用模型
6. 保存 assistant 回复
7. 移除页面上的标注框
8. 解析 Action
9. 执行 Selenium 动作
10. 进入下一轮
```

最大轮数由 `--max_iter` 控制。模型如果输出 `ANSWER; ...`，当前任务提前结束。

## 7. 消息裁剪

多轮截图非常耗 token，也会把模型脑子搅成浆糊，所以代码会裁剪旧观测：

- 视觉模式：`clip_message_and_obs(messages, args.max_attached_imgs)`
- 文本模式：`clip_message_and_obs_text_only(messages, args.max_attached_imgs)`

裁剪策略不是删除整段历史，而是把旧截图替换成一句摘要：

```text
Observation: A screenshot and some texts. (Omitted in context.)
```

这样保留决策轨迹，又不一直把老截图塞进上下文。

## 8. 模型调用

`call_gpt4v_api(...)` 使用：

```python
openai_client.chat.completions.create(
    model=args.api_model,
    messages=messages,
    max_tokens=1000,
    seed=args.seed,
)
```

文本模式额外设置 `timeout=30`。

几个现实问题：

- `--temperature` 没传进 API 调用，当前参数不生效。
- 默认模型名来自老代码，实际使用时要替换成你当前账号可用的模型。
- 异常处理按旧 OpenAI SDK 错误名判断，升级依赖后要重新确认。

## 9. 动作解析

模型必须包含：

```text
Thought:
Action:
```

否则主循环设置 `fail_obs`，下一轮把格式错误提示发回模型。

动作解析在 `utils.extract_information(text)`：

```text
Click [5]              -> action_key = click
Type [0]; query        -> action_key = type
Scroll [WINDOW]; down  -> action_key = scroll
Wait                   -> action_key = wait
GoBack                 -> action_key = goback
Google                 -> action_key = google
ANSWER; result         -> action_key = answer
```

这套正则比较脆，动作格式偏一点就可能解析失败。

## 10. 动作执行

### Click

视觉模式下把编号转成 `web_eles[index]`，然后：

```python
driver_task.execute_script("arguments[0].setAttribute('target', '_self')", web_ele)
web_ele.click()
```

它会强行把链接打开方式改成当前窗口，避免新 tab 搞乱上下文。

### Type

输入前会尝试：

1. `clear()`
2. 全选
3. 输入空格再 backspace
4. 点击元素
5. 输入内容
6. 自动按 Enter

所以 prompt 里才会强调：输入文本不用先点输入框。

### Scroll

`Scroll [WINDOW]; down` 会滚动整个窗口高度的三分之二。

如果指定某个元素，代码会尝试 focus 该元素，然后发送 `Alt + ArrowDown/ArrowUp`。

### PDF

点击后如果下载目录出现新的 PDF：

1. 等 10 秒。
2. 调用 `get_pdf_retrieval_ans_from_assistant(...)`。
3. 把 PDF 分析结果拼回下一轮 observation。
4. 把 PDF 复制到任务结果目录。

这块使用的是老 Assistant API 写法，后续真要评测 PDF 流程，建议单独验证。

## 11. 输出轨迹

任务结束后调用：

```python
print_message(messages, task_dir)
driver_task.quit()
```

`print_message` 会把图片 base64 替换成占位符后保存到：

```text
interact_messages.json
```

这份文件是后续自动评测和人工复盘的核心证据。

## 12. 示例轨迹

`results/examples/taskGitHub--0/interact_messages.json` 里能看到典型链路：

```text
Click [5]
Type [0]; climate change data visualization
Click [29]
Click [52]
ANSWER; resource-watch/resource-watch with 63 stars
```

这说明 WebVoyager 的结果不是只看最终答案，而是完整保存了 agent 在网页上的每一步选择。

