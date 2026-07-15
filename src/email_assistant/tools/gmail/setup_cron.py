#!/usr/bin/env python
"""
为 LangGraph 邮件导入配置 cron 任务。

此脚本会在 LangGraph 中创建定时 cron 任务，周期性运行邮件导入图以处理新邮件。
"""

import argparse
import asyncio
from typing import Optional
from langgraph_sdk import get_client
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

async def main(
    email: str,
    url: Optional[str] = None,
    minutes_since: int = 60,
    schedule: str = "*/10 * * * *",
    graph_name: str = "email_assistant_hitl_memory_gmail",
    include_read: bool = False,
):
    """为邮件导入配置 cron 任务。"""
    # 连接到 LangGraph 服务器
    if url is None:
        client = get_client(url="http://127.0.0.1:2024")
    else:
        client = get_client(url=url)
    
    # 创建 cron 任务配置
    cron_input = {
        "email": email,
        "minutes_since": minutes_since,
        "graph_name": graph_name,
        "url": url if url else "http://127.0.0.1:2024",
        "include_read": include_read,
        "rerun": False,
        "early": False,
        "skip_filters": False
    }
    
    # 注册 cron 任务
    cron = await client.crons.create(
        "cron",              # cron 使用的图名称
        schedule=schedule,   # Cron 调度表达式
        input=cron_input     # cron 图的输入参数
    )
    
    print(f"已成功创建 cron 任务，调度表达式：{schedule}")
    print(f"将为以下邮箱导入邮件：{email}")
    print(f"处理过去 {minutes_since} 分钟内的邮件")
    print(f"使用的图：{graph_name}")
    
    return cron

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="为 LangGraph 邮件导入配置 cron 任务")
    
    parser.add_argument(
        "--email",
        type=str,
        required=True,
        help="要获取邮件的邮箱地址",
    )
    parser.add_argument(
        "--url",
        type=str,
        required=True,
        help="LangGraph 服务器的 URL",
    )
    parser.add_argument(
        "--minutes-since",
        type=int,
        default=60,
        help="仅处理在指定分钟数内收到的邮件",
    )
    parser.add_argument(
        "--schedule",
        type=str,
        default="*/10 * * * *",
        help="Cron 调度表达式（默认：每 10 分钟）",
    )
    parser.add_argument(
        "--graph-name",
        type=str,
        default="email_assistant_hitl_memory_gmail",
        help="用于处理邮件的图名称",
    )
    parser.add_argument(
        "--include-read",
        action="store_true",
        help="包含已读邮件",
    )
    
    args = parser.parse_args()
    
    asyncio.run(
        main(
            email=args.email,
            url=args.url,
            minutes_since=args.minutes_since,
            schedule=args.schedule,
            graph_name=args.graph_name,
            include_read=args.include_read,
        )
    )
