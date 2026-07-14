# Agents From Scratch 

The repo is a guide to building agents from scratch. It builds up to an ["ambient"](https://blog.langchain.dev/introducing-ambient-agents/) agent that can manage your email with connection to the Gmail API. It's grouped into 4 sections, each with a notebook and accompanying code in the `src/email_assistant` directory. These section build from the basics of agents, to agent evaluation, to human-in-the-loop, and finally to memory. These all come together in an agent that you can deploy, and the principles can be applied to other agents across a wide range of tasks. 

![overview](notebooks/img/overview.png)

## Environment Setup 

### Python Version

* Ensure you're using Python 3.11 or later. 
* This version is required for optimal compatibility with LangGraph. 

```shell
python3 --version
```

### API Keys

* 开通[阿里云百炼](https://bailian.console.aliyun.com/)并创建 API Key。
* Sign up for LangSmith [here](https://smith.langchain.com/).
* Generate a LangSmith API key.

### Set Environment Variables

* Create a `.env` file in the root directory:
```shell
# Copy the .env.example file to .env
cp .env.example .env
```

* Edit the `.env` file with the following:
```shell
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT="interrupt-workshop"
DASHSCOPE_API_KEY=your_dashscope_api_key
# 可选：默认使用 qwen-plus
QWEN_MODEL=qwen-plus
# 可选：北京地域的百炼 OpenAI 兼容接口为默认值
# DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

* You can also set the environment variables in your terminal:
```shell
export LANGSMITH_API_KEY=your_langsmith_api_key
export LANGSMITH_TRACING=true
export DASHSCOPE_API_KEY=your_dashscope_api_key
```

本项目使用 `langchain-openai` 的 `ChatOpenAI` 适配器调用百炼的 OpenAI 兼容接口；它不需要 OpenAI API Key。请确保环境中已安装 `langchain-openai`。

### Package Installation

**Recommended: Using uv (faster and more reliable)**

```shell
# Create a virtual environment
uv venv

# Install project dependencies
uv pip install -r requirements.txt

# Activate the virtual environment
source .venv/bin/activate
```

**Alternative: Using pip**

```shell
$ python3 -m venv .venv
$ source .venv/bin/activate
# Ensure you have a recent version of pip
$ python3 -m pip install --upgrade pip
# Install project dependencies
$ pip install -r requirements.txt
```

> **⚠️ IMPORTANT**: 安装依赖后，请从项目根目录执行脚本或设置 `PYTHONPATH=src`，以便 Python 能找到 `email_assistant` 包。

## Structure 

The repo is organized into the 4 sections, with a notebook for each and accompanying code in the `src/email_assistant` directory.

### Preface: LangGraph 101
For a brief introduction to LangGraph and some of the concepts used in this repo, see the [LangGraph 101 notebook](notebooks/langgraph_101.ipynb). This notebook explains the basics of chat models, tool calling, agents vs workflows, LangGraph nodes / edges / memory, and LangGraph Studio.

### Building an agent 
* Notebook: [notebooks/agent.ipynb](/notebooks/agent.ipynb)
* Code: [src/email_assistant/email_assistant.py](/src/email_assistant/email_assistant.py)

![overview-agent](notebooks/img/overview_agent.png)

This notebook shows how to build the email assistant, combining an [email triage step](https://langchain-ai.github.io/langgraph/tutorials/workflows/) with an agent that handles the email response. You can see the linked code for the full implementation in `src/email_assistant/email_assistant.py`.

![Screenshot 2025-04-04 at 4 06 18 PM](notebooks/img/studio.png)

### Evaluation 
* Notebook: [notebooks/evaluation.ipynb](/notebooks/evaluation.ipynb)

![overview-eval](notebooks/img/overview_eval.png)

This notebook introduces evaluation with an email dataset in [eval/email_dataset.py](/eval/email_dataset.py). It shows how to run evaluations using Pytest and the LangSmith `evaluate` API. It runs evaluation for emails responses using LLM-as-a-judge as well as evaluations for tools calls and triage decisions.

![Screenshot 2025-04-08 at 8 07 48 PM](notebooks/img/eval.png)

### Human-in-the-loop 
* Notebook: [notebooks/hitl.ipynb](/notebooks/hitl.ipynb)
* Code: [src/email_assistant/email_assistant_hitl.py](/src/email_assistant/email_assistant_hitl.py)

![overview-hitl](notebooks/img/overview_hitl.png)

This notebooks shows how to add human-in-the-loop (HITL), allowing the user to review specific tool calls (e.g., send email, schedule meeting). For this, we use [Agent Inbox](https://github.com/langchain-ai/agent-inbox) as an interface for human in the loop. You can see the linked code for the full implementation in [src/email_assistant/email_assistant_hitl.py](/src/email_assistant/email_assistant_hitl.py).

![Agent Inbox showing email threads](notebooks/img/agent-inbox.png)

### Memory  
* Notebook: [notebooks/memory.ipynb](/notebooks/memory.ipynb)
* Code: [src/email_assistant/email_assistant_hitl_memory.py](/src/email_assistant/email_assistant_hitl_memory.py)

![overview-memory](notebooks/img/overview_memory.png)  

This notebook shows how to add memory to the email assistant, allowing it to learn from user feedback and adapt to preferences over time. The memory-enabled assistant ([email_assistant_hitl_memory.py](/src/email_assistant/email_assistant_hitl_memory.py)) uses the [LangGraph Store](https://langchain-ai.github.io/langgraph/concepts/memory/#long-term-memory) to persist memories. You can see the linked code for the full implementation in [src/email_assistant/email_assistant_hitl_memory.py](/src/email_assistant/email_assistant_hitl_memory.py).

## Connecting to APIs  

The above notebooks using mock email and calendar tools. 

### Gmail Integration and Deployment

Set up Google API credentials following the instructions in [Gmail Tools README](src/email_assistant/tools/gmail/README.md).

The README also explains how to deploy the graph to LangGraph Platform.

The full implementation of the Gmail integration is in [src/email_assistant/email_assistant_hitl_memory_gmail.py](/src/email_assistant/email_assistant_hitl_memory_gmail.py).

## Running Tests

The repository includes an automated test suite to evaluate the email assistant. 

Tests verify correct tool usage and response quality using LangSmith for tracking.

### Running Tests with [run_all_tests.py](/tests/run_all_tests.py)

```shell
python tests/run_all_tests.py
```

### Test Results

Test results are logged to LangSmith under the project name specified in your `.env` file (`LANGSMITH_PROJECT`). This provides:
- Visual inspection of agent traces
- Detailed evaluation metrics
- Comparison of different agent implementations

### Available Test Implementations

The available implementations for testing are:
- `email_assistant` - Basic email assistant

### Testing Notebooks

You can also run tests to verify all notebooks execute without errors:

```shell
# Run all notebook tests
python tests/test_notebooks.py

# Or run via pytest
pytest tests/test_notebooks.py -v
```

## Future Extensions

Add [LangMem](https://langchain-ai.github.io/langmem/) to manage memories:
* Manage a collection of background memories. 
* Add memory tools that can look up facts in the background memories. 

## 项目结构

```text
.
├── AGENTS.md                         # 面向编码智能体的仓库协作说明
├── CLAUDE.md                         # 补充的仓库开发指引
├── README.md                         # 项目概览、环境配置与使用说明
├── langgraph.json                    # LangGraph 图定义与部署配置
├── notebooks/                        # 分阶段讲解的教程 Notebook
│   ├── langgraph_101.ipynb           # LangGraph 基础知识
│   ├── agent.ipynb                   # 基础邮件助手
│   ├── evaluation.ipynb              # 评估流程
│   ├── hitl.ipynb                    # 人工参与（HITL）流程
│   ├── memory.ipynb                  # 持久化记忆流程
│   ├── test_tools.py                 # Notebook 工具辅助检查
│   └── img/                          # Notebook 和 README 使用的图片资源
├── src/
│   └── email_assistant/              # 邮件助手 Python 包
│       ├── langgraph_101.py          # LangGraph 入门示例
│       ├── email_assistant.py        # 基础邮件分类与回复智能体
│       ├── email_assistant_hitl.py   # 支持人工审核操作的智能体
│       ├── email_assistant_hitl_memory.py
│       │                             # 带持久化记忆的 HITL 智能体
│       ├── email_assistant_hitl_memory_gmail.py
│       │                             # 集成 Gmail 的记忆型智能体
│       ├── configuration.py          # 运行时配置模型
│       ├── schemas.py                # 通用数据结构定义
│       ├── prompts.py                # 邮件分类和回复生成提示词
│       ├── utils.py                  # 工作流与消息处理工具函数
│       ├── cron.py                   # 定时拉取 Gmail 邮件的图
│       ├── eval/                     # 邮件数据集和评估工具
│       │   ├── email_dataset.py
│       │   ├── evaluate_triage.py
│       │   └── prompts.py
│       └── tools/                    # 智能体可调用的工具实现
│           ├── base.py               # 通用工具抽象
│           ├── default/              # 用于本地演示的模拟邮件和日历工具
│           └── gmail/                # Gmail API 工具及初始化脚本
└── tests/                            # 自动化测试
    ├── conftest.py                   # Pytest 配置和自定义参数
    ├── run_all_tests.py              # 智能体评估测试套件入口
    ├── test_response.py              # 工具调用和回复质量测试
    └── test_notebooks.py             # Notebook 执行测试
```

本项目围绕“逐步增强的邮件助手”组织：`notebooks` 用于分阶段讲解实现思路，`src/email_assistant` 提供可运行的 LangGraph 实现、提示词、工具和评估组件，`tests` 负责验证基础邮件助手与 Notebook。Gmail 的配置和集成代码位于 `src/email_assistant/tools/gmail`。
