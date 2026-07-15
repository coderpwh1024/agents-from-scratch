#!/usr/bin/env python
"""
基于 test.ipynb 的简易 Gmail 导入脚本，支持 LangSmith 追踪。

此脚本以最小实现将邮件导入 LangGraph 服务器，并提供可靠的 LangSmith 追踪。
"""

import base64
import json
import uuid
import hashlib
import asyncio
import argparse
import os
from pathlib import Path
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from langgraph_sdk import get_client
from dotenv import load_dotenv

load_dotenv()

# 设置路径
_ROOT = Path(__file__).parent.absolute()
_SECRETS_DIR = _ROOT / ".secrets"
TOKEN_PATH = _SECRETS_DIR / "token.json"

def extract_message_part(payload):
    """从邮件片段中提取内容。"""
    # 如果这是多部分邮件，优先处理 text/plain 部分
    if payload.get("parts"):
        # 先尝试查找 text/plain 部分
        for part in payload["parts"]:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/plain" and part.get("body", {}).get("data"):
                data = part["body"]["data"]
                return base64.urlsafe_b64decode(data).decode("utf-8")
                
        # 如果未找到 text/plain，则尝试 text/html
        for part in payload["parts"]:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/html" and part.get("body", {}).get("data"):
                data = part["body"]["data"]
                return base64.urlsafe_b64decode(data).decode("utf-8")
                
        # 如果仍未找到内容，则递归检查嵌套部分
        for part in payload["parts"]:
            content = extract_message_part(part)
            if content:
                return content
    
    # 非多部分邮件，直接尝试获取内容
    if payload.get("body", {}).get("data"):
        data = payload["body"]["data"]
        return base64.urlsafe_b64decode(data).decode("utf-8")

    return ""

def load_gmail_credentials():
    """
    从 token.json 或环境变量加载 Gmail 凭据。
    
    此函数会按以下顺序尝试从多个来源加载凭据：
    1. 环境变量 GMAIL_TOKEN
    2. 本地文件 token_path（.secrets/token.json）
    
    返回：
        Google OAuth2 Credentials 对象；无法加载凭据时返回 None
    """
    token_data = None
    
    # 1. 尝试环境变量
    env_token = os.getenv("GMAIL_TOKEN")
    if env_token:
        try:
            token_data = json.loads(env_token)
            print("正在使用 GMAIL_TOKEN 环境变量")
        except Exception as e:
            print(f"无法解析 GMAIL_TOKEN 环境变量：{str(e)}")
    
    # 2. 回退至本地文件
    if token_data is None:
        if TOKEN_PATH.exists():
            try:
                with open(TOKEN_PATH, "r") as f:
                    token_data = json.load(f)
                print(f"正在使用 {TOKEN_PATH} 中的令牌")
            except Exception as e:
                print(f"无法从 {TOKEN_PATH} 加载令牌：{str(e)}")
        else:
            print(f"未找到令牌文件：{TOKEN_PATH}")
    
    # 如果无法从任何来源获得令牌数据，则返回 None
    if token_data is None:
        print("未在任何位置找到有效的令牌数据")
        return None
    
    try:
        # 创建凭据对象
        credentials = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes", ["https://www.googleapis.com/auth/gmail.modify"])
        )
        return credentials
    except Exception as e:
        print(f"创建凭据对象时出错：{str(e)}")
        return None

def extract_email_data(message):
    """从 Gmail 邮件中提取关键信息。"""
    headers = message['payload']['headers']
    
    # 提取关键邮件头
    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '无主题')
    from_email = next((h['value'] for h in headers if h['name'] == 'From'), '未知发件人')
    to_email = next((h['value'] for h in headers if h['name'] == 'To'), '未知收件人')
    date = next((h['value'] for h in headers if h['name'] == 'Date'), '未知日期')
    
    # 提取邮件正文
    content = extract_message_part(message['payload'])
    
    # 创建邮件数据对象
    email_data = {
        "from_email": from_email,
        "to_email": to_email,
        "subject": subject,
        "page_content": content,
        "id": message['id'],
        "thread_id": message['threadId'],
        "send_time": date
    }
    
    return email_data

async def ingest_email_to_langgraph(email_data, graph_name, url="http://127.0.0.1:2024"):
    """将邮件导入 LangGraph。"""
    # 连接到 LangGraph 服务器
    client = get_client(url=url)
    
    # 为线程创建稳定一致的 UUID
    raw_thread_id = email_data["thread_id"]
    thread_id = str(
        uuid.UUID(hex=hashlib.md5(raw_thread_id.encode("UTF-8")).hexdigest())
    )
    print(f"Gmail 线程 ID：{raw_thread_id} → LangGraph 线程 ID：{thread_id}")
    
    thread_exists = False
    try:
        # 尝试获取已有线程信息
        thread_info = await client.threads.get(thread_id)
        thread_exists = True
        print(f"找到已有线程：{thread_id}")
    except Exception as e:
        # 如果线程不存在，则创建它
        print(f"正在创建新线程：{thread_id}")
        thread_info = await client.threads.create(thread_id=thread_id)
    
    # 如果线程已存在，清理先前的运行记录
    if thread_exists:
        try:
            # 列出该线程的所有运行记录
            runs = await client.runs.list(thread_id)
            
            # 删除所有先前运行记录，避免状态累积
            for run_info in runs:
                run_id = run_info.id
                print(f"正在删除线程 {thread_id} 中之前的运行记录 {run_id}")
                try:
                    await client.runs.delete(thread_id, run_id)
                except Exception as e:
                    print(f"删除运行记录 {run_id} 失败：{str(e)}")
        except Exception as e:
            print(f"列出或删除运行记录时出错：{str(e)}")
    
    # 使用当前邮件 ID 更新线程元数据
    await client.threads.update(thread_id, metadata={"email_id": email_data["id"]})
    
    # 为该邮件创建新的运行记录
    print(f"正在使用图 {graph_name} 为线程 {thread_id} 创建运行记录")
    
    run = await client.runs.create(
        thread_id,
        graph_name,
        input={"email_input": {
            "from": email_data["from_email"],
            "to": email_data["to_email"],
            "subject": email_data["subject"],
            "body": email_data["page_content"],
            "id": email_data["id"]
        }},
        multitask_strategy="rollback",
    )
    
    print(f"已成功创建运行记录，线程 ID：{thread_id}")
    
    return thread_id, run

async def fetch_and_process_emails(args):
    """从 Gmail 获取邮件并通过 LangGraph 处理。"""
    # 加载 Gmail 凭据
    credentials = load_gmail_credentials()
    if not credentials:
        print("加载 Gmail 凭据失败")
        return 1
        
    # 构建 Gmail 服务
    service = build("gmail", "v1", credentials=credentials)
    
    # 处理邮件
    processed_count = 0
    
    try:
        # 获取与指定邮箱地址相关的邮件
        email_address = args.email
        
        # 构造 Gmail 搜索查询
        query = f"to:{email_address} OR from:{email_address}"
        
        # 如有指定，添加时间限制
        if args.minutes_since > 0:
            # 计算用于筛选的时间戳
            from datetime import timedelta
            after = int((datetime.now() - timedelta(minutes=args.minutes_since)).timestamp())
            query += f" after:{after}"
            
        # 除非 include_read 为 True，否则只包含未读邮件
        if not args.include_read:
            query += " is:unread"
            
        print(f"Gmail 搜索查询：{query}")
        
        # 执行搜索
        results = service.users().messages().list(userId="me", q=query).execute()
        messages = results.get("messages", [])
        
        if not messages:
            print("未找到符合条件的邮件")
            return 0
            
        print(f"找到 {len(messages)} 封邮件")
        
        # 逐封处理邮件
        for i, message_info in enumerate(messages):
            # 如有要求则提前停止
            if args.early and i > 0:
                print(f"处理 {i} 封邮件后提前停止")
                break
                
            # 检查是否应重新处理该邮件
            if not args.rerun:
                # TODO：增加对已处理邮件的检查
                pass
                
            # 获取完整邮件
            message = service.users().messages().get(userId="me", id=message_info["id"]).execute()
            
            # 提取邮件数据
            email_data = extract_email_data(message)
            
            print(f"\n正在处理邮件 {i+1}/{len(messages)}：")
            print(f"发件人：{email_data['from_email']}")
            print(f"主题：{email_data['subject']}")
            
            # 导入到 LangGraph
            thread_id, run = await ingest_email_to_langgraph(
                email_data, 
                args.graph_name,
                url=args.url
            )
            
            processed_count += 1
            
        print(f"\n已成功处理 {processed_count} 封邮件")
        return 0
        
    except Exception as e:
        print(f"处理邮件时出错：{str(e)}")
        return 1

def parse_args():
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="带可靠追踪功能的 LangGraph 简易 Gmail 导入工具")
    
    parser.add_argument(
        "--email", 
        type=str, 
        required=True,
        help="要获取邮件的邮箱地址"
    )
    parser.add_argument(
        "--minutes-since", 
        type=int, 
        default=120,
        help="仅获取在指定分钟数内收到的邮件"
    )
    parser.add_argument(
        "--graph-name", 
        type=str, 
        default="email_assistant_hitl_memory_gmail",
        help="要使用的 LangGraph 名称"
    )
    parser.add_argument(
        "--url", 
        type=str, 
        default="http://127.0.0.1:2024",
        help="LangGraph 部署的 URL"
    )
    parser.add_argument(
        "--early", 
        action="store_true",
        help="处理一封邮件后提前停止"
    )
    parser.add_argument(
        "--include-read",
        action="store_true",
        help="包含已读邮件"
    )
    parser.add_argument(
        "--rerun", 
        action="store_true",
        help="即使邮件已处理过，也再次处理"
    )
    parser.add_argument(
        "--skip-filters",
        action="store_true",
        help="跳过邮件筛选"
    )
    return parser.parse_args()

if __name__ == "__main__":
    # 获取命令行参数
    args = parse_args()
    
    # 运行脚本
    exit(asyncio.run(fetch_and_process_emails(args)))
