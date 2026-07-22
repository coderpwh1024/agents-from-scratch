from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

from email_assistant.tools import get_tools, get_tools_by_name
from email_assistant.models import get_chat_model
from email_assistant.tools.default.prompt_templates import HITL_TOOLS_PROMPT
from email_assistant.prompts import triage_system_prompt, triage_user_prompt, agent_system_prompt_hitl, default_background, default_triage_instructions, default_response_preferences, default_cal_preferences
from email_assistant.schemas import State, RouterSchema, StateInput
from email_assistant.utils import parse_email, format_for_display, format_email_markdown
from dotenv import load_dotenv

load_dotenv(".env")

# 获取工具
tools = get_tools(["write_email", "schedule_meeting", "check_calendar_availability", "Question", "Done"])
tools_by_name = get_tools_by_name(tools)

# 初始化供路由器/结构化输出使用的 LLM
llm = get_chat_model(temperature=0.0)
llm_router = llm.with_structured_output(RouterSchema) 

# 初始化 LLM，并强制智能体使用工具（任一可用工具）
llm = get_chat_model(temperature=0.0)
llm_with_tools = llm.bind_tools(tools, tool_choice="required")

# 节点
def triage_router(state: State) -> Command[Literal["triage_interrupt_handler", "response_agent", "__end__"]]:
    """分析邮件内容，决定应回复、通知还是忽略。

    分诊步骤可避免助手将时间浪费在以下内容上：
    - 营销邮件和垃圾邮件
    - 全公司公告
    - 发给其他团队的消息
    """

    # 图入口既可接收结构化邮件，也可接收聊天消息。
    # 将标准化后的邮件持久化到状态中，供后续 HITL 节点
    # 向审核人员展示原始消息。
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

    # 解析邮件输入
    author, to, subject, email_thread = parse_email(email_input)
    user_prompt = triage_user_prompt.format(
        author=author, to=to, subject=subject, email_thread=email_thread
    )

    # 创建供通知场景下 Agent Inbox 使用的邮件 Markdown
    email_markdown = format_email_markdown(subject, author, to, email_thread)

    # 使用背景信息和分诊指令格式化系统提示词
    system_prompt = triage_system_prompt.format(
        background=default_background,
        triage_instructions=default_triage_instructions
    )

    # 运行路由 LLM
    result = llm_router.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )

    # 决策结果
    classification = result.classification

    # 处理分类决策
    if classification == "respond":
        print("📧 Classification: RESPOND - This email requires a response")
        # 下一个节点
        goto = "response_agent"
        # 更新状态
        update = {
            "email_input": email_input,
            "classification_decision": result.classification,
            "messages": [{"role": "user",
                            "content": f"Respond to the email: {email_markdown}"
                        }],
        }
    elif classification == "ignore":
        print("🚫 Classification: IGNORE - This email can be safely ignored")

        # 下一个节点
        goto = END
        # 更新状态
        update = {
            "email_input": email_input,
            "classification_decision": classification,
        }

    elif classification == "notify":
        print("🔔 Classification: NOTIFY - This email contains important information") 

        # 下一个节点
        goto = "triage_interrupt_handler"
        # 更新状态
        update = {
            "email_input": email_input,
            "classification_decision": classification,
        }

    else:
        raise ValueError(f"Invalid classification: {classification}")
    return Command(goto=goto, update=update)

def triage_interrupt_handler(state: State) -> Command[Literal["response_agent", "__end__"]]:
    """处理分诊步骤发出的中断。"""
    
    # 解析邮件输入
    author, to, subject, email_thread = parse_email(state["email_input"])

    # 创建供通知场景下 Agent Inbox 使用的邮件 Markdown
    email_markdown = format_email_markdown(subject, author, to, email_thread)

    # 创建消息
    messages = [{"role": "user",
                "content": f"Email to notify user about: {email_markdown}"
                }]

    # 为 Agent Inbox 创建中断
    request = {
        "action_request": {
            "action": f"Email Assistant: {state['classification_decision']}",
            "args": {}
        },
        "config": {
            "allow_ignore": True,  
            "allow_respond": True, 
            "allow_edit": False, 
            "allow_accept": False,  
        },
        # 在 Agent Inbox 中展示的邮件
        "description": email_markdown,
    }

    # Agent Inbox 以列表形式返回响应
    response = interrupt([request])[0]

    # 若用户提供反馈，则转至回复智能体，并利用反馈回复邮件
    if response["type"] == "response":
        # 将反馈添加到消息中
        user_input = response["args"]
        # 供回复智能体使用
        messages.append({"role": "user",
                        "content": f"User wants to reply to the email. Use this feedback to respond: {user_input}"
                        })
        # 转至回复智能体
        goto = "response_agent"

    # 若用户忽略邮件，则转至 END
    elif response["type"] == "ignore":
        goto = END

    # 捕获所有其他响应
    else:
        raise ValueError(f"Invalid response: {response}")

    # 更新状态
    update = {
        "messages": messages,
    }

    return Command(goto=goto, update=update)

def llm_call(state: State):
    """由 LLM 决定是否调用工具。"""

    return {
        "messages": [
            llm_with_tools.invoke(
                [
                    {"role": "system", "content": agent_system_prompt_hitl.format(
                        tools_prompt=HITL_TOOLS_PROMPT,
                        background=default_background,
                        response_preferences=default_response_preferences, 
                        cal_preferences=default_cal_preferences
                    )}
                ]
                + state["messages"]
            )
        ]
    }

def interrupt_handler(state: State) -> Command[Literal["llm_call", "__end__"]]:
    """为人工审核工具调用创建中断。"""
    
    # 存储消息
    result = []

    # 接下来转至 LLM 调用节点
    goto = "llm_call"

    # 遍历最后一条消息中的工具调用
    for tool_call in state["messages"][-1].tool_calls:
        
        # HITL 允许的工具
        hitl_tools = ["write_email", "schedule_meeting", "Question"]
        
        # 如果工具不在 HITL 列表中，则直接执行，无需中断
        if tool_call["name"] not in hitl_tools:

            # 直接执行 search_memory 和其他工具，无需中断
            tool = tools_by_name[tool_call["name"]]



            observation = tool.invoke(tool_call["args"])
            result.append({"role": "tool", "content": observation, "tool_call_id": tool_call["id"]})
            continue
            
        # 从状态中的 email_input 获取原始邮件
        email_input = state["email_input"]
        author, to, subject, email_thread = parse_email(email_input)
        original_email_markdown = format_email_markdown(subject, author, to, email_thread)
        
        # 格式化工具调用以供展示，并在前面附加原始邮件
        tool_display = format_for_display(tool_call)
        description = original_email_markdown + tool_display

        # 配置 Agent Inbox 中允许的操作
        if tool_call["name"] == "write_email":
            config = {
                "allow_ignore": True,
                "allow_respond": True,
                "allow_edit": True,
                "allow_accept": True,
            }
        elif tool_call["name"] == "schedule_meeting":
            config = {
                "allow_ignore": True,
                "allow_respond": True,
                "allow_edit": True,
                "allow_accept": True,
            }
        elif tool_call["name"] == "Question":
            config = {
                "allow_ignore": True,
                "allow_respond": True,
                "allow_edit": False,
                "allow_accept": False,
            }
        else:
            raise ValueError(f"Invalid tool call: {tool_call['name']}")

        # 创建中断请求
        request = {
            "action_request": {
                "action": tool_call["name"],
                "args": tool_call["args"]
            },
            "config": config,
            "description": description,
        }

        # 发送至 Agent Inbox 并等待响应
        response = interrupt([request])[0]

        # 处理响应
        if response["type"] == "accept":

            # 使用原始参数执行工具
            tool = tools_by_name[tool_call["name"]]
            observation = tool.invoke(tool_call["args"])
            result.append({"role": "tool", "content": observation, "tool_call_id": tool_call["id"]})
                        
        elif response["type"] == "edit":

            # 选择工具
            tool = tools_by_name[tool_call["name"]]
            
            # 从 Agent Inbox 获取编辑后的参数
            edited_args = response["args"]["args"]

            # 使用编辑后的内容更新 AI 消息的工具调用（引用状态中的消息）
            ai_message = state["messages"][-1] # 获取状态中最新的消息
            current_id = tool_call["id"] # 保存正在编辑的工具调用 ID
            
            # 通过过滤出正在编辑的调用并添加更新版本，创建新的工具调用列表
            # 这可避免直接修改原始列表（不可变方式）
            updated_tool_calls = [tc for tc in ai_message.tool_calls if tc["id"] != current_id] + [
                {"type": "tool_call", "name": tool_call["name"], "args": edited_args, "id": current_id}
            ]

            # 创建包含更新后工具调用的消息副本，而非修改原始消息
            # 这可确保状态不可变，并防止影响代码其他部分
            result.append(ai_message.model_copy(update={"tool_calls": updated_tool_calls}))

            # 使用 Agent Inbox 中编辑后的内容更新 write_email 工具调用
            if tool_call["name"] == "write_email":
                
                # 使用编辑后的参数执行工具
                observation = tool.invoke(edited_args)
                
                # 仅添加工具响应消息
                result.append({"role": "tool", "content": observation, "tool_call_id": current_id})
            
            # 使用 Agent Inbox 中编辑后的内容更新 schedule_meeting 工具调用
            elif tool_call["name"] == "schedule_meeting":
                
                
                # 使用编辑后的参数执行工具
                observation = tool.invoke(edited_args)
                
                # 仅添加工具响应消息
                result.append({"role": "tool", "content": observation, "tool_call_id": current_id})
            
            # 捕获所有其他工具调用
            else:
                raise ValueError(f"Invalid tool call: {tool_call['name']}")

        elif response["type"] == "ignore":
            if tool_call["name"] == "write_email":
                # 不执行工具，并告知智能体后续处理方式
                result.append({"role": "tool", "content": "User ignored this email draft. Ignore this email and end the workflow.", "tool_call_id": tool_call["id"]})
                # 转至 END
                goto = END
            elif tool_call["name"] == "schedule_meeting":
                # 不执行工具，并告知智能体后续处理方式
                result.append({"role": "tool", "content": "User ignored this calendar meeting draft. Ignore this email and end the workflow.", "tool_call_id": tool_call["id"]})
                # 转至 END
                goto = END
            elif tool_call["name"] == "Question":
                # 不执行工具，并告知智能体后续处理方式
                result.append({"role": "tool", "content": "User ignored this question. Ignore this email and end the workflow.", "tool_call_id": tool_call["id"]})
                # 转至 END
                goto = END
            else:
                raise ValueError(f"Invalid tool call: {tool_call['name']}")
            
        elif response["type"] == "response":
            # 用户提供了反馈
            user_feedback = response["args"]
            if tool_call["name"] == "write_email":
                # 不执行工具，添加包含用户反馈的消息以纳入邮件
                result.append({"role": "tool", "content": f"User gave feedback, which can we incorporate into the email. Feedback: {user_feedback}", "tool_call_id": tool_call["id"]})
            elif tool_call["name"] == "schedule_meeting":
                # 不执行工具，添加包含用户反馈的消息以纳入邮件
                result.append({"role": "tool", "content": f"User gave feedback, which can we incorporate into the meeting request. Feedback: {user_feedback}", "tool_call_id": tool_call["id"]})
            elif tool_call["name"] == "Question":
                # 不执行工具，添加包含用户反馈的消息以纳入邮件
                result.append({"role": "tool", "content": f"User answered the question, which can we can use for any follow up actions. Feedback: {user_feedback}", "tool_call_id": tool_call["id"]})
            else:
                raise ValueError(f"Invalid tool call: {tool_call['name']}")

        # 捕获所有其他响应
        else:
            raise ValueError(f"Invalid response: {response}")
            
    # 更新状态
    update = {
        "messages": result,
    }

    return Command(goto=goto, update=update)

# 条件边函数
def should_continue(state: State) -> Literal["interrupt_handler", "__end__"]:
    """路由到工具处理器；若调用 Done 工具则结束。"""
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            if tool_call["name"] == "Done":
                return END
            else:
                return "interrupt_handler"

# 构建工作流
agent_builder = StateGraph(State)

# 添加节点
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("interrupt_handler", interrupt_handler)

# 添加边
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    {
        "interrupt_handler": "interrupt_handler",
        END: END,
    },
)

# 编译智能体
response_agent = agent_builder.compile()

# 构建整体工作流
overall_workflow = (
    StateGraph(State, input=StateInput)
    .add_node(triage_router)
    .add_node(triage_interrupt_handler)
    .add_node("response_agent", response_agent)
    .add_edge(START, "triage_router")
    
)

email_assistant = overall_workflow.compile()
