# 01 项目地图

## 项目定位

这个仓库实现的是 WebVoyager：一个端到端网页智能体。它不会托管你自己的网页，也不是传统后端服务。它做的事情是让大模型通过 Selenium 操作真实浏览器，完成自然语言任务，然后保存执行轨迹，最后可选用视觉模型判断任务是否成功。

适合拿来做这类评测：

- Web 应用能否被智能体顺利使用。
- 页面可交互元素是否清晰可见、可点击、可输入。
- 搜索、筛选、排序、详情页跳转等流程是否能被多模态模型完成。
- 最终回答是否和网页状态一致。

不适合直接评测这类内容：

- 纯后端 API 正确性。
- 不打开浏览器的离线算法。
- 需要登录、验证码、支付、隐私数据输入的生产流程。

## 顶层目录

```text
.
├── assets/                 # README 图片和论文示意图
├── data/                   # 任务集和参考答案
├── downloads/              # 浏览器下载目录，运行时会被清理
├── evaluation/             # 自动评测脚本
├── results/                # agent 运行结果和示例轨迹
├── prompts.py              # 模型系统提示词和动作协议
├── requirements.txt        # Python 依赖
├── run.py                  # 主运行入口
├── run.sh                  # 示例启动脚本
├── utils.py                # 截图标注、动作解析、消息裁剪、PDF 处理
└── utils_webarena.py       # accessibility tree 抽取和清洗
```

## 核心文件职责

### `run.py`

项目主驾驶员，负责：

- 解析命令行参数。
- 创建 OpenAI client。
- 配置和启动 Chrome。
- 加载 JSONL 任务。
- 对每个任务执行多轮 agent loop。
- 保存截图、日志、交互消息。
- 根据模型输出执行 Selenium 动作。

最关键的函数是：

- `driver_config(args)`：配置 Chrome，包括 headless、下载目录、device scale。
- `format_msg(...)`：视觉模式下把任务、元素文本、截图组装成模型消息。
- `format_msg_text_only(...)`：文本模式下把任务和 accessibility tree 组装成模型消息。
- `call_gpt4v_api(...)`：调用 OpenAI Chat Completions。
- `exec_action_click/type/scroll(...)`：执行模型选择的动作。
- `main()`：完整任务调度和循环。

### `prompts.py`

定义模型行动协议。模型每轮必须输出：

```text
Thought: ...
Action: ...
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

这套格式不是装饰，`utils.extract_information()` 会用正则硬解析。输出一歪，程序就开始骂街式失败。

### `utils.py`

工具大杂烩，但核心有三块：

- `get_web_element_rect(...)`：往页面里注入 JS，找可交互元素，画编号框，返回 Selenium 元素列表和元素文本摘要。
- `extract_information(text)`：把模型动作字符串解析成内部 action key 和参数。
- `clip_message_and_obs(...)`：裁剪历史消息，只保留最近若干张图片，控制 token 和上下文噪声。

另外它还处理：

- 图片 base64 编码。
- 交互消息落盘。
- PDF 下载后的 Assistant API 检索。
- accessibility tree 包装调用。

### `utils_webarena.py`

借鉴 WebArena 的可访问性树逻辑，使用 Chrome DevTools Protocol 抓取页面结构：

- `fetch_browser_info(...)` 抓 DOM snapshot 和浏览器窗口配置。
- `fetch_page_accessibility_tree(...)` 抓完整 AXTree 并过滤当前视口外节点。
- `parse_accessibility_tree(...)` 把树转成模型可读文本。
- `clean_accesibility_tree(...)` 清掉重复静态文本。

文本模式 `--text_only` 靠它，不走截图理解。

### `evaluation/auto_eval.py`

自动评测脚本。它不会重新操作网页，只做离线判断：

1. 读取某个任务结果目录里的 `interact_messages.json`。
2. 抽取原始任务和最终 `ANSWER`。
3. 读取最后若干张 `screenshotN.png`。
4. 发给视觉模型判断 `SUCCESS` 或 `NOT SUCCESS`。

这个评测方式适合快速批量看趋势，但不是绝对真理。页面截图和最终回答矛盾时，脚本提示词倾向以截图为准。

## 数据文件

### `data/WebVoyager_data.jsonl`

完整任务集。每行一个任务，结构类似：

```json
{"web_name":"Allrecipes","id":"Allrecipes--0","ques":"...","web":"https://www.allrecipes.com/"}
```

### `data/tasks_test.jsonl`

当前运行脚本默认使用的测试任务文件。你后续评测自己的项目，最直接就是替换或新建这个 JSONL。

### `data/reference_answer.json`

人工参考答案。当前自动评测脚本没有直接读取它做严格匹配，主要还是用模型根据任务、最终回答和截图判断。

## 输出文件

一次运行会生成：

```text
results/<timestamp>/
└── task<id>/
    ├── agent.log
    ├── interact_messages.json
    ├── screenshot1.png
    ├── screenshot2.png
    └── ...
```

如果启用 `--save_accessibility_tree`，还会保存：

```text
accessibility_tree1.json
accessibility_tree1.txt
```

如果任务下载 PDF，PDF 会复制到当前任务结果目录。

