from datetime import datetime
from typing import TypedDict, Literal, NotRequired

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field


# 路由模型
class RouterSchema(BaseModel):
    """路由模式"""
    reasoning: str = Field(description="推理结果")
    classification: Literal["ignore", "respond", "notify"] = Field(description="分类结果")


# 状态输入
class StateInput(MessagesState):
    """状态输入"""
    email_input: NotRequired[dict]


# 状态
class State(MessagesState):
    """状态"""
    email_input: dict
    classification_decision: Literal["ignore", "respond", "notify"]


# 邮件数据
class EmailData(TypedDict):
    """邮件数据"""
    id: int
    thread_id: str
    from_email: str
    subject: str
    page_content: str
    send_time: datetime
    to_email: str


class UserPreferences(BaseModel):
    """用户偏好"""
    user_preferences_reason: str = Field(description="更新原因")
    user_preferences: str = Field(description="更新后的用户偏好")
