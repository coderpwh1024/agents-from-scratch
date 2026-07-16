"""LLM-driven email response helper."""

from email_assistant.models import get_chat_model
from email_assistant.schemas_002 import State
from email_assistant.tools import get_tools

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
