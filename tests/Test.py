"""查询 Hipobuy 订单信息。

示例：
    HIPO_BUY_CLIENT_ID=your_client_id HIPO_BUY_SECRET_KEY=your_secret_key \\
        python tests/Test.py --order-no YOUR_ORDER_NO

也可通过 --client-id、--secret-key 覆盖环境变量，便于密钥轮换。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ORDER_QUERY_URL = "https://api.hipobuy.com/openapi/v1/order/helpKnowQuery"
DEFAULT_TIMEOUT_SECONDS = 15


def create_signature(request_date: str, timestamp: int, secret_key: str) -> str:
    """按 Hipobuy 规则生成签名：MD5(date + timestamp + secret_key).upper()。"""
    if not secret_key:
        raise ValueError("secret_key 不能为空")

    sign_source = f"{request_date}{timestamp}{secret_key}"
    return hashlib.md5(sign_source.encode("utf-8")).hexdigest().upper()


def build_order_query_payload(order_no: str, secret_key: str) -> dict[str, str | int]:
    """构造订单查询请求体，并附加日期、毫秒时间戳和签名。"""
    if not order_no.strip():
        raise ValueError("order_no 不能为空")

    request_date = date.today().isoformat()
    timestamp = int(time.time() * 1000)
    return {
        "orderNo": order_no,
        "date": request_date,
        "timestamp": timestamp,
        "signature": create_signature(request_date, timestamp, secret_key),
    }


def _print_json(label: str, value: Any) -> None:
    print(f"\n{label}:")  # noqa: T201
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))  # noqa: T201


def query_order(
    order_no: str,
    client_id: str,
    secret_key: str,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """调用订单查询接口并打印请求和响应中的关键字段。"""
    if not client_id:
        raise ValueError("client_id 不能为空")

    payload = build_order_query_payload(order_no, secret_key)
    headers = {
        "Client-Id": client_id,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # 不输出 secret_key 或参与签名的明文，避免密钥出现在终端日志中。
    _print_json("请求前原始参数", {"orderNo": order_no})
    _print_json("加密/签名后的请求参数", payload)
    _print_json("请求头", {**headers, "Client-Id": f"{client_id[:4]}***"})

    request = Request(
        ORDER_QUERY_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = response.status
            response_body = response.read().decode("utf-8")
    except HTTPError as error:
        status_code = error.code
        response_body = error.read().decode("utf-8", errors="replace")
    except URLError as error:
        raise ConnectionError(f"请求 Hipobuy 接口失败: {error.reason}") from error

    try:
        response_data: dict[str, Any] = json.loads(response_body)
    except json.JSONDecodeError:
        response_data = {"raw_response": response_body}

    _print_json("响应状态码", status_code)
    _print_json(
        "响应关键字段",
        {
            "code": response_data.get("code"),
            "data": response_data.get("data", response_data.get("result")),
            "message": response_data.get("message"),
        },
    )
    _print_json("完整响应", response_data)
    return {"status_code": status_code, **response_data}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--order-no", required=True, help="")
    parser.add_argument(
        "--client-id",
        default=os.getenv("", ""),
        help="Client-Id（默认读取）",
    )
    parser.add_argument(
        "--secret-key",
        default=os.getenv("", ""),
        help="签名密钥（默认读取 ）",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    query_order(
        order_no=args.order_no,
        client_id=args.client_id,
        secret_key=args.secret_key,
        timeout=args.timeout,
    )
