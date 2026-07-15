from pydantic import BaseModel, Field
from typing_extensions import Literal, NotRequired, TypedDict
from langgraph.graph import MessagesState

class RouterSchema(BaseModel):
    """分析未读邮件，并根据其内容进行路由。"""

    reasoning: str = Field(
        description="分类背后的逐步推理过程。"
    )
    classification: Literal["ignore", "respond", "notify"] = Field(
        description="邮件的分类：'ignore' 表示不相关的邮件，"
        "'notify' 表示不需要回复的重要信息，"
        "'respond' 表示需要回复的邮件",
    )

class StateInput(MessagesState):
    """在图入口处接收结构化邮件或聊天界面消息。"""

    email_input: NotRequired[dict]

class State(MessagesState):
    # 此状态类内置了 messages 键
    email_input: dict
    classification_decision: Literal["ignore", "respond", "notify"]

class EmailData(TypedDict):
    id: str
    thread_id: str
    from_email: str
    subject: str
    page_content: str
    send_time: str
    to_email: str

class UserPreferences(BaseModel):
    """根据用户反馈更新后的用户偏好。"""
    chain_of_thought: str = Field(description="对需要添加或更新哪些用户偏好的推理")
    user_preferences: str = Field(description="更新后的用户偏好")
