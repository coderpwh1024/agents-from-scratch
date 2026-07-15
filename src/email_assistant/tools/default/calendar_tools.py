from datetime import datetime
from langchain_core.tools import tool

@tool
def schedule_meeting(
    attendees: list[str], subject: str, duration_minutes: int, preferred_day: datetime, start_time: int
) -> str:
    """Schedule a calendar meeting."""
    # 占位响应：真实应用中会检查日历并创建日程
    date_str = preferred_day.strftime("%A, %B %d, %Y")
    return f"Meeting '{subject}' scheduled on {date_str} at {start_time} for {duration_minutes} minutes with {len(attendees)} attendees"

@tool
def check_calendar_availability(day: str) -> str:
    """Check calendar availability for a given day."""
    # 占位响应：真实应用中会查询实际日历
    return f"Available times on {day}: 9:00 AM, 2:00 PM, 4:00 PM"
