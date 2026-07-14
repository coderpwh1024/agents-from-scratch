from typing import Literal

from email_assistant.tools import get_tools, get_tools_by_name
from email_assistant.models import get_chat_model
from email_assistant.tools.default.prompt_templates import AGENT_TOOLS_PROMPT
from email_assistant.prompts import triage_system_prompt, triage_user_prompt, agent_system_prompt, default_background, default_triage_instructions, default_response_preferences, default_cal_preferences
from email_assistant.schemas import State, RouterSchema, StateInput
from email_assistant.utils import parse_email, format_email_markdown

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from dotenv import load_dotenv
load_dotenv(".env")

# 获取工具
tools = get_tools()
tools_by_name = get_tools_by_name(tools)

# 初始化供路由器/结构化输出使用的 LLM
llm = get_chat_model(temperature=0.0)
llm_router = llm.with_structured_output(RouterSchema) 

# 初始化 LLM，并要求智能体必须使用某个可用工具
llm = get_chat_model(temperature=0.0)
llm_with_tools = llm.bind_tools(tools, tool_choice="any")

# 节点
def llm_call(state: State):
    """由 LLM 决定是否调用工具。"""

    return {
        "messages": [
            llm_with_tools.invoke(
                [
                    {"role": "system", "content": agent_system_prompt.format(
                        tools_prompt=AGENT_TOOLS_PROMPT,
                        background=default_background,
                        response_preferences=default_response_preferences, 
                        cal_preferences=default_cal_preferences)
                    },
                    
                ]
                + state["messages"]
            )
        ]
    }

def tool_node(state: State):
    """执行工具调用。"""

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        result.append({"role": "tool", "content" : observation, "tool_call_id": tool_call["id"]})
    return {"messages": result}

# 条件边函数
def should_continue(state: State) -> Literal["Action", "__end__"]:
    """路由到 Action；如果调用 Done 工具，则结束流程。"""
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        for tool_call in last_message.tool_calls: 
            if tool_call["name"] == "Done":
                return END
            else:
                return "Action"
    return END

# 构建工作流
agent_builder = StateGraph(State)

# 添加节点
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("environment", tool_node)

# 添加边以连接节点
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    {
        # should_continue 返回的名称：下一个要访问的节点名称
        "Action": "environment",
        END: END,
    },
)
agent_builder.add_edge("environment", "llm_call")

# 编译智能体
agent = agent_builder.compile()

def triage_router(state: State) -> Command[Literal["response_agent", "__end__"]]:
    """分析邮件内容，决定是回复、通知还是忽略。

    分诊步骤可避免助手在以下邮件上浪费时间：
    - 营销邮件和垃圾邮件
    - 面向全公司的公告
    - 发给其他团队的消息
    """
    email_input = state.get("email_input")
    if email_input is None:
        messages = state.get("messages", [])
        if not messages:
            raise ValueError("Provide either email_input or a chat message.")

        content = messages[-1].content
        email_input = {
            "author": "Chat user",
            "to": "Email assistant",
            "subject": "Chat request",
            "email_thread": content if isinstance(content, str) else str(content),
        }

    author, to, subject, email_thread = parse_email(email_input)
    system_prompt = triage_system_prompt.format(
        background=default_background,
        triage_instructions=default_triage_instructions
    )

    user_prompt = triage_user_prompt.format(
        author=author, to=to, subject=subject, email_thread=email_thread
    )

    # 创建邮件 Markdown，供通知时展示在智能体收件箱中
    email_markdown = format_email_markdown(subject, author, to, email_thread)

    # 运行路由器 LLM
    result = llm_router.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )

    # 处理决策结果
    classification = result.classification

    if classification == "respond":
        print("📧 Classification: RESPOND - This email requires a response")
        goto = "response_agent"
        # 将邮件添加到消息列表
        update = {
            "classification_decision": result.classification,
            "messages": [{"role": "user",
                            "content": f"Respond to the email: {email_markdown}"
                        }],
        }
    elif result.classification == "ignore":
        print("🚫 Classification: IGNORE - This email can be safely ignored")
        update =  {
            "classification_decision": result.classification,
        }
        goto = END
    elif result.classification == "notify":
        # 在实际场景中，这里会执行其他操作
        print("🔔 Classification: NOTIFY - This email contains important information")
        update = {
            "classification_decision": result.classification,
        }
        goto = END
    else:
        raise ValueError(f"Invalid classification: {result.classification}")
    return Command(goto=goto, update=update)

# 构建工作流
overall_workflow = (
    StateGraph(State, input_schema=StateInput)
    .add_node(triage_router)
    .add_node("response_agent", agent)
    .add_edge(START, "triage_router")
)

email_assistant = overall_workflow.compile()
