# 03 模块代码走读

这一篇按模块看关键函数。老王只讲会影响你接入评测的部分，没用的边角料先不扯。

## `run.py`

### `setup_logger(folder_path)`

给每个任务目录单独设置 `agent.log`。它会移除 root logger 上已有 handler，再挂一个新的 `FileHandler`。

影响：

- 每个任务日志独立。
- 如果你把 WebVoyager 嵌进别的 Python 程序，root logger 会被它重置，可能影响宿主项目日志。

### `driver_config(args)`

返回 Chrome options。核心配置：

- headless。
- user-agent。
- 下载目录。
- PDF 下载行为。
- device scale factor。

如果你评测自己的本地项目，通常保持默认即可；如果页面里依赖浏览器权限、摄像头、定位、跨域下载，就要在这里加 Chrome 参数。

### `format_msg(...)`

视觉模式消息组装器。

第一轮消息包含：

- 任务描述。
- 起始网站。
- 操作要求。
- 元素文本摘要。
- 当前截图。

后续轮次消息包含：

- 上轮错误提示 `warn_obs` 或 PDF 结果 `pdf_obs`。
- 当前元素文本摘要。
- 当前截图。

这就是多模态 agent 的“眼睛”和“上下文”。

### `format_msg_text_only(...)`

文本模式消息组装器。结构更简单，把 accessibility tree 直接拼到文本里。

如果你的页面对 accessibility 支持很差，文本模式会比较惨；如果页面语义标签写得好，文本模式反而更稳定、更便宜。

### `call_gpt4v_api(...)`

负责 OpenAI API 调用和重试。

当前行为：

- 视觉模式调用 `chat.completions.create`。
- 文本模式也调用 `chat.completions.create`，但加 `timeout=30`。
- 遇到 RateLimitError 等错误会 sleep 后重试。
- 最多重试 10 次。

坑点：

- `args.temperature` 没传进去。
- 默认模型名偏老，实际跑前要换成当前可用模型。
- 错误类型名按旧 SDK 习惯写，升级依赖时可能对不上。

### `exec_action_click(info, web_ele, driver_task)`

点击元素。点击前强行设置：

```python
target="_self"
```

这样链接不会开新 tab，简化浏览器窗口管理。

### `exec_action_type(info, web_ele, driver_task)`

输入文本并回车。

这段会判断元素是不是常见输入框。如果不是，会返回 `warn_obs`，下一轮提醒模型可能选错元素。

输入流程比较粗暴但实用：

```text
clear -> 全选 -> 清空 -> click -> send_keys(content) -> Enter
```

这意味着评测你的页面时，搜索框、文本框最好支持标准输入行为。那些花里胡哨的自定义输入控件，能把 Selenium 和模型一起搞懵。

### `exec_action_scroll(info, web_eles, driver_task, args, obs_info)`

滚动窗口或局部元素。

窗口滚动用 JS：

```text
window.scrollBy(0, window_height * 2 / 3)
```

局部滚动用键盘：

```text
Alt + ArrowDown / Alt + ArrowUp
```

如果你的项目有复杂虚拟列表、内部滚动容器，评测前要重点验证这一块。

### `main()`

完整调度器。可以拆成这几个阶段：

```text
参数解析
创建 OpenAI client
配置 Chrome
创建 result_dir
读取 tasks
for task in tasks:
  创建 task_dir
  启动浏览器
  打开页面
  清空下载目录
  初始化 prompt/messages
  while it < max_iter:
    采集观测
    调用模型
    解析动作
    执行动作
  保存 interact_messages.json
  关闭浏览器
```

你要改成评测自己的项目，优先改任务数据，不要一上来动主循环。艹，主循环看着长，其实能不动就别动。

## `utils.py`

### `encode_image(image_path)`

读取 PNG 并转 base64，用于塞进多模态消息。

### `get_web_element_rect(browser, fix_color=True)`

这是视觉模式最核心的观测函数。

它往页面注入一段 JS：

1. 遍历 `document.querySelectorAll('*')`。
2. 找可交互元素：`input`、`textarea`、`select`、`button`、`a`、有 `onclick`、鼠标 pointer、`iframe`、`video`、`li`、`td`、`option`。
3. 过滤面积小于 20 的元素。
4. 尽量去掉按钮内部重复子元素。
5. 在页面上为每个元素画虚线框和数字 label。
6. 返回 label DOM 节点、原始元素、元素文本。

返回值：

```python
rects, web_eles, web_eles_text
```

- `rects`：画上去的标注框，截图后要删掉。
- `web_eles`：Selenium 后续点击/输入用的元素列表。
- `web_eles_text`：发给模型的元素摘要文本。

页面设计建议：

- 按钮和输入框要用标准标签。
- 交互元素要有可见文本或 `aria-label`。
- 不要把真正可点击区域藏在过深的 div/span 里。

### `extract_information(text)`

把模型 action 字符串解析成程序能执行的数据。

正则支持：

```text
Click [1]
Type [1]; abc
Scroll [WINDOW]; down
Wait
GoBack
Google
ANSWER; abc
```

注意：它没有健壮的兜底。如果模型输出 `click 1`、`Click: [1]`、`Answer: xxx`，可能直接解析失败。

### `clip_message_and_obs(...)`

视觉模式历史裁剪。保留所有 assistant 消息，用户消息里只保留最近 `max_img_num` 个含图片观测，旧图片观测替换成文本摘要。

这个策略能降低成本，也避免旧截图干扰当前页面判断。

### `clip_message_and_obs_text_only(...)`

文本模式历史裁剪。逻辑类似，只是裁剪的是旧 accessibility tree。

### `print_message(json_object, save_dir=None)`

把完整消息写到 `interact_messages.json`。为了避免文件巨大，保存前会把图片 base64 替换成：

```text
data:image/png;base64,{b64_img}
```

所以这个 JSON 能复盘模型文本决策，但不能直接还原图片。图片本体在同目录的 `screenshotN.png`。

### `get_webarena_accessibility_tree(browser, save_file=None)`

包装 `utils_webarena.py`，返回：

```python
content, obs_nodes_info
```

- `content`：发给模型看的树文本。
- `obs_nodes_info`：label 到 DOM bounding box 的映射，文本模式执行 click/type/scroll 时要用。

### `get_pdf_retrieval_ans_from_assistant(client, pdf_path, task)`

PDF 辅助处理。下载 PDF 后，上传给 Assistant API，让模型基于 PDF 回答任务，再把这个回答放回下一轮 observation。

这块不是 WebVoyager 主链路的必需功能。你如果评测自己的普通 Web 项目，可以先绕开 PDF。

## `utils_webarena.py`

### `fetch_browser_info(browser)`

通过 Chrome CDP 抓：

- DOM snapshot。
- layout bounds。
- window scroll。
- window size。
- device pixel ratio。

里面有一个硬断言：

```python
assert device_pixel_ratio == 1.0
```

所以文本模式或保存 accessibility tree 时，`--force_device_scale` 很重要。

### `fetch_page_accessibility_tree(info, browser, current_viewport_only)`

调用：

```text
Accessibility.getFullAXTree
```

然后：

- 去重 node。
- 给每个 node 找 bounding box。
- 过滤不可见或视口外节点。
- 移除无效节点并把子节点接回父节点。

### `parse_accessibility_tree(accessibility_tree)`

把树转成缩进文本，例如：

```text
[12] button 'Search'
    [13] StaticText 'Search'
```

同时保存每个可观测节点的：

- backend id。
- union bound。
- 文本。

### `clean_accesibility_tree(tree_str)`

清掉最近几行里重复出现的 `StaticText`，减少 token 浪费。

## `prompts.py`

两个系统提示词：

- `SYSTEM_PROMPT`：视觉模式，强调截图和数字 label。
- `SYSTEM_PROMPT_TEXT_ONLY`：文本模式，强调 accessibility tree。

提示词设计的核心约束：

- 每次只能一个动作。
- 输入文本不需要先点击。
- 不要连续重复同一动作。
- 只有任务全部完成后才能 `ANSWER`。
- 要关注筛选、排序、日期等任务条件。

如果你要评测自己的项目，一般不需要先改 prompt。只有当你的页面有非常特殊交互，比如地图拖拽、画布操作、复杂快捷键，才考虑扩展动作协议。

## `evaluation/auto_eval.py`

### `auto_eval_by_gpt4v(process_dir, openai_client, api_model, img_num)`

单任务评测函数。

它读取：

```text
process_dir/interact_messages.json
process_dir/screenshot*.png
```

然后抽取：

- 原始任务。
- 最终回答。
- 最后 `img_num` 张截图。

最后让模型输出 `SUCCESS` 或 `NOT SUCCESS`。

### `main()`

当前 `main()` 写死了 15 个 WebVoyager 网站名和 `0..45` 编号区间：

```python
webs = ['Allrecipes', 'Amazon', ...]
for web in webs:
    for idx in range(0, 46):
        file_dir = os.path.join(args.process_dir, 'task'+web+'--'+str(idx))
```

这对原论文数据集方便，但对你的项目不通用。后续要评测你自己的项目，建议优先改这里，让它遍历 `args.process_dir` 下所有含 `interact_messages.json` 的任务目录。

