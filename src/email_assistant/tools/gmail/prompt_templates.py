"""Gmail 集成的工具提示词模板。"""

# 用于插入智能体系统提示词的 Gmail 工具提示词
GMAIL_TOOLS_PROMPT = """
1. fetch_emails_tool(email_address, minutes_since) - 从 Gmail 获取近期邮件
2. send_email_tool(email_id, response_text, email_address, additional_recipients) - 回复邮件会话
3. check_calendar_tool(dates) - 查询指定日期的 Google 日历空闲情况
4. schedule_meeting_tool(attendees, title, start_time, end_time, organizer_email, timezone) - 安排会议并发送邀请
5. triage_email(ignore, notify, respond) - 将邮件分诊为三类之一
6. Done - 邮件已发送
"""

# 完整集成使用的组合工具提示词（默认工具 + Gmail）
COMBINED_TOOLS_PROMPT = """
1. fetch_emails_tool(email_address, minutes_since) - 从 Gmail 获取近期邮件
2. send_email_tool(email_id, response_text, email_address, additional_recipients) - 回复邮件会话
3. check_calendar_tool(dates) - 查询指定日期的 Google 日历空闲情况
4. schedule_meeting_tool(attendees, title, start_time, end_time, organizer_email, timezone) - 安排会议并发送邀请
5. write_email(to, subject, content) - 为指定收件人起草邮件
6. triage_email(ignore, notify, respond) - 将邮件分诊为三类之一
7. check_calendar_availability(day) - 查询指定日期的可用时段
8. Done - 邮件已发送
"""
