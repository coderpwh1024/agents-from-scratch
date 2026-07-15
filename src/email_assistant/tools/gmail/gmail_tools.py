"""
Gmail 工具实现模块。
此模块将 Gmail API 函数封装为 LangChain 工具。
"""

import os
import sys
import base64
import email.utils
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Iterator
from pathlib import Path
from pydantic import Field, BaseModel
from langchain_core.tools import tool

# 配置基础日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定义凭据和令牌文件路径
_ROOT = Path(__file__).parent.absolute()
_SECRETS_DIR = _ROOT / ".secrets"

# 尝试导入 Gmail API 库
# 如果不可用，则使用模拟实现
try:
    import logging
    from googleapiclient.discovery import build
    from email.mime.text import MIMEText
    from datetime import timedelta
    from dateutil.parser import parse as parse_time
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # 邮件内容提取函数
    def extract_message_part(payload):
        """从邮件片段中提取内容。"""
        if payload.get("body", {}).get("data"):
            # 处理 Base64 编码的内容
            data = payload["body"]["data"]
            decoded = base64.urlsafe_b64decode(data).decode("utf-8")
            return decoded
            
        # 处理多部分邮件
        if payload.get("parts"):
            text_parts = []
            for part in payload["parts"]:
                # 递归处理各个部分
                content = extract_message_part(part)
                if content:
                    text_parts.append(content)
            return "\n".join(text_parts)
            
        return ""
    
    # 从 token.json 或环境变量获取凭据的函数
    def get_credentials(gmail_token=None, gmail_secret=None):
        """
        从 token.json 或环境变量获取 Gmail API 凭据。
        
        此函数会按以下顺序尝试从多个来源加载凭据：
        1. 直接传入的 gmail_token 和 gmail_secret 参数
        2. 环境变量 GMAIL_TOKEN 和 GMAIL_SECRET
        3. 本地文件 token_path（.secrets/token.json）和 secrets_path（.secrets/secrets.json）
        
        参数：
            gmail_token: 可选，包含令牌数据的 JSON 字符串
            gmail_secret: 可选，包含凭据的 JSON 字符串
            
        返回：
            Google OAuth2 Credentials 对象；无法加载凭据时返回 None
        """
        token_path = _SECRETS_DIR / "token.json"
        token_data = None
        
        # 尝试从不同来源获取令牌数据
        if gmail_token:
            # 1. 如有直接传入的令牌参数，则使用它
            try:
                token_data = json.loads(gmail_token) if isinstance(gmail_token, str) else gmail_token
                logger.info("正在使用直接传入的 gmail_token 参数")
            except Exception as e:
                logger.warning(f"无法解析传入的 gmail_token：{str(e)}")
                
        if token_data is None:
            # 2. 尝试环境变量
            env_token = os.getenv("GMAIL_TOKEN")
            if env_token:
                try:
                    token_data = json.loads(env_token)
                    logger.info("正在使用 GMAIL_TOKEN 环境变量")
                except Exception as e:
                    logger.warning(f"无法解析 GMAIL_TOKEN 环境变量：{str(e)}")
        
        if token_data is None:
            # 3. 尝试本地文件
            if os.path.exists(token_path):
                try:
                    with open(token_path, "r") as f:
                        token_data = json.load(f)
                    logger.info(f"正在使用 {token_path} 中的令牌")
                except Exception as e:
                    logger.warning(f"无法从 {token_path} 加载令牌：{str(e)}")
        
        # 如果无法从任何来源获得令牌数据，则返回 None
        if token_data is None:
            logger.error("未在任何位置找到有效的令牌数据")
            return None
        
        try:
            from google.oauth2.credentials import Credentials
            
            # 以指定格式创建凭据对象
            credentials = Credentials(
                token=token_data.get("token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes", ["https://www.googleapis.com/auth/gmail.modify"])
            )
            
            # 添加 authorize 方法，以兼容旧代码
            credentials.authorize = lambda request: request
            
            return credentials
        except Exception as e:
            logger.error(f"创建凭据对象时出错：{str(e)}")
            return None
    
    # 用于提升可读性的类型别名
    EmailData = Dict[str, Any]
    
    GMAIL_API_AVAILABLE = True
    
except ImportError:
    # Gmail API 库不可用时，设置使用模拟实现的标记
    GMAIL_API_AVAILABLE = False
    logger = logging.getLogger(__name__)

# 可供工具调用及其他模块导入的辅助函数
def fetch_group_emails(
    email_address: str,
    minutes_since: int = 30,
    gmail_token: Optional[str] = None,
    gmail_secret: Optional[str] = None,
    include_read: bool = False,
    skip_filters: bool = False,
) -> Iterator[Dict[str, Any]]:
    """
    获取与指定邮箱地址相关的近期 Gmail 邮件。
    
    此函数获取指定地址作为发件人或收件人的邮件，完成处理后以适合邮件助手使用的格式返回。
    
    参数：
        email_address: 要获取邮件的邮箱地址
        minutes_since: 仅获取在指定分钟数内收到的邮件
        gmail_token: 可选，用于 Gmail API 身份验证的令牌
        gmail_secret: 可选，用于 Gmail API 身份验证的凭据
        include_read: 是否包含已读邮件（默认：False）
        skip_filters: 是否跳过会话和发件人筛选并返回全部邮件（默认：False）

    产出：
        包含已处理邮件信息的字典对象
    """
    use_mock = False
    
    # 检查是否需要使用模拟实现
    if not GMAIL_API_AVAILABLE:
        logger.info("Gmail API 不可用，正在使用模拟实现")
        use_mock = True
    
    # 检查所需凭据文件是否存在
    if not use_mock and not gmail_token and not gmail_secret:
        token_path = str(_SECRETS_DIR / "token.json")
        secrets_path = str(_SECRETS_DIR / "secrets.json")
        
        if not os.path.exists(token_path) and not os.path.exists(secrets_path):
            logger.warning("未找到 Gmail API 凭据，正在 .secrets 目录中查找 token.json 或 secrets.json")
            logger.warning("将改用模拟实现")
            use_mock = True
    
    # 如有需要，返回模拟数据
    if use_mock:
        # 为演示目的，返回一封模拟邮件
        mock_email = {
            "from_email": "sender@example.com",
            "to_email": email_address,
            "subject": "示例邮件主题",
            "page_content": "这是一封用于测试邮件助手的示例邮件。",
            "id": "mock-email-id-123",
            "thread_id": "mock-thread-id-123",
            "send_time": datetime.now().isoformat()
        }
        
        yield mock_email
        return
    
    try:
        # 从参数、环境变量或本地文件中获取 Gmail API 凭据
        creds = get_credentials(gmail_token, gmail_secret)
        
        # 检查凭据是否有效
        if not creds or not hasattr(creds, 'authorize'):
            logger.warning("Gmail 凭据无效，正在使用模拟实现")
            logger.warning("请确认已设置 GMAIL_TOKEN 环境变量，或 token.json 文件存在")
            mock_email = {
                "from_email": "sender@example.com",
                "to_email": email_address,
                "subject": "示例邮件主题：凭据无效",
                "page_content": "由于 Gmail 凭据无效，这是一封模拟邮件。",
                "id": "mock-email-id-123",
                "thread_id": "mock-thread-id-123",
                "send_time": datetime.now().isoformat()
            }
            yield mock_email
            return
            
        service = build("gmail", "v1", credentials=creds)
        
        # 计算用于筛选的时间戳
        after = int((datetime.now() - timedelta(minutes=minutes_since)).timestamp())
        
        # 构造 Gmail 搜索查询
        # 该查询将搜索：
        # - 收件人或发件人为指定地址的邮件
        # - 指定时间戳之后的邮件
        # - 所有类别中的邮件（收件箱、更新、促销等）
        
        # 带时间筛选的基础查询
        query = f"(to:{email_address} OR from:{email_address}) after:{after}"
        
        # 除非 include_read 为 True，否则只包含未读邮件
        if not include_read:
            query += " is:unread"
        else:
            logger.info("搜索中包含已读邮件")
            
        # 记录最终查询，便于调试
        logger.info(f"Gmail 搜索查询：{query}")
            
        # 其他筛选选项（默认注释）
        # 如需包含特定类别的邮件，请使用：
        # query += " category:(primary OR updates OR promotions)"
        
        # 获取所有匹配邮件（处理分页）
        messages = []
        nextPageToken = None
        logger.info(f"正在获取 {email_address} 在过去 {minutes_since} 分钟内的邮件")
        
        while True:
            results = (
                service.users()
                .messages()
                .list(userId="me", q=query, pageToken=nextPageToken)
                .execute()
            )
            if "messages" in results:
                new_messages = results["messages"]
                messages.extend(new_messages)
                logger.info(f"此页找到 {len(new_messages)} 封邮件")
            else:
                logger.info("此页未找到邮件")
                
            nextPageToken = results.get("nextPageToken")
            if not nextPageToken:
                logger.info(f"共找到 {len(messages)} 封邮件")
                break

        # 处理每封邮件
        count = 0
        for message in messages:
            try:
                # 获取完整邮件详情
                msg = service.users().messages().get(userId="me", id=message["id"]).execute()
                thread_id = msg["threadId"]
                payload = msg["payload"]
                headers = payload.get("headers", [])
                
                # 获取线程详情以确定会话上下文
                # 直接获取完整线程，不限制格式
                # 此处与测试代码中成功获取所有邮件的方法保持一致
                thread = service.users().threads().get(userId="me", id=thread_id).execute()
                messages_in_thread = thread["messages"]
                logger.info(f"已获取线程 {thread_id}，其中有 {len(messages_in_thread)} 封邮件")
                
                # 按 internalDate 排序，确保正确的时间顺序
                # 这确保能正确识别最新邮件
                if all("internalDate" in msg for msg in messages_in_thread):
                    messages_in_thread.sort(key=lambda m: int(m.get("internalDate", 0)))
                    logger.info(f"已按 internalDate 排序 {len(messages_in_thread)} 封邮件")
                else:
                    # internalDate 缺失时回退到基于 ID 的排序
                    messages_in_thread.sort(key=lambda m: m["id"])
                    logger.info(f"因缺少 internalDate，已按 ID 排序 {len(messages_in_thread)} 封邮件")
                
                # 记录线程中邮件的详情，便于调试
                for idx, msg in enumerate(messages_in_thread):
                    headers = msg["payload"]["headers"]
                    subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
                    from_email = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
                    date = next((h["value"] for h in headers if h["name"] == "Date"), "Unknown")
                    logger.info(f"  邮件 {idx+1}/{len(messages_in_thread)}：ID={msg['id']}，日期={date}，发件人={from_email}")
                
                # 记录线程信息，便于调试
                logger.info(f"线程 {thread_id} 包含 {len(messages_in_thread)} 封邮件")
                
                # 分析线程中最后一封邮件，确定是否需要处理
                last_message = messages_in_thread[-1]
                last_headers = last_message["payload"]["headers"]
                
                # 获取最后一封邮件的发件人
                from_header = next(
                    header["value"] for header in last_headers if header["name"] == "From"
                )
                last_from_header = next(
                    header["value"]
                    for header in last_message["payload"].get("headers")
                    if header["name"] == "From"
                )
                
                # 如果最后一封邮件由用户发送，则标记为用户回复
                # 且不再处理（助手无需回复用户自己的邮件）
                if email_address in last_from_header:
                    yield {
                        "id": message["id"],
                        "thread_id": message["threadId"],
                        "user_respond": True,
                    }
                    continue
                    
                # 检查这是否是应处理的邮件
                is_from_user = email_address in from_header
                is_latest_in_thread = message["id"] == last_message["id"]
                
                # skip_filters 的调整后逻辑：
                # 1. 当 skip_filters 为 True 时，不论在线程中的位置，处理所有邮件
                # 2. 当 skip_filters 为 False 时，仅处理非用户发送且为线程最新的邮件
                should_process = skip_filters or (not is_from_user and is_latest_in_thread)
                
                if not should_process:
                    if is_from_user:
                        logger.debug(f"跳过邮件 {message['id']}：由用户发送")
                    elif not is_latest_in_thread:
                        logger.debug(f"跳过邮件 {message['id']}：并非会话中的最新邮件")
                
                # 邮件通过筛选（或跳过筛选）时进行处理
                if should_process:
                    # 记录该邮件的详细信息
                    logger.info(f"正在处理线程 {thread_id} 中的邮件 {message['id']}")
                    logger.info(f"  是否为会话最新邮件：{is_latest_in_thread}")
                    logger.info(f"  是否启用跳过筛选：{skip_filters}")
                    
                    # 如用户希望处理线程中的最新邮件，
                    # 则使用线程 API 调用中的 last_message，而非原始搜索查询
                    # 匹配到的邮件
                    if not skip_filters:
                        # skip_filters 为 False 时使用原始邮件
                        process_message = message
                        process_payload = payload
                        process_headers = headers
                    else:
                        # skip_filters 为 True 时使用线程中的最新邮件
                        process_message = last_message
                        process_payload = last_message["payload"]
                        process_headers = process_payload.get("headers", [])
                        logger.info(f"正在使用会话中的最新邮件：{process_message['id']}")
                    
                    # 从邮件头中提取邮件元数据
                    subject = next(
                        header["value"] for header in process_headers if header["name"] == "Subject"
                    )
                    from_email = next(
                        (header["value"] for header in process_headers if header["name"] == "From"),
                        "",
                    ).strip()
                    _to_email = next(
                        (header["value"] for header in process_headers if header["name"] == "To"),
                        "",
                    ).strip()
                    
                    # 如有 Reply-To 邮件头，则使用它
                    if reply_to := next(
                        (
                            header["value"]
                            for header in process_headers
                            if header["name"] == "Reply-To"
                        ),
                        "",
                    ).strip():
                        from_email = reply_to
                        
                    # 提取并解析邮件时间戳
                    send_time = next(
                        header["value"] for header in process_headers if header["name"] == "Date"
                    )
                    parsed_time = parse_time(send_time)
                    
                    # 提取邮件正文
                    body = extract_message_part(process_payload)
                    
                    # 产出处理后的邮件数据
                    yield {
                        "from_email": from_email,
                        "to_email": _to_email,
                        "subject": subject,
                        "page_content": body,
                        "id": process_message["id"],
                        "thread_id": process_message["threadId"],
                        "send_time": parsed_time.isoformat(),
                    }
                    count += 1
                    
            except Exception as e:
                logger.warning(f"处理邮件 {message['id']} 失败：{str(e)}")

        logger.info(f"共 {len(messages)} 封邮件，其中 {count} 封需要处理。")
    
    except Exception as e:
        logger.error(f"访问 Gmail API 时出错：{str(e)}")
        # 回退到模拟实现
        mock_email = {
            "from_email": "sender@example.com",
            "to_email": email_address,
            "subject": "示例邮件主题",
            "page_content": "这是一封用于测试邮件助手的示例邮件。",
            "id": "mock-email-id-123",
            "thread_id": "mock-thread-id-123",
            "send_time": datetime.now().isoformat()
        }
        
        yield mock_email

class FetchEmailsInput(BaseModel):
    """
    fetch_emails_tool 的输入模式。
    """
    email_address: str = Field(
        description="要获取邮件的邮箱地址"
    )
    minutes_since: int = Field(
        default=30,
        description="仅获取在指定分钟数内收到的邮件"
    )

@tool(args_schema=FetchEmailsInput)
def fetch_emails_tool(email_address: str, minutes_since: int = 30) -> str:
    """
    从 Gmail 获取指定邮箱地址的近期邮件。
    
    参数：
        email_address: 要获取邮件的邮箱地址
        minutes_since: 仅获取在指定分钟数内收到的邮件（默认：30）
        
    返回：
        已获取邮件的摘要字符串
    """
    emails = list(fetch_group_emails(email_address, minutes_since))
    
    if not emails:
        return "未找到新邮件。"
    
    result = f"找到 {len(emails)} 封新邮件：\n\n"
    
    for i, email in enumerate(emails, 1):
        if email.get("user_respond", False):
            result += f"{i}. 您已回复此邮件（线程 ID：{email['thread_id']}）\n\n"
            continue
            
        result += f"{i}. 发件人：{email['from_email']}\n"
        result += f"   收件人：{email['to_email']}\n"
        result += f"   主题：{email['subject']}\n"
        result += f"   时间：{email['send_time']}\n"
        result += f"   ID：{email['id']}\n"
        result += f"   线程 ID：{email['thread_id']}\n"
        result += f"   内容：{email['page_content'][:200]}...\n\n"
    
    return result

class SendEmailInput(BaseModel):
    """
    send_email_tool 的输入模式。
    """
    email_id: str = Field(
        description="要回复的 Gmail 邮件 ID，必须是由 fetch_emails_tool 获取的有效 Gmail 邮件 ID。若要新建邮件而非回复，可使用如 'NEW_EMAIL' 的任意字符串。"
    )
    response_text: str = Field(
        description="回复内容"
    )
    email_address: str = Field(
        description="当前用户的邮箱地址"
    )
    additional_recipients: Optional[List[str]] = Field(
        default=None,
        description="可选，需要抄送的其他收件人"
    )

# 用于发送邮件的辅助函数
def send_email(
    email_id: str,
    response_text: str,
    email_address: str,
    addn_receipients: Optional[List[str]] = None
) -> bool:
    """
    回复现有邮件会话或创建新邮件。
    
    参数：
        email_id: 要回复的 Gmail 邮件 ID。若该 ID 无效（例如创建新邮件时），函数会创建新邮件而非回复现有会话。
        response_text: 回复或新邮件的内容
        email_address: 当前用户的邮箱地址（发件人）
        addn_receipients: 可选，其他收件人

    返回：
        成功标记（邮件已发送时为 True）
    """
    if not GMAIL_API_AVAILABLE:
        logger.info("Gmail API 不可用，正在模拟发送邮件")
        logger.info(f"将发送：{response_text[:100]}...")
        return True
        
    try:
        # 从环境变量或本地文件获取 Gmail API 凭据
        creds = get_credentials(
            gmail_token=os.getenv("GMAIL_TOKEN"),
            gmail_secret=os.getenv("GMAIL_SECRET")
        )
        service = build("gmail", "v1", credentials=creds)
        
        try:
            # 尝试获取原始邮件以提取邮件头
            message = service.users().messages().get(userId="me", id=email_id).execute()
            headers = message["payload"]["headers"]
            
            # 提取主题；如果尚未存在则添加 Re: 前缀
            subject = next(header["value"] for header in headers if header["name"] == "Subject")
            if not subject.startswith("Re:"):
                subject = f"Re: {subject}"
                
            # 创建回复邮件
            original_from = next(header["value"] for header in headers if header["name"] == "From")
            
            # 从邮件中获取线程 ID
            thread_id = message["threadId"]
        except Exception as e:
            logger.warning(f"无法获取 ID 为 {email_id} 的原始邮件。错误：{str(e)}")
            # 无法获取原始邮件时，以最少信息创建一封新邮件
            subject = "回复"
            original_from = "recipient@example.com"  # 将由用户输入覆盖
            thread_id = None
            
        # 创建邮件对象
        msg = MIMEText(response_text)
        msg["to"] = original_from
        msg["from"] = email_address
        msg["subject"] = subject
        
        # 如有指定，添加其他收件人
        if addn_receipients:
            msg["cc"] = ", ".join(addn_receipients)
            
        # 编码邮件
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        
        # 准备邮件正文
        body = {"raw": raw}
        # 仅在线程 ID 存在时添加 threadId
        if thread_id:
            body["threadId"] = thread_id
            
        # 发送邮件
        sent_message = (
            service.users()
            .messages()
            .send(
                userId="me",
                body=body,
            )
            .execute()
        )
        
        logger.info(f"邮件已发送：邮件 ID {sent_message['id']}")
        return True
        
    except Exception as e:
        logger.error(f"发送邮件时出错：{str(e)}")
        return False

@tool(args_schema=SendEmailInput)
def send_email_tool(
    email_id: str,
    response_text: str,
    email_address: str,
    additional_recipients: Optional[List[str]] = None
) -> str:
    """
    在 Gmail 中回复现有邮件会话或创建新邮件。
    
    参数：
        email_id: 要回复的 Gmail 邮件 ID，应由 fetch_emails_tool 获取。若要新建邮件而非回复，可使用如 "NEW_EMAIL" 的任意字符串标识。
        response_text: 回复或新邮件的内容
        email_address: 当前用户的邮箱地址（发件人）
        additional_recipients: 可选，需要包含的其他收件人

    返回：
        确认消息
    """
    try:
        success = send_email(
            email_id,
            response_text,
            email_address,
            addn_receipients=additional_recipients
        )
        if success:
            return f"已成功回复邮件 ID：{email_id}"
        else:
            return "因 API 错误，邮件发送失败"
    except Exception as e:
        return f"邮件发送失败：{str(e)}"

class CheckCalendarInput(BaseModel):
    """
    check_calendar_tool 的输入模式。
    """
    dates: List[str] = Field(
        description="要查询的日期列表，格式为 DD-MM-YYYY"
    )

def get_calendar_events(dates: List[str]) -> str:
    """
    查询 Google 日历在指定日期的日程。
    
    参数：
        dates: 要查询的日期列表，格式为 DD-MM-YYYY
        
    返回：
        指定日期的格式化日程信息
    """
    if not GMAIL_API_AVAILABLE:
        logger.info("Gmail API 不可用，正在模拟日历查询")
        # 回退：为演示和测试目的返回模拟日历数据
        # 在生产环境中，此处应使用真实的 Google Calendar API
        result = "日历日程：\n\n"
        for date in dates:
            result += f"{date} 的日程：\n"
            result += "  - 上午 9:00 - 10:00：团队会议\n"
            result += "  - 下午 2:00 - 3:00：项目评审\n"
            result += "可用时段：上午 10:00 至下午 2:00，下午 3:00 后\n\n"
        return result
        
    try:
        # 从环境变量或本地文件获取 Gmail API 凭据
        creds = get_credentials(
            gmail_token=os.getenv("GMAIL_TOKEN"),
            gmail_secret=os.getenv("GMAIL_SECRET")
        )
        service = build("calendar", "v3", credentials=creds)
        
        result = "日历日程：\n\n"
        
        for date_str in dates:
            # 解析日期字符串（DD-MM-YYYY）
            day, month, year = date_str.split("-")
            
            # 将开始和结束时间格式化为 API 所需格式
            start_time = f"{year}-{month}-{day}T00:00:00Z"
            end_time = f"{year}-{month}-{day}T23:59:59Z"
            
            # 调用 Calendar API
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_time,
                    timeMax=end_time,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            
            events = events_result.get("items", [])
            
            result += f"{date_str} 的日程：\n"
            
            if not events:
                result += "  当天没有日程\n"
                result += "  全天可用\n\n"
                continue
                
            # 处理事件
            busy_slots = []
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))
                
                # 转换为 datetime 对象
                if "T" in start:  # dateTime 格式
                    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                    
                    # 格式化以便显示
                    start_display = start_dt.strftime("%I:%M %p")
                    end_display = end_dt.strftime("%I:%M %p")
                    
                    result += f"  - {start_display} - {end_display}: {event['summary']}\n"
                    busy_slots.append((start_dt, end_dt))
                else:  # 全天事件
                    result += f"  - 全天：{event['summary']}\n"
                    busy_slots.append(("all-day", "all-day"))
            
            # 计算可用时段
            if "all-day" in [slot[0] for slot in busy_slots]:
                result += "  可用时段：无（存在全天日程）\n\n"
            else:
                # 按开始时间对忙碌时段排序
                busy_slots.sort(key=lambda x: x[0])
                
                # 定义工作时间（上午 9 点至下午 5 点）
                # 注意：为简化起见，当前工作时间为硬编码
                # 在生产环境中，可按用户或组织进行配置
                work_start = datetime(
                    year=int(year), 
                    month=int(month), 
                    day=int(day), 
                    hour=9, 
                    minute=0
                )
                work_end = datetime(
                    year=int(year), 
                    month=int(month), 
                    day=int(day), 
                    hour=17, 
                    minute=0
                )
                
                # 计算可用时段
                available_slots = []
                current = work_start
                
                for start, end in busy_slots:
                    if current < start:
                        available_slots.append((current, start))
                    current = max(current, end)
                
                if current < work_end:
                    available_slots.append((current, work_end))
                
                # 格式化可用时段
                if available_slots:
                    result += "  可用时段："
                    for i, (start, end) in enumerate(available_slots):
                        start_display = start.strftime("%I:%M %p")
                        end_display = end.strftime("%I:%M %p")
                        result += f"{start_display} - {end_display}"
                        if i < len(available_slots) - 1:
                            result += ", "
                    result += "\n\n"
                else:
                    result += "  可用时段：工作时间内无空闲\n\n"
        
        return result
        
    except Exception as e:
        logger.error(f"查询日历时出错：{str(e)}")
        # 发生错误时返回模拟数据
        result = "日历日程（因错误返回模拟数据）：\n\n"
        for date in dates:
            result += f"{date} 的日程：\n"
            result += "  - 上午 9:00 - 10:00：团队会议\n"
            result += "  - 下午 2:00 - 3:00：项目评审\n"
            result += "可用时段：上午 10:00 至下午 2:00，下午 3:00 后\n\n"
        return result

@tool(args_schema=CheckCalendarInput)
def check_calendar_tool(dates: List[str]) -> str:
    """
    查询 Google 日历在指定日期的日程。
    
    参数：
        dates: 要查询的日期列表，格式为 DD-MM-YYYY
        
    返回：
        指定日期的格式化日程信息
    """
    try:
        events = get_calendar_events(dates)
        return events
    except Exception as e:
        return f"查询日历失败：{str(e)}"

class ScheduleMeetingInput(BaseModel):
    """
    schedule_meeting_tool 的输入模式。
    """
    attendees: List[str] = Field(
        description="会议参会人的邮箱地址"
    )
    title: str = Field(
        description="会议标题/主题"
    )
    start_time: str = Field(
        description="会议开始时间，ISO 格式（YYYY-MM-DDTHH:MM:SS）"
    )
    end_time: str = Field(
        description="会议结束时间，ISO 格式（YYYY-MM-DDTHH:MM:SS）"
    )
    organizer_email: str = Field(
        description="会议组织者的邮箱地址"
    )
    timezone: str = Field(
        default="America/Los_Angeles",
        description="会议时区"
    )

def send_calendar_invite(
    attendees: List[str],
    title: str,
    start_time: str,
    end_time: str,
    organizer_email: str,
    timezone: str = "America/Los_Angeles"
) -> bool:
    """
    通过 Google 日历安排会议并发送邀请。
    
    参数：
        attendees: 会议参会人的邮箱地址
        title: 会议标题/主题
        start_time: 会议开始时间，ISO 格式（YYYY-MM-DDTHH:MM:SS）
        end_time: 会议结束时间，ISO 格式（YYYY-MM-DDTHH:MM:SS）
        organizer_email: 会议组织者的邮箱地址
        timezone: 会议时区

    返回：
        成功标记（会议安排成功时为 True）
    """
    if not GMAIL_API_AVAILABLE:
        logger.info("Gmail API 不可用，正在模拟发送日历邀请")
        logger.info(f"将安排会议：{title}，时间为 {start_time} 至 {end_time}")
        logger.info(f"参会人：{', '.join(attendees)}")
        return True
        
    try:
        # 从环境变量或本地文件获取 Gmail API 凭据
        creds = get_credentials(
            gmail_token=os.getenv("GMAIL_TOKEN"),
            gmail_secret=os.getenv("GMAIL_SECRET")
        )
        service = build("calendar", "v3", credentials=creds)
        
        # 创建事件详情
        event = {
            "summary": title,
            "start": {
                "dateTime": start_time,
                "timeZone": timezone,
            },
            "end": {
                "dateTime": end_time,
                "timeZone": timezone,
            },
            "attendees": [{"email": email} for email in attendees],
            "organizer": {
                "email": organizer_email,
                "self": True,
            },
            "reminders": {
                "useDefault": True,
            },
            "sendUpdates": "all",  # 向参会者发送邮件通知
        }
        
        # 创建事件
        event = service.events().insert(calendarId="primary", body=event).execute()
        
        logger.info(f"会议已创建：{event.get('htmlLink')}")
        return True
        
    except Exception as e:
        logger.error(f"安排会议时出错：{str(e)}")
        return False

@tool(args_schema=ScheduleMeetingInput)
def schedule_meeting_tool(
    attendees: List[str],
    title: str,
    start_time: str,
    end_time: str,
    organizer_email: str,
    timezone: str = "America/Los_Angeles"
) -> str:
    """
    通过 Google 日历安排会议并发送邀请。
    
    参数：
        attendees: 会议参会人的邮箱地址
        title: 会议标题/主题
        start_time: 会议开始时间，ISO 格式（YYYY-MM-DDTHH:MM:SS）
        end_time: 会议结束时间，ISO 格式（YYYY-MM-DDTHH:MM:SS）
        organizer_email: 会议组织者的邮箱地址
        timezone: 会议时区（默认：America/Los_Angeles）

    返回：
        成功或失败消息
    """
    try:
        success = send_calendar_invite(
            attendees,
            title,
            start_time,
            end_time,
            organizer_email,
            timezone
        )
        
        if success:
            return f"会议“{title}”已成功安排在 {start_time} 至 {end_time}，共有 {len(attendees)} 位参会人"
        else:
            return "安排会议失败"
    except Exception as e:
        return f"安排会议时出错：{str(e)}"
    
def mark_as_read(
    message_id,
    gmail_token: str | None = None,
    gmail_secret: str | None = None,
):
    creds = get_credentials(gmail_token, gmail_secret)

    service = build("gmail", "v1", credentials=creds)
    service.users().messages().modify(
        userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()
