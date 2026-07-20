"""LLM-driven email response helper."""
from typing import Literal

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from email_assistant.models import get_chat_model
from email_assistant.prompts import triage_system_prompt, default_background, default_triage_instructions, \
    triage_user_prompt, agent_system_prompt, default_response_preferences, default_cal_preferences
from email_assistant.schemas_002 import State, RouterSchema, StateInput
from email_assistant.tools import get_tools, get_tools_by_name
from langgraph.graph import StateGraph, START, END

from email_assistant.tools.default import AGENT_TOOLS_PROMPT
from email_assistant.utils import format_email_markdown

tools = get_tools()

llm = get_chat_model(temperature=0.0)
llm_router = llm.with_structured_output(RouterSchema)

tools_by_name = get_tools_by_name(tools)
llm_with_tools = llm.bind_tools(tools)

system_prompt = agent_system_prompt.format(
    tools_prompt=AGENT_TOOLS_PROMPT,
    background=default_background,
    response_preferences=default_response_preferences,
    cal_preferences=default_cal_preferences,
)


# lll 函数
def llm_call(state: State):
    """由 LLM 决定是否调用工具."""
    return {
        "messages": [
            llm_with_tools.invoke(
                [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"""发件人:{state["email_input"].get('from_email')},
                        收件人:{state["email_input"].get('to_email')},
                        主题:{state["email_input"].get('subject')},
                        内容:{state["email_input"].get('page_content')}"""
                    }
                ]
                + state["messages"]
            )
        ]
    }


# 条件判断函数
def should_continue(state: State) -> Literal["tool_node", "__end__"]:
    """条件判断"""
    messages = state["messages"]

    tool_calls = messages[-1].tool_calls
    if tool_calls:
        return "tool_node"
    else:
        return END


def tool_node(state: State):
    """执行工具调用"""

    messages = state["messages"]
    result = []
    if messages[-1].tool_calls:
        for tool_call in messages[-1].tool_calls:
            tool = tools_by_name[tool_call["name"]]
            observation = tool.invoke(tool_call["args"])
            tool_message = ToolMessage(tool_call_id=tool_call["id"], content=str(observation))
            result.append(tool_message)
    return {"messages": result}


# 构建图
response_agent = StateGraph(State)

response_agent.add_node("llm_call", llm_call)
response_agent.add_node("tool_node", tool_node)
response_agent.add_edge(START, "llm_call")
response_agent.add_conditional_edges(
    "llm_call",
    should_continue,
    {
        "tool_node": "tool_node",
        END: END,
    },
)
response_agent.add_edge("tool_node", "llm_call")
response_agent = response_agent.compile()


# 邮件分类
def triage_router(state: State) -> Command[Literal["response_agent", "__end__"]]:
    """邮件分类"""
    email_input = state.get("email_input")

    if email_input is None:
        messages = state.get("messages", [])
        if not messages:
            raise ValueError("请提供 email_input，或在 messages 中至少提供一条聊天消息。")
        content = messages[-1].content
        email_input = {
            "from_email": "Chat user",
            "to_email": "Email assistant",
            "subject": "Chat request",
            "page_content": content if isinstance(content, str) else str(content),
        }

    author = email_input.get("from_email", "")
    to = email_input.get("to_email", "")
    subject = email_input.get("subject", "")
    email_thread = email_input.get("page_content", "")
    system_prompt = triage_system_prompt.format(
        background=default_background,
        triage_instructions=default_triage_instructions,
    )

    user_prompt = triage_user_prompt.format(
        author=author, to=to, subject=subject, email_thread=email_thread,
    )

    email_markdown = format_email_markdown(subject, author, to, email_thread)

    result = llm_router.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )

    # 处理决策结果
    classification = result.classification

    if classification == "respond":
        print("📧 分类结果：需要回复——此邮件需要答复")
        goto = "response_agent"
        # 将邮件添加到消息列表
        update = {
            "email_input": email_input,
            "classification_decision": result.classification,
            "messages": [{"role": "user",
                          "content": f"Respond to the email: {email_markdown}"
                          }],
        }
    elif result.classification == "ignore":
        print("🚫 分类结果：忽略——此邮件可以安全忽略")
        update = {
            "email_input": email_input,
            "classification_decision": result.classification,
        }
        goto = END
    elif result.classification == "notify":
        # 在实际场景中，这里会执行其他操作
        print("🔔 分类结果：通知——此邮件包含重要信息")
        update = {
            "email_input": email_input,
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
    .add_node("response_agent", response_agent)
    .add_edge(START, "triage_router")
)

email_assistant = overall_workflow.compile()
