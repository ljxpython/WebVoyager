# WebVoyager 代码走读

这个目录记录老王对当前 WebVoyager 项目的代码上手笔记。目标不是复述论文，而是把这个仓库怎么跑、怎么观测网页、怎么让模型决策、怎么保存轨迹、怎么做评测讲清楚，方便后续拿它评测你自己的项目。

## 阅读顺序

1. [项目地图](01-project-map.md)：先知道每个目录和核心文件管什么。
2. [运行主链路](02-runtime-flow.md)：按 `run.py` 的执行顺序走一遍，一眼看懂 agent loop。
3. [模块代码走读](03-module-walkthrough.md)：逐个模块看关键函数、输入输出和坑点。
4. [评测接入指南](04-evaluation-adaptation.md)：把它改造成评测你自己项目的工具链。

## 一句话架构

WebVoyager 是一个 `Selenium 浏览器环境 + 网页截图/可访问性树观测 + OpenAI 模型决策 + 动作解析执行 + 轨迹保存 + 视觉评测` 的网页智能体评测项目。

每轮循环的核心是：

```text
打开网页 -> 标注可交互元素 -> 截图/抽 accessibility tree -> 请求模型 -> 解析 Action -> Selenium 执行动作 -> 保存轨迹
```

## 当前仓库关键结论

- 主入口是 `run.py`，不是 `README.md` 里的脚本本身。
- 任务格式是 JSONL，每行至少需要 `id`、`ques`、`web`。
- 普通模式依赖截图和网页元素编号；`--text_only` 模式依赖 accessibility tree。
- 模型必须严格输出 `Thought:` 和 `Action:`，否则主循环会把它当格式错误。
- 结果目录里最有价值的是 `interact_messages.json` 和每轮 `screenshotN.png`。
- 自动评测在 `evaluation/auto_eval.py`，它不复跑网页，只读取已保存轨迹和最后若干张截图。

