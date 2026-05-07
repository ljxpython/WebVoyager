# WebVoyager 本地使用文档

这份文档用于后续验证测试。当前项目已经适配 `uv` 虚拟环境和 `.env` 中的豆包 OpenAI-compatible 配置。

## 1. 前置条件

需要准备：

- macOS 上已安装 Google Chrome。
- 已安装 `uv`。
- 项目根目录存在 `.env`。
- `.env` 里有豆包模型配置：

```bash
DOUBAO_API_KEY=你的 key
DOUBAO_API_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_API_MODEL=doubao-seed-2-0-pro-260215
```

`.env` 已经在 `.gitignore` 中，别把 key 提交上去。这个要是泄漏了，老王能当场把键盘敲冒烟。

## 2. 安装环境

如果 `.venv` 已经存在，可以跳过创建虚拟环境。

```bash
uv python install "3.10"
uv venv ".venv" --python "3.10"
uv pip install --python ".venv/bin/python" -r "requirements.txt"
```

验证依赖：

```bash
uv run python -c "import openai, httpx, selenium, PIL, numpy; print(openai.__version__, httpx.__version__, selenium.__version__, PIL.__version__, numpy.__version__)"
```

预期版本大致是：

```text
openai 1.1.1
httpx 0.27.2
selenium 4.15.2
pillow 10.1.0
numpy 2.2.6
```

## 3. 验证浏览器可用

```bash
uv run python -c "from selenium import webdriver; options = webdriver.ChromeOptions(); options.add_argument('--headless'); driver = webdriver.Chrome(options=options); print(driver.capabilities.get('browserName'), driver.capabilities.get('browserVersion')); driver.quit()"
```

能输出 `chrome <版本号>` 就说明 Selenium 能拉起 Chrome。

## 4. 验证 env 配置可读

这个命令不会打印 key，只验证模型和 base URL：

```bash
uv run python -c "import os, run; run.load_env_file('.env'); print(os.getenv('DOUBAO_API_MODEL')); print(os.getenv('DOUBAO_API_URL'))"
```

预期能看到：

```text
doubao-seed-2-0-pro-260215
https://ark.cn-beijing.volces.com/api/v3
```

## 5. 任务文件

默认测试文件：

```text
data/tasks_test.jsonl
```

每行一个任务，格式类似：

```json
{"web_name":"Cambridge Dictionary","id":"Cambridge Dictionary--29","ques":"Go to the Plus section of Cambridge Dictionary, find Image quizzes and do an easy quiz about Animals and tell me your final score.","web":"https://dictionary.cambridge.org/"}
```

核心字段：

- `id`：任务结果目录名的一部分。
- `ques`：Agent 要完成的自然语言任务。
- `web`：起始网页。

## 6. 最小试运行

推荐先跑 2 轮 smoke test，验证浏览器、截图、模型调用、动作解析能通：

```bash
uv run python "run.py" \
  --test_file "data/tasks_test.jsonl" \
  --headless \
  --max_iter 2 \
  --max_attached_imgs 1 \
  --fix_box_color
```

说明：

- 不传 `--api_key` 时，`run.py` 会自动从 `.env` 读取 `DOUBAO_API_KEY`。
- 不传 `--api_model` 时，会自动读取 `DOUBAO_API_MODEL`。
- 不传 `--api_base` 时，会自动读取 `DOUBAO_API_URL`。
- `max_iter 2` 不保证完成任务，只验证链路。

## 7. 正式一点的单任务运行

```bash
uv run python "run.py" \
  --test_file "data/tasks_test.jsonl" \
  --headless \
  --max_iter 15 \
  --max_attached_imgs 3 \
  --fix_box_color \
  --seed 42
```

也可以直接用脚本：

```bash
bash "run.sh"
```

`run.sh` 会自动 `source .env`，默认使用 `.venv/bin/python`。

## 8. 结果目录怎么看

运行结果会写到：

```text
results/<timestamp>/task<任务id>/
```

重点看：

```text
agent.log
interact_messages.json
screenshot1.png
screenshot2.png
...
```

解释：

- `screenshotN.png`：每轮网页截图，含元素编号框。
- `interact_messages.json`：每轮 prompt、模型回复、动作记录。
- `agent.log`：token、错误、任务结束信息。

如果模型最终输出 `ANSWER; ...`，说明 WebVoyager 认为任务完成。注意，这不等于任务真实成功，还要看截图和最终答案是否对得上。

## 9. 常见问题

### OpenAI client 报 `proxies`

说明 `httpx` 版本太新，和 `openai==1.1.1` 不兼容。当前已经在 `requirements.txt` 固定：

```text
httpx==0.27.2
```

重新安装即可：

```bash
uv pip install --python ".venv/bin/python" -r "requirements.txt"
```

### 报 `No module named numpy`

旧仓库 `requirements.txt` 漏写了 `numpy`。当前已补：

```text
numpy==2.2.6
```

### API 报认证错误

检查 `.env`：

```bash
uv run python -c "import os, run; run.load_env_file('.env'); print(bool(os.getenv('DOUBAO_API_KEY')))"
```

输出 `True` 才说明 key 被读取到了。

### 模型输出格式错误

WebVoyager 要求模型必须输出：

```text
Thought: ...
Action: ...
```

如果豆包模型不稳定输出这个格式，`run.py` 会把格式错误回传给模型，让它下一轮修正。多次出错就要考虑改 prompt 或加一层输出修复。

### 浏览器打不开

先检查 Chrome：

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version
```

再跑 Selenium 最小验证，见第 3 节。

## 10. 当前改造点

当前仓库已做这些适配：

- `run.py` 支持 `--api_base` 和 `--env_file`。
- `run.py` 自动读取 `.env` 中的豆包配置。
- `run.sh` 自动加载 `.env`。
- `.gitignore` 忽略 `.env`、`.idea/`、`.venv/`。
- `requirements.txt` 补齐 `httpx` 和 `numpy`。

## 11. 建议验证顺序

按这个顺序来，别一上来就跑完整任务集：

1. 验证依赖 import。
2. 验证 Chrome/Selenium。
3. 验证 `.env` 配置读取。
4. 跑 `max_iter 2` smoke test。
5. 看 `results/<timestamp>/task.../screenshot1.png`。
6. 看 `interact_messages.json` 是否有模型回复。
7. 再跑 `max_iter 15` 的完整单任务。
