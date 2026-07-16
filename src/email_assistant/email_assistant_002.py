"""LLM-driven email response helper."""
from typing import Literal

from email_assistant.models import get_chat_model
from email_assistant.schemas_002 import State
from email_assistant.tools import get_tools
from langgraph.graph import StateGraph, START, END
tools = get_tools()

llm = get_chat_model(temperature=0.0)

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
