"""千问聊天模型的统一配置入口。"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


DEFAULT_QWEN_MODEL = "qwen-plus"
DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def get_chat_model(*, temperature: float = 0.0, model: str | None = None) -> ChatOpenAI:
    """创建通过阿里云百炼 OpenAI 兼容接口调用的千问聊天模型。

    ``QWEN_MODEL`` 可覆盖默认业务模型，``DASHSCOPE_BASE_URL`` 可用于
    配置其他地域或工作空间的百炼兼容接口地址。
    """
    load_dotenv(".env")
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "未配置 DASHSCOPE_API_KEY。请在 .env 或环境变量中设置阿里云百炼 API Key。"
        )

    return ChatOpenAI(
        model=model or os.getenv("QWEN_MODEL", DEFAULT_QWEN_MODEL),
        temperature=temperature,
        api_key=api_key,
        base_url=os.getenv("DASHSCOPE_BASE_URL", DEFAULT_DASHSCOPE_BASE_URL),
    )
