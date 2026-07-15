from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore
from langgraph.types import interrupt, Command

from email_assistant.tools import get_tools, get_tools_by_name
from email_assistant.models import get_chat_model
from email_assistant.tools.gmail.prompt_templates import GMAIL_TOOLS_PROMPT
from email_assistant.tools.gmail.gmail_tools import mark_as_read
from email_assistant.prompts import triage_system_prompt, triage_user_prompt, agent_system_prompt_hitl_memory, default_triage_instructions, default_background, default_response_preferences, default_cal_preferences, MEMORY_UPDATE_INSTRUCTIONS, MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT
from email_assistant.schemas import State, RouterSchema, StateInput, UserPreferences
from email_assistant.utils import parse_gmail, format_for_display, format_gmail_markdown
from dotenv import load_dotenv

load_dotenv(".env")

# 获取包含 Gmail 工具的工具列表
tools = get_tools(["send_email_tool", "schedule_meeting_tool", "check_calendar_tool", "Question", "Done"], include_gmail=True)
tools_by_name = get_tools_by_name(tools)

# 初始化用于路由和结构化输出的 LLM
llm = get_chat_model(temperature=0.0)
llm_router = llm.with_structured_output(RouterSchema) 

# 初始化 LLM，并要求智能体必须调用可用工具
llm = get_chat_model(temperature=0.0)
llm_with_tools = llm.bind_tools(tools, tool_choice="required")

def get_memory(store, namespace, default_content=None):
    """从存储中获取记忆；若不存在则使用默认值初始化。
    
    Args:
        store: LangGraph BaseStore instance to search for existing memory
        namespace: 定义记忆命名空间的元组，例如 ("email_assistant", "triage_preferences")
        default_content: 记忆不存在时使用的默认内容
        
    Returns:
        str: 现有记忆或默认值中的用户偏好内容
    """
    # 按命名空间和键查询现有记忆
    user_preferences = store.get(namespace, "user_preferences")
    
    # 若记忆存在，返回其内容（value）
    if user_preferences:
        return user_preferences.value
    
    # 若记忆不存在，写入默认内容并返回
    else:
        # 命名空间、键、值
        store.put(namespace, "user_preferences", default_content)
        user_preferences = default_content
    
    # 返回默认内容
    return user_preferences 

def update_memory(store, namespace, messages):
    """更新存储中的记忆档案。
    
    Args:
        store: LangGraph BaseStore instance to update memory
        namespace: 定义记忆命名空间的元组，例如 ("email_assistant", "triage_preferences")
        messages: 用于更新记忆的消息列表
    """

    # 获取现有记忆
    user_preferences = store.get(namespace, "user_preferences")
    # 更新记忆
    llm = get_chat_model(temperature=0.0).with_structured_output(UserPreferences)
    result = llm.invoke(
        [
            {"role": "system", "content": MEMORY_UPDATE_INSTRUCTIONS.format(current_profile=user_preferences.value, namespace=namespace)},
        ] + messages
    )
    # 将更新后的记忆写回存储
    store.put(namespace, "user_preferences", result.user_preferences)

# 节点
def triage_router(state: State, store: BaseStore) -> Command[Literal["triage_interrupt_handler", "response_agent", "__end__"]]:
    """分析邮件内容，决定应回复、通知还是忽略。

    The triage step prevents the assistant from wasting time on:
    - 营销邮件和垃圾邮件
    - 面向全公司的公告
    - 发给其他团队的消息
    """
    
    # 此图可以通过 Gmail 导入器或 Studio Chat 启动。
    # 聊天消息没有 Gmail ID，因此该路径的结束节点不会尝试将源邮件标为已读。
    email_input = state.get("email_input")
    if email_input is None:
        messages = state.get("messages", [])
        if not messages:
            raise ValueError(
                "请提供 email_input，或在 messages 中至少提供一条聊天消息。"
            )

        last_message = messages[-1]
        content = (
            last_message.content
            if hasattr(last_message, "content")
            else last_message["content"]
        )
        email_input = {
            "from": "聊天用户",
            "to": "邮件助手",
            "subject": "聊天请求",
            "body": content if isinstance(content, str) else str(content),
            "id": None,
        }
    elif not isinstance(email_input, dict):
        raise ValueError("email_input 必须是字典。")

    # 解析邮件输入
    author, to, subject, email_thread, email_id = parse_gmail(email_input)
    user_prompt = triage_user_prompt.format(
        author=author, to=to, subject=subject, email_thread=email_thread
    )

    # 为通知场景创建展示在 Agent Inbox 中的邮件 Markdown
    email_markdown = format_gmail_markdown(subject, author, to, email_thread, email_id)

    # 查询现有的 triage_preferences 记忆
    triage_instructions = get_memory(store, ("email_assistant", "triage_preferences"), default_triage_instructions)

    # 使用背景信息和分诊指令格式化系统提示词
    system_prompt = triage_system_prompt.format(
        background=default_background,
        triage_instructions=triage_instructions,
    )

    # 运行路由 LLM
    result = llm_router.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )

    # 获取决策
    classification = result.classification

    # 处理分类决策
    if classification == "respond":
        print("📧 分类结果：需要回复——这封邮件需要答复")
        # 下一个节点
        goto = "response_agent"
        # 更新状态
        update = {
            "email_input": email_input,
            "classification_decision": result.classification,
            "messages": [{"role": "user",
                            "content": f"请回复这封邮件：{email_markdown}"
                        }],
        }
        
    elif classification == "ignore":
        print("🚫 分类结果：忽略——这封邮件可以安全忽略")

        # 下一个节点
        goto = END
        # 更新状态
        update = {
            "email_input": email_input,
            "classification_decision": classification,
        }

    elif classification == "notify":
        print("🔔 分类结果：通知——这封邮件包含重要信息")

        # 下一个节点
        goto = "triage_interrupt_handler"
        # 更新状态
        update = {
            "email_input": email_input,
            "classification_decision": classification,
        }

    else:
        raise ValueError(f"无效的分类结果：{classification}")
    
    return Command(goto=goto, update=update)

def triage_interrupt_handler(state: State, store: BaseStore) -> Command[Literal["response_agent", "__end__"]]:
    """处理分诊步骤产生的中断。"""
    
    # 解析邮件输入
    author, to, subject, email_thread, email_id = parse_gmail(state["email_input"])

    # 为通知场景创建展示在 Agent Inbox 中的邮件 Markdown
    email_markdown = format_gmail_markdown(subject, author, to, email_thread, email_id)

    # 创建消息
    messages = [{"role": "user",
                "content": f"请通知用户以下邮件内容：{email_markdown}"
                }]

    # 为 Agent Inbox 创建中断
    request = {
        "action_request": {
            "action": f"邮件助手：{state['classification_decision']}",
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

    # 发送到 Agent Inbox 并等待响应
    response = interrupt([request])[0]

    # 若用户提供反馈，进入回复智能体并依据反馈回复邮件
    if response["type"] == "response":
        # 将反馈加入消息
        user_input = response["args"]
        messages.append({"role": "user",
                        "content": f"用户希望回复该邮件。请根据以下反馈进行回复：{user_input}"
                        })
        # 使用反馈更新记忆
        update_memory(store, ("email_assistant", "triage_preferences"), [{
            "role": "user",
            "content": "用户决定回复该邮件，请更新分诊偏好以记录这一决定。"
        }] + messages)

        goto = "response_agent"

    # 若用户忽略邮件，转到 END
    elif response["type"] == "ignore":
        # 记录用户忽略邮件的决定
        messages.append({"role": "user",
                        "content": "用户虽然收到通知，却决定忽略该邮件。请更新分诊偏好以记录这一决定。"
                        })
        # 使用反馈更新记忆
        update_memory(store, ("email_assistant", "triage_preferences"), messages)
        goto = END

    # 捕获其他响应
    else:
        raise ValueError(f"无效的响应：{response}")

    # 更新状态
    update = {
        "messages": messages,
    }

    return Command(goto=goto, update=update)

def llm_call(state: State, store: BaseStore):
    """由 LLM 决定是否调用工具。"""
    
    # 查询现有的 cal_preferences 记忆
    cal_preferences = get_memory(store, ("email_assistant", "cal_preferences"), default_cal_preferences)
    
    # 查询现有的 response_preferences 记忆
    response_preferences = get_memory(store, ("email_assistant", "response_preferences"), default_response_preferences)

    return {
        "messages": [
            llm_with_tools.invoke(
                [
                    {"role": "system", "content": agent_system_prompt_hitl_memory.format(
                        tools_prompt=GMAIL_TOOLS_PROMPT,
                        background=default_background,
                        response_preferences=response_preferences, 
                        cal_preferences=cal_preferences
                    )}
                ]
                + state["messages"]
            )
        ]
    }
    
def interrupt_handler(state: State, store: BaseStore) -> Command[Literal["llm_call", "__end__"]]:
    """为工具调用创建供人工审核的中断。"""
    
    # 存放消息
    result = []

    # 接下来进入 LLM 调用节点
    goto = "llm_call"

    # 遍历最后一条消息中的工具调用
    for tool_call in state["messages"][-1].tool_calls:
        
        # 需要人工介入审核的工具
        hitl_tools = ["send_email_tool", "schedule_meeting_tool", "Question"]
        
        # 如果工具不在人工审核列表中，直接执行，无需中断
        if tool_call["name"] not in hitl_tools:

            # 直接执行 search_memory 和其他无需审核的工具
            tool = tools_by_name[tool_call["name"]]
            observation = tool.invoke(tool_call["args"])
            result.append({"role": "tool", "content": observation, "tool_call_id": tool_call["id"]})
            continue
            
        # 从状态中的 email_input 获取原始邮件
        email_input = state["email_input"]
        author, to, subject, email_thread, email_id = parse_gmail(email_input)
        original_email_markdown = format_gmail_markdown(subject, author, to, email_thread, email_id)
        
        # 格式化待展示的工具调用，并在前面附上原始邮件
        tool_display = format_for_display(tool_call)
        description = original_email_markdown + tool_display

        # 配置 Agent Inbox 中允许的操作
        if tool_call["name"] == "send_email_tool":
            config = {
                "allow_ignore": True,
                "allow_respond": True,
                "allow_edit": True,
                "allow_accept": True,
            }
        elif tool_call["name"] == "schedule_meeting_tool":
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
            raise ValueError(f"无效的工具调用：{tool_call['name']}")

        # 创建中断请求
        request = {
            "action_request": {
                "action": tool_call["name"],
                "args": tool_call["args"]
            },
            "config": config,
            "description": description,
        }

        # 发送到 Agent Inbox 并等待响应
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
            initial_tool_call = tool_call["args"]
            
            # 从 Agent Inbox 获取编辑后的参数
            edited_args = response["args"]["args"]

            # 用编辑后的内容更新 AI 消息中的工具调用（引用状态中的消息）
            ai_message = state["messages"][-1] # 获取状态中最新的消息
            current_id = tool_call["id"] # 保存正在编辑的工具调用 ID
            
            # 过滤掉被编辑的调用并添加更新后的版本，生成新的工具调用列表
            # 这样可避免直接修改原列表（保持不可变性）
            updated_tool_calls = [tc for tc in ai_message.tool_calls if tc["id"] != current_id] + [
                {"type": "tool_call", "name": tool_call["name"], "args": edited_args, "id": current_id}
            ]

            # 创建带更新后工具调用的消息副本，而非修改原消息
            # 这可保证状态不可变，并避免影响代码的其他部分
            result.append(ai_message.model_copy(update={"tool_calls": updated_tool_calls}))

            # 将反馈保存到记忆，并用 Agent Inbox 编辑后的内容更新 write_email 工具调用
            if tool_call["name"] == "send_email_tool":
                
                # 使用编辑后的参数执行工具
                observation = tool.invoke(edited_args)
                
                # 仅添加工具响应消息
                result.append({"role": "tool", "content": observation, "tool_call_id": current_id})

                # 更新记忆
                update_memory(store, ("email_assistant", "response_preferences"), [{
                    "role": "user",
                    "content": f"用户编辑了邮件回复。以下是助手最初生成的邮件：{initial_tool_call}。以下是用户编辑后的邮件：{edited_args}。请遵循以上所有指令，并牢记：{MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}。"
                }])
            
            # 将反馈保存到记忆，并用 Agent Inbox 编辑后的内容更新 schedule_meeting 工具调用
            elif tool_call["name"] == "schedule_meeting_tool":
                
                # 使用编辑后的参数执行工具
                observation = tool.invoke(edited_args)
                
                # 仅添加工具响应消息
                result.append({"role": "tool", "content": observation, "tool_call_id": current_id})

                # 更新记忆
                update_memory(store, ("email_assistant", "cal_preferences"), [{
                    "role": "user",
                    "content": f"用户编辑了日历邀请。以下是助手最初生成的邀请：{initial_tool_call}。以下是用户编辑后的邀请：{edited_args}。请遵循以上所有指令，并牢记：{MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}。"
                }])
            
            # 捕获其他工具调用
            else:
                raise ValueError(f"无效的工具调用：{tool_call['name']}")

        elif response["type"] == "ignore":

            if tool_call["name"] == "send_email_tool":
                # 不执行工具，并告知智能体后续处理方式
                result.append({"role": "tool", "content": "用户忽略了这份邮件草稿。请忽略该邮件并结束工作流。", "tool_call_id": tool_call["id"]})
                # 转到 END
                goto = END
                # 更新记忆
                update_memory(store, ("email_assistant", "triage_preferences"), state["messages"] + result + [{
                    "role": "user",
                    "content": f"用户忽略了邮件草稿，表示他们不希望回复该邮件。请更新分诊偏好，确保此类邮件不会被归类为需要回复。请遵循以上所有指令，并牢记：{MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}。"
                }])

            elif tool_call["name"] == "schedule_meeting_tool":
                # 不执行工具，并告知智能体后续处理方式
                result.append({"role": "tool", "content": "用户忽略了这份日历会议草稿。请忽略该邮件并结束工作流。", "tool_call_id": tool_call["id"]})
                # 转到 END
                goto = END
                # 更新记忆
                update_memory(store, ("email_assistant", "triage_preferences"), state["messages"] + result + [{
                    "role": "user",
                    "content": f"用户忽略了日历会议草稿，表示他们不希望为该邮件安排会议。请更新分诊偏好，确保此类邮件不会被归类为需要回复。请遵循以上所有指令，并牢记：{MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}。"
                }])

            elif tool_call["name"] == "Question":
                # 不执行工具，并告知智能体后续处理方式
                result.append({"role": "tool", "content": "用户忽略了这个问题。请忽略该邮件并结束工作流。", "tool_call_id": tool_call["id"]})
                # 转到 END
                goto = END
                # 更新记忆
                update_memory(store, ("email_assistant", "triage_preferences"), state["messages"] + result + [{
                    "role": "user",
                    "content": f"用户忽略了该问题，表示他们不想回答问题或处理该邮件。请更新分诊偏好，确保此类邮件不会被归类为需要回复。请遵循以上所有指令，并牢记：{MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}。"
                }])

            else:
                raise ValueError(f"无效的工具调用：{tool_call['name']}")

        elif response["type"] == "response":
            # 用户提供了反馈
            user_feedback = response["args"]
            if tool_call["name"] == "send_email_tool":
                # 不执行工具，添加用户反馈消息以便纳入邮件内容
                result.append({"role": "tool", "content": f"用户提供了可纳入邮件的反馈。反馈：{user_feedback}", "tool_call_id": tool_call["id"]})
                # 更新记忆
                update_memory(store, ("email_assistant", "response_preferences"), state["messages"] + result + [{
                    "role": "user",
                    "content": f"用户提供了反馈，可用于更新回复偏好。请遵循以上所有指令，并牢记：{MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}。"
                }])

            elif tool_call["name"] == "schedule_meeting_tool":
                # 不执行工具，添加用户反馈消息以便纳入会议请求
                result.append({"role": "tool", "content": f"用户提供了可纳入会议请求的反馈。反馈：{user_feedback}", "tool_call_id": tool_call["id"]})
                # 更新记忆
                update_memory(store, ("email_assistant", "cal_preferences"), state["messages"] + result + [{
                    "role": "user",
                    "content": f"用户提供了反馈，可用于更新日历偏好。请遵循以上所有指令，并牢记：{MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}。"
                }])

            elif tool_call["name"] == "Question":
                # 不执行工具，添加用户回答以供后续操作使用
                result.append({"role": "tool", "content": f"用户回答了问题，可用于后续操作。反馈：{user_feedback}", "tool_call_id": tool_call["id"]})

            else:
                raise ValueError(f"无效的工具调用：{tool_call['name']}")

    # 更新状态
    update = {
        "messages": result,
    }

    return Command(goto=goto, update=update)

# 条件边函数
def should_continue(state: State, store: BaseStore) -> Literal["interrupt_handler", "mark_as_read_node"]:
    """路由至工具处理器；若调用 Done 工具则结束。"""
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        for tool_call in last_message.tool_calls: 
            if tool_call["name"] == "Done":
                # TODO：这里可以用邮件回复更新背景记忆，以支持后续操作。
                return "mark_as_read_node"
            else:
                return "interrupt_handler"

def mark_as_read_node(state: State):
    email_input = state["email_input"]
    author, to, subject, email_thread, email_id = parse_gmail(email_input)
    if email_id:
        mark_as_read(email_id)

# 构建工作流
agent_builder = StateGraph(State)

# 添加节点（带 store 参数）
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("interrupt_handler", interrupt_handler)
agent_builder.add_node("mark_as_read_node", mark_as_read_node)

# 添加边
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    {
        "interrupt_handler": "interrupt_handler",
        "mark_as_read_node": "mark_as_read_node",
    },
)
agent_builder.add_edge("mark_as_read_node", END)

# 编译智能体
response_agent = agent_builder.compile()

# 使用存储和检查点器构建整体工作流
overall_workflow = (
    StateGraph(State, input=StateInput)
    .add_node(triage_router)
    .add_node(triage_interrupt_handler)
    .add_node("response_agent", response_agent)
    .add_node("mark_as_read_node", mark_as_read_node)
    .add_edge(START, "triage_router")
    .add_edge("mark_as_read_node", END)
)

email_assistant = overall_workflow.compile()
