# Agents from Scratch

## 学习方法：能力闭环，而非按目录打卡

不要按源码文件从头读到尾，也不要完整手撸整个项目。那种方式容易产生“看懂了、下次仍不会设计”的熟悉感，且在断续学习时反复热身、收益很低。

后续采用**问题实验室**方式：一次学习只攻克一个 Agent 设计问题，在同一闭环内完成预测、实现、验证和复盘。源码是用来对照设计的参考，不是待逐行抄写的清单。

每个专题按下面的固定节奏进行，尽量连续完成（建议 90–150 分钟）：

1. **场景与预测**：先给出一个具体失败场景或业务约束；不看实现，画出状态流转，预测当前行为和风险。
2. **最小定位**：只阅读解决该问题所需的提示词、状态、节点、工具和测试，不扩散到无关模块。
3. **最小改动**：自己决定应修改提示词、工具 schema/权限、图路由、中断逻辑还是状态；只实现能验证假设的最小变更。
4. **证据验证**：先写或补充评估样本/断言，再运行验证正常、模糊、越权、高风险和失败路径。
5. **设计复盘**：用自己的话记录“风险—决策—状态变化—测试证据”；最后才对照原实现，解释差异与取舍。

只有关键机制采用“选择性盲写”：脱离源码重建一个 60–90 分钟的最小骨架，或重建一个 HITL 恢复路径。**不重写整个项目**；Gmail、OAuth、定时任务和配置脚手架以读懂、能修改为目标。

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
- [x] `email_assistant_002.py`：已独立完成基础版并通过验证。
  - [x] 内层 `response_agent` 已完成并通过导入/编译验证：`START → llm_call → should_continue → tool_node → llm_call`；无 `tool_calls` 时到 `END`。
  - [x] `llm_call`：将结构化邮件信息与历史 `messages` 交给绑定工具的 LLM，并将 AI 消息返回给状态。
  - [x] `should_continue`：以最后一条 AI 消息的 `tool_calls` 是否为空为条件，路由至 `tool_node` 或 `END`。
  - [x] `tool_node`：按工具名执行全部工具调用，并以携带原始 `tool_call_id` 的 `ToolMessage` 返回本轮结果。
  - [x] 外层节点 `triage_router(state)` 已完成并通过本地替身验证。
    1. 返回 `Command[Literal["response_agent", "__end__"]]`，下一跳仅为 `response_agent` 或 `END`。
    2. 支持 `email_input` 与聊天消息两种入口；聊天消息会标准化为 `from_email`、`to_email`、`subject`、`page_content`。
    3. 使用 `RouterSchema` 获取 `ignore / notify / respond` 结构化分类，并通过 `Command` 写入 `email_input` 和 `classification_decision`。
    4. 已验证三种分类：仅 `respond` 路由至 `response_agent`，其余分类结束。
  - [x] 外层 `StateGraph(State, input_schema=StateInput)` 已完成：`START → triage_router → response_agent / END`，并已编译为 `email_assistant`。
  - [x] 通过本地 LLM 替身完成端到端路由验证：`ignore` 与 `notify` 直接结束，`respond` 进入 `response_agent` 并返回回复。
  - [ ] 当前任务：阅读并解释 `prompts.py` 与 `tools/default/`，明确分诊/回复提示词的职责边界，以及每个工具的输入 schema、权限和终止条件。

## 能力专题与投入边界

| 专题 | 必须掌握的问题 | 深入范围 | 验收证据 | 学习方式 |
| --- | --- | --- | --- | --- |
| 工具边界 | 模型何时该调用工具，工具如何拒绝越权/失败输入 | `prompts.py`、`tools/default/`、相关测试 | 工具权限表；成功、拒绝、失败三类断言 | 审计一个默认工具并做最小改造 |
| 人工介入（HITL） | 哪些副作用必须审批；批准、编辑、拒绝后图如何恢复或结束 | `email_assistant_hitl.py` | 状态图；三条恢复路径测试 | 选择性盲写一个关键中断路径 |
| 评估与回归 | 如何证明改动有效且没有退化 | `eval/`、`tests/` | 15–20 条数据集，覆盖正常/模糊/越权/高风险/工具失败 | 每次改动先补断言，再实现 |
| 长期记忆 | checkpoint 与 Store 的区别；何时读写偏好，如何避免污染 | `email_assistant_hitl_memory.py` | 一次人工修正影响下一次回复的端到端测试 | 在前 3 个专题完成后再做精简实验 |

下面内容保留在项目中，但不作为当前的深度练习对象：

- **读懂并能修改即可**：`configuration.py`、`models.py`、`utils.py`。
- **明确暂缓**：`email_assistant_hitl_memory_gmail.py`、`tools/gmail/`、`cron.py`、OAuth 和部署。它们是工程接入层，等核心 Agent 能力稳定后再处理。

## 原优先级参考

| 学习序号 | 优先级等级 | 模块 | 应掌握的能力 | 是否手撸 | 进度 |
| --- | --- | --- | --- | --- | --- |
| 1 | P0（必须） | `schemas.py`、`email_assistant.py`、`email_assistant_002.py` | State 的定义；`Command(goto=...)` 路由；LLM 与工具节点的循环 | 是，独立重写基础版 | 已完成 |
| 2 | P0（必须） | `prompts.py`、`tools/default/` | 为什么分拆“分诊”和“回复”；工具 schema、权限与终止条件 | 是，换一个小业务改写 | 进行中 |
| 3 | P0（必须） | `email_assistant_hitl.py` | 哪些动作必须审批；`interrupt()` 后如何恢复；批准、编辑、拒绝的状态语义 | 是，重写一次关键路径 | 未开始 |
| 4 | P0（必须） | `eval/`、`tests/` | 测量分诊准确性、工具调用、回复质量和回归，而不只是看能否运行 | 是，新增自己的数据集和断言 | 未开始 |
| 5 | P1（重点） | `email_assistant_hitl_memory.py` | 区分 checkpoint（恢复执行）和 Store（跨会话偏好）；理解记忆读写时机及污染风险 | 建议手撸精简版 | 未开始 |
| 6 | P2（部分关注） | `configuration.py`、`models.py`、`utils.py` | 配置、模型封装与可测试性 | 读懂并能修改 | 未开始 |
| 7 | P2（部分关注） | `email_assistant_hitl_memory_gmail.py`、`tools/gmail/`、`cron.py` | OAuth、真实副作用、幂等、已读标记、定时触发和部署边界 | 暂不必全手撸 | 未开始 |

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

## 推荐的专题练习

不要先复刻 Gmail 集成，也不要把完整邮件助手再写一遍。更有效的练习是，以基础 Agent 为底做一个有边界的小型改造：例如工单助手或会议请求助手。

1. 先从一个“工具越权或工具失败”的场景开始，审计 `prompts.py` 和 `tools/default/`，写出工具的输入、权限、失败与终止条件。
2. 再从 `email_assistant_hitl.py` 处理一个“发送或创建操作需要审批”的场景，画出批准、编辑、拒绝三条状态路径。
3. 为前两步加入 10–20 条评估样本，至少覆盖：正常、模糊、越权、高风险、工具失败；以此作为后续提示词和工具改动的回归基线。
4. 最后才让一次人工修改提炼为一条用户偏好记忆，并验证它会影响下一次回答。

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
