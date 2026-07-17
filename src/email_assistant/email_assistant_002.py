"""LLM-driven email response helper."""
from typing import Literal

from langchain_core.messages import ToolMessage

from email_assistant.models import get_chat_model
from email_assistant.schemas_002 import State
from email_assistant.tools import get_tools, get_tools_by_name
from langgraph.graph import StateGraph, START, END
tools = get_tools()

llm = get_chat_model(temperature=0.0)
tools_by_name = get_tools_by_name(tools)
llm_with_tools = llm.bind_tools(tools)


# lll 函数
def llm_call(state: State):
    """由 LLM 决定是否调用工具."""
    return {
        "messages": [
            llm_with_tools.invoke(
                [
                    {"role": "system", "content": "这是提示词"},
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
def should_continue(state: State)-> Literal["tool_node", "__end__"]:
    """条件判断"""
    messages = state["messages"]

    tool_calls = messages[-1].tool_calls
    if tool_calls:
        return "tool_node"
    else:
        return END


def tool_node(state:State):
    """执行工具调用"""

    messages  = state["messages"]
    result =[]
    if messages[-1].tool_calls:
        for tool_call in messages[-1].tool_calls:
            tool =tools_by_name[tool_call["name"]]
            observation = tool.invoke(tool_call["args"])
            tool_message= ToolMessage(tool_call_id=tool_call["id"], content=str(observation))
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


def triage_router(state: State):
    """邮件分类"""
    email_input =  state.get("email_input")

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
        update = {
            "email_input": email_input,
        }
        goto = "response_agent"





