import os
import sys
import asyncio
from typing import Dict, Any, TypedDict
from dataclasses import dataclass, field
from langgraph.graph import StateGraph, START, END
from email_assistant.tools.gmail.run_ingest import fetch_and_process_emails

@dataclass(kw_only=True)
class JobKickoff:
    """邮件摄取定时任务的状态。"""
    email: str
    minutes_since: int = 60
    graph_name: str = "email_assistant_hitl_memory_gmail"
    url: str = "http://127.0.0.1:2024"
    include_read: bool = False
    rerun: bool = False
    early: bool = False
    skip_filters: bool = False

async def main(state: JobKickoff):
    """运行邮件摄取流程。"""
    print(f"开始执行任务：获取过去 {state.minutes_since} 分钟内的邮件")
    print(f"邮箱：{state.email}")
    print(f"URL：{state.url}")
    print(f"图名称：{state.graph_name}")
    
    try:
        # 将状态转换为 fetch_and_process_emails 所需的参数对象
        class Args:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
                print(f"已创建 Args 对象，其属性为：{dir(self)}")
        
        args = Args(
            email=state.email,
            minutes_since=state.minutes_since,
            graph_name=state.graph_name,
            url=state.url,
            include_read=state.include_read,
            rerun=state.rerun,
            early=state.early,
            skip_filters=state.skip_filters
        )
        
        # 打印邮箱和 URL，验证它们是否被正确传入
        print(f"Args 邮箱：{args.email}")
        print(f"Args URL：{args.url}")
        
        # 运行摄取流程
        print("开始执行 fetch_and_process_emails...")
        result = await fetch_and_process_emails(args)
        print(f"fetch_and_process_emails 返回结果：{result}")
        
        # 返回结果状态
        return {"status": "success" if result == 0 else "error", "exit_code": result}
    except Exception as e:
        import traceback
        print(f"定时任务发生错误：{str(e)}")
        print(traceback.format_exc())
        return {"status": "error", "error": str(e)}

# 构建图
graph = StateGraph(JobKickoff)
graph.add_node("ingest_emails", main)
graph.set_entry_point("ingest_emails")
graph = graph.compile()
