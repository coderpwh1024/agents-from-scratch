from typing import List, Any
import json
import html2text

def format_email_markdown(subject, author, to, email_thread, email_id=None):
    """将邮件详情格式化为便于展示的 Markdown 字符串。
    
    Args:
        subject: 邮件主题
        author: 邮件发件人
        to: 邮件收件人
        email_thread: 邮件内容
        email_id: 可选的邮件 ID（供 Gmail API 使用）
    """
    id_section = f"\n**ID**: {email_id}" if email_id else ""
    
    return f"""

**主题**: {subject}
**发件人**: {author}
**收件人**: {to}{id_section}

{email_thread}

---
"""

def format_gmail_markdown(subject, author, to, email_thread, email_id=None):
    """将 Gmail 邮件详情格式化为便于展示的 Markdown 字符串，
    并将 HTML 内容转换为文本。
    
    Args:
        subject: 邮件主题
        author: 邮件发件人
        to: 邮件收件人
        email_thread: 邮件内容（可能为 HTML）
        email_id: 可选的邮件 ID（供 Gmail API 使用）
    """
    id_section = f"\n**ID**: {email_id}" if email_id else ""
    
    # 检查 email_thread 是否为 HTML 内容，并在需要时转换为文本
    if email_thread and (email_thread.strip().startswith("<!DOCTYPE") or 
                          email_thread.strip().startswith("<html") or
                          "<body" in email_thread):
        # 将 HTML 转换为 Markdown 文本
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0  # 不换行
        email_thread = h.handle(email_thread)
    
    return f"""

**主题**: {subject}
**发件人**: {author}
**收件人**: {to}{id_section}

{email_thread}

---
"""

def format_for_display(tool_call):
    """格式化将在智能体收件箱中展示的内容。
    
    Args:
        tool_call: 要格式化的工具调用
    """
    # 初始化空展示内容
    display = ""
    
    # 添加工具调用信息
    if tool_call["name"] == "write_email":
        display += f"""# 邮件草稿

**收件人**: {tool_call["args"].get("to")}
**主题**: {tool_call["args"].get("subject")}

{tool_call["args"].get("content")}
"""
    elif tool_call["name"] == "schedule_meeting":
        display += f"""# 日历邀请

**会议**: {tool_call["args"].get("subject")}
**参会者**: {', '.join(tool_call["args"].get("attendees"))}
**时长**: {tool_call["args"].get("duration_minutes")} 分钟
**日期**: {tool_call["args"].get("preferred_day")}
"""
    elif tool_call["name"] == "Question":
        # 对问题使用特殊格式，使其更清晰
        display += f"""# 给用户的问题

{tool_call["args"].get("content")}
"""
    else:
        # 其他工具使用通用格式
        display += f"""# 工具调用：{tool_call["name"]}

参数："""
        
        # 检查 args 是字典还是字符串
        if isinstance(tool_call["args"], dict):
            display += f"\n{json.dumps(tool_call['args'], indent=2)}\n"
        else:
            display += f"\n{tool_call['args']}\n"
    return display

def parse_email(email_input: dict) -> dict:
    """解析邮件输入字典。

    Args:
        email_input (dict): 包含邮件字段的字典：
            - author: 发件人的姓名和邮箱
            - to: 收件人的姓名和邮箱
            - subject: 邮件主题行
            - email_thread: 完整邮件内容

    Returns:
        tuple[str, str, str, str]: 包含以下内容的元组：
            - author: 发件人的姓名和邮箱
            - to: 收件人的姓名和邮箱
            - subject: 邮件主题行
            - email_thread: 完整邮件内容
    """
    return (
        email_input["author"],
        email_input["to"],
        email_input["subject"],
        email_input["email_thread"],
    )

def parse_gmail(email_input: dict) -> tuple[str, str, str, str, str | None]:
    """解析 Gmail 的邮件输入字典，包括邮件 ID。
    
    此函数扩展了 parse_email，额外返回用于 Gmail 集成的邮件 ID。

    Args:
        email_input (dict): 包含以下格式邮件字段的字典：
            Gmail 架构：
                - From: 发件人邮箱
                - To: 收件人邮箱
                - Subject: 邮件主题行
                - Body: 完整邮件内容
                - Id: Gmail 消息 ID
            
    Returns:
        tuple[str, str, str, str, str]: 包含以下内容的元组：
            - author: 发件人的姓名和邮箱
            - to: 收件人的姓名和邮箱
            - subject: 邮件主题行
            - email_thread: 完整邮件内容
            - email_id: 邮件 ID（Studio Chat 请求时为 None）
    """

    required_fields = ("from", "to", "subject", "body")
    missing_fields = [field for field in required_fields if field not in email_input]
    if missing_fields:
        raise ValueError(
            "无效的 Gmail email_input；缺少必填字段："
            + ", ".join(missing_fields)
        )

    # Gmail 架构
    return (
        email_input["from"],
        email_input["to"],
        email_input["subject"],
        email_input["body"],
        email_input.get("id"),
    )
    
def extract_message_content(message) -> str:
    """从不同消息类型中提取内容，并返回干净的字符串。
    
    Args:
        message: 消息对象（HumanMessage、AIMessage、ToolMessage）
        
    Returns:
        str: 提取出的干净字符串内容
    """
    content = message.content
    
    # 检查字符串中的递归标记
    if isinstance(content, str) and '<Recursion on AIMessage with id=' in content:
        return "[递归内容]"
    
    # 处理字符串内容
    if isinstance(content, str):
        return content
        
    # 处理列表内容（AIMessage 格式）
    elif isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and 'text' in item:
                text_parts.append(item['text'])
        return "\n".join(text_parts)
    
    # 不尝试处理递归，以避免无限循环
    # 改为直接返回字符串表示
    return str(content)

def format_few_shot_examples(examples):
    """将示例格式化为易读的字符串表示。

    Args:
        examples (List[Item]): 来自向量存储的示例项列表，每个示例项都包含以下格式的值字符串：
            'Email: {...} Original routing: {...} Correct routing: {...}'

    Returns:
        str: 包含所有示例的格式化字符串，每个示例的格式如下：
            示例：
            邮件：{email_details}
            原始分类：{original_routing}
            正确分类：{correct_routing}
            ---
    """
    formatted = []
    for example in examples:
        # 将示例值字符串解析为多个组成部分
        email_part = example.value.split('Original routing:')[0].strip()
        original_routing = example.value.split('Original routing:')[1].split('Correct routing:')[0].strip()
        correct_routing = example.value.split('Correct routing:')[1].strip()
        
        # 格式化为干净的字符串
        formatted_example = f"""示例：
邮件：{email_part}
原始分类：{original_routing}
正确分类：{correct_routing}
---"""
        formatted.append(formatted_example)
    
    return "\n".join(formatted)

def extract_tool_calls(messages: List[Any]) -> List[str]:
    """从消息中提取工具调用名称，并安全处理没有 tool_calls 的消息。"""
    tool_call_names = []
    for message in messages:
        # 检查消息是否为包含 tool_calls 的字典
        if isinstance(message, dict) and message.get("tool_calls"):
            tool_call_names.extend([call["name"].lower() for call in message["tool_calls"]])
        # 检查消息是否为具有 tool_calls 属性的对象
        elif hasattr(message, "tool_calls") and message.tool_calls:
            tool_call_names.extend([call["name"].lower() for call in message.tool_calls])
    
    return tool_call_names

def format_messages_string(messages: List[Any]) -> str:
    """将消息格式化为一个字符串，供分析使用。"""
    return '\n'.join(message.pretty_repr() for message in messages)

def show_graph(graph, xray=False):
    """显示 LangGraph Mermaid 图，并提供备用渲染方式。
    
    当 mermaid.ink 超时时，回退到 pyppeteer。
    
    Args:
        graph: 具有 get_graph() 方法的 LangGraph 对象
    """
    from IPython.display import Image
    try:
        # 先尝试默认渲染器
        return Image(graph.get_graph(xray=xray).draw_mermaid_png())
    except Exception as e:
        # 默认渲染器失败时回退到 pyppeteer
        import nest_asyncio
        nest_asyncio.apply()
        from langchain_core.runnables.graph import MermaidDrawMethod
        return Image(graph.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.PYPPETEER))
