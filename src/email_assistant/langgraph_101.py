from typing import Literal
from langchain.tools import tool
from langgraph.graph import MessagesState, StateGraph, END, START
from email_assistant.models import get_chat_model
from dotenv import load_dotenv
load_dotenv(".env")

@tool
def write_email(to: str, subject: str, content: str) -> str:
    """撰写并发送邮件。"""
    # 占位响应：实际应用中会在这里发送邮件
    return f"Email sent to {to} with subject '{subject}' and content: {content}"

llm = get_chat_model(temperature=0)
model_with_tools = llm.bind_tools([write_email], tool_choice="any")

def call_llm(state: MessagesState) -> MessagesState:
    """调用大语言模型。"""

    output = model_with_tools.invoke(state["messages"])
    return {"messages": [output]}

def run_tool(state: MessagesState) -> MessagesState:
    """执行工具调用。"""

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        observation = write_email.invoke(tool_call["args"])
        result.append({"role": "tool", "content": observation, "tool_call_id": tool_call["id"]})
    return {"messages": result}

def should_continue(state: MessagesState) -> Literal["run_tool", "__end__"]:
    """路由到工具处理节点；没有工具调用时结束流程。"""
    
    # 获取最后一条消息
    messages = state["messages"]
    last_message = messages[-1]
    
    # 如果最后一条消息包含工具调用，则路由到工具处理节点
    if last_message.tool_calls:
        return "run_tool"
    # 否则结束流程（回复用户）
    return END

workflow = StateGraph(MessagesState)
workflow.add_node("call_llm", call_llm)
workflow.add_node("run_tool", run_tool)
workflow.add_edge(START, "call_llm")
workflow.add_conditional_edges("call_llm", should_continue, {"run_tool": "run_tool", END: END})
workflow.add_edge("run_tool", END)

app = workflow.compile()
