# Agents from Scratch

## 当前阶段与目标

你已经完成了 `langgraph-101` 的手撸实践，也已在 LangGraph Studio 中运行过本项目的完整 `src`。因此，下一阶段不需要再把整个项目逐行照抄一遍。

更合适的目标是：

1. 能解释每个状态为什么、如何流转。
2. 能安全地修改成自己的业务版本。
3. 能用评估证明自己的改动有效，而不只是“能跑”。

官方项目按四层能力递进：基础 Agent、评估、人工介入（HITL）、长期记忆，最后才接入 Gmail。它是一个“邮件环境智能体”的参考实现；新版 `langgraph-101` 则进一步覆盖 middleware、多智能体和深度研究等生产模式。

- [agents-from-scratch](https://github.com/langchain-ai/agents-from-scratch)
- [langgraph-101](https://github.com/langchain-ai/langgraph-101)

## 学习进度

- [x] `schemas.py`：已独立完成并验收 `RouterSchema`、`StateInput`、`State`、`EmailData` 和 `UserPreferences`。
  - 能解释入口状态与运行期状态的边界：`StateInput.email_input` 可缺省以支持聊天消息入口；进入图后，`State.email_input` 作为后续节点依赖的数据必须存在。
  - 能解释 `Literal["ignore", "respond", "notify"]` 同时约束结构化模型输出与图路由的合法下一跳。
- [x] `email_assistant.py`：已完成基础双层图的流程理解验收。
  - 外层图：`triage_router → response_agent / END`，负责邮件分诊与是否进入处理流程的决策。
  - 内层图：`llm_call → should_continue → tool_node → llm_call`，模型根据工具结果迭代，直至不再产生 `tool_calls` 后结束。
  - 能解释 `Command(goto=...)` 用于指定图的下一节点，并可同时更新状态。
- [ ] `email_assistant_002.py`：开始独立手撸基础版；当前进行第 1A 步——先定义 `llm_call`、`tool_node`、`should_continue`、`triage_router` 的职责与状态读写边界，再构建内层图和外层图。

## 优先级

| 学习序号 | 优先级等级 | 模块 | 应掌握的能力 | 是否手撸 |
| --- | --- | --- | --- | --- |
| 1 | P0（必须） | `schemas.py`、`email_assistant.py` | State 的定义；`Command(goto=...)` 路由；LLM 与工具节点的循环 | 是，独立重写基础版 |
| 2 | P0（必须） | `prompts.py`、`tools/default/` | 为什么分拆“分诊”和“回复”；工具 schema、权限与终止条件 | 是，换一个小业务改写 |
| 3 | P0（必须） | `email_assistant_hitl.py` | 哪些动作必须审批；`interrupt()` 后如何恢复；批准、编辑、拒绝的状态语义 | 是，重写一次关键路径 |
| 4 | P0（必须） | `eval/`、`tests/` | 测量分诊准确性、工具调用、回复质量和回归，而不只是看能否运行 | 是，新增自己的数据集和断言 |
| 5 | P1（重点） | `email_assistant_hitl_memory.py` | 区分 checkpoint（恢复执行）和 Store（跨会话偏好）；理解记忆读写时机及污染风险 | 建议手撸精简版 |
| 6 | P2（部分关注） | `configuration.py`、`models.py`、`utils.py` | 配置、模型封装与可测试性 | 读懂并能修改 |
| 7 | P2（部分关注） | `email_assistant_hitl_memory_gmail.py`、`tools/gmail/`、`cron.py` | OAuth、真实副作用、幂等、已读标记、定时触发和部署边界 | 暂不必全手撸 |

## 核心心智模型

```text
邮件输入
  → triage_router：ignore / notify / respond / 需要人工确认
  → response_agent：LLM ↔ tool loop
  → interrupt_handler：高风险工具调用停下来等待人
  → memory：从反馈抽取“用户偏好”，下次注入提示词
  → （Gmail 版）真实发信、日历、已读标记、定时触发
```

## 重点代码导航

按下面的顺序阅读、调试和改写代码：

1. 基础双层图：`triage_router` 与内嵌 Agent/tool loop。
   - `src/email_assistant/email_assistant.py`
   - 重点：`llm_call`、`tool_node`、`should_continue`、`triage_router` 和图构建部分。

2. 人工介入：中断、审批和恢复执行。
   - `src/email_assistant/email_assistant_hitl.py`
   - 重点：`triage_interrupt_handler`、`interrupt_handler` 和 `should_continue`。

3. 长期记忆：偏好读取、更新和注入到 Agent。
   - `src/email_assistant/email_assistant_hitl_memory.py`
   - 重点：`get_memory`、`update_memory`、两个 interrupt handler 和图构建部分。

4. 评估：把“运行成功”变成“行为可信”。
   - `src/email_assistant/eval/evaluate_triage.py`
   - `src/email_assistant/eval/email_dataset.py`
   - `tests/`

## 推荐的手撸练习

不要先复刻 Gmail 集成。更有效的练习是，以基础 Agent 为底做一个有边界的小型改造：例如工单助手或会议请求助手。

1. 从 `email_assistant.py` 开始，保留 `triage → agent → tool loop`。
2. 自行设计 `State` 与 2–3 个工具。
3. 为发送、创建、删除等有副作用的操作接入 HITL。
4. 让一次人工修改提炼为一条用户偏好记忆，并验证它会影响下一次回答。
5. 新增 10–20 条评估样本，至少覆盖：正常、模糊、越权、高风险、工具失败。

## 完成标准

不看原项目源码时，能在 60–90 分钟内实现上述精简助手，并清楚回答：

- 状态在哪里持久化？
- 人工拒绝后图如何继续或结束？
- 记忆为什么不等同于聊天历史？
- 如何避免模型未经确认就发送邮件或创建日程？
- 如何用评估发现一次提示词或工具改动造成的回归？

达到这些标准，才算真正掌握这个项目，而不只是能够在 Studio 中运行它。

## 暂缓投入的部分

Gmail OAuth、定时任务和部署属于工程接入层。它们很重要，但不是当前最核心的 Agent 能力。优先补齐评估：这是最容易在 Demo 阶段被跳过、却最能将系统变得可迭代和可信的一层。
