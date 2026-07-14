# 本仓库中的智能体

## 概述

本仓库演示如何使用 LangGraph 构建智能体，重点是一个能够完成以下工作的邮件助手：
- 分诊收到的邮件
- 起草恰当回复
- 执行操作（日程安排等）
- 纳入人工反馈
- 从过往交互中学习


## 环境配置

**推荐：使用 uv（更快且更可靠）**

```bash
# 如尚未安装，请安装 uv
pip install uv

# 安装包含开发依赖的包
uv sync --extra dev
```

**替代方案：使用 pip**

```bash
# 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 确保 pip 为较新版本（使用 pyproject.toml 进行可编辑安装时需要）
python3 -m pip install --upgrade pip

# 以可编辑模式安装包
pip install -e .
```

## 智能体实现

### 脚本

`src/email_assistant` 中包含复杂度逐步提升的多个实现：

1. **LangGraph 101**（`langgraph_101.py`）
   - LangGraph 基础

2. **基础邮件助手**（`email_assistant.py`）
   - 核心邮件分诊和回复功能

3. **人工介入**（`email_assistant_hitl.py`）
   - 支持人工审查和批准操作

4. **启用记忆的 HITL**（`email_assistant_hitl_memory.py`）
   - 添加持久记忆以从反馈中学习

5. **Gmail 集成**（`email_assistant_hitl_memory_gmail.py`）
   - 连接 Gmail API 处理真实邮件

### 笔记本

各个智能体主题均在专门的笔记本中讲解：
- `notebooks/langgraph_101.ipynb` - LangGraph 基础
- `notebooks/agent.ipynb` - 基础智能体实现
- `notebooks/evaluation.ipynb` - 智能体评估
- `notebooks/hitl.ipynb` - 人工介入功能
- `notebooks/memory.ipynb` - 添加记忆能力

## 运行测试

### 测试脚本

运行测试以确认各实现正常工作：

```bash
# 测试所有实现
python tests/run_all_tests.py --all
```

（注意：该命令不测试 Gmail 实现 `email_assistant_hitl_memory_gmail`。）

### 测试笔记本

测试全部笔记本，确保执行时不会出错：

```bash
# 直接运行全部笔记本测试
python tests/test_notebooks.py
```
