"""Tool prompt templates for the email assistant."""

# 用于插入提示词的标准工具说明
STANDARD_TOOLS_PROMPT = """
1. triage_email(ignore, notify, respond) - 将邮件分诊为三类之一
2. write_email(to, subject, content) - 向指定收件人发送邮件
3. schedule_meeting(attendees, subject, duration_minutes, preferred_day, start_time) - 安排日历会议，其中 preferred_day 为 datetime 对象
4. check_calendar_availability(day) - 查询指定日期的可用时段
5. Done - 邮件已发送
"""

# HITL 工作流的工具说明
HITL_TOOLS_PROMPT = """
1. write_email(to, subject, content) - 向指定收件人发送邮件
2. schedule_meeting(attendees, subject, duration_minutes, preferred_day, start_time) - 安排日历会议，其中 preferred_day 为 datetime 对象
3. check_calendar_availability(day) - 查询指定日期的可用时段
4. Question(content) - 向用户提出任何后续问题
5. Done - 邮件已发送
"""

# 带记忆的 HITL 工作流工具说明
# 注意：可在此添加其他记忆专用工具
HITL_MEMORY_TOOLS_PROMPT = """
1. write_email(to, subject, content) - 向指定收件人发送邮件
2. schedule_meeting(attendees, subject, duration_minutes, preferred_day, start_time) - 安排日历会议，其中 preferred_day 为 datetime 对象
3. check_calendar_availability(day) - 查询指定日期的可用时段
4. Question(content) - 向用户提出任何后续问题
5. Done - 邮件已发送
"""

# 不含分诊步骤的智能体工作流工具说明
AGENT_TOOLS_PROMPT = """
1. write_email(to, subject, content) - 向指定收件人发送邮件
2. schedule_meeting(attendees, subject, duration_minutes, preferred_day, start_time) - 安排日历会议，其中 preferred_day 为 datetime 对象
3. check_calendar_availability(day) - 查询指定日期的可用时段
4. Done - 邮件已发送
"""
