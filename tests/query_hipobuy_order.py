#!/usr/bin/env python3
"""Query a HipoBuy order and print the complete request/response details.

Run from the repository root:
    python tests/query_hipobuy_order.py

Use the timestamp from an API example when a reproducible request is needed:
    python tests/query_hipobuy_order.py --timestamp 1785208920448
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import time
from typing import Any
from urllib.parse import urlsplit


URL = "xxxxxx"
CLIENT_ID = "xxx"
ORDER_NO = "xxx"
SECRET_KEY = ""


def build_payload(order_no: str, timestamp: int) -> tuple[dict[str, Any], str]:
    """Build the signed JSON payload and return the pre-signature string."""
    raw_signature = f"{timestamp}{SECRET_KEY}"
    signature = hashlib.md5(raw_signature.encode("utf-8")).hexdigest().upper()
    return (
        {
            "orderNo": order_no,
            "timestamp": timestamp,
            "signature": signature,
        },
        raw_signature,
    )


def query_order(payload: dict[str, Any], raw_signature: str) -> None:
    """POST the payload and print its input, HTTP status, and response body."""
    request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    parsed_url = urlsplit(URL)
    request_path = parsed_url.path or "/"
    if parsed_url.query:
        request_path = f"{request_path}?{parsed_url.query}"
    headers = {
        "Client-Id": CLIENT_ID,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    print("请求 URL:", URL)
    print("请求方法: POST")
    print("请求头:", json.dumps(headers, ensure_ascii=False))
    print("签名前拼接字符串:", raw_signature)
    print("签名结果:", payload["signature"])
    print("请求入参:", json.dumps(payload, ensure_ascii=False))

    connection = http.client.HTTPSConnection(parsed_url.netloc, timeout=30)
    try:
        connection.request("POST", request_path, body=request_body, headers=headers)
        response = connection.getresponse()
        body = response.read().decode("utf-8", errors="replace")
        print("响应状态码:", response.status)
        print("响应内容:", body)
    except OSError as error:
        print("请求失败:", error)
    finally:
        connection.close()


def main() -> None:
    """Generate a millisecond timestamp, sign the request, and query the API."""
    parser = argparse.ArgumentParser(description="Query a HipoBuy order.")
    parser.add_argument(
        "--timestamp",
        type=int,
        help="Optional millisecond timestamp; defaults to the current time.",
    )
    args = parser.parse_args()
    timestamp = args.timestamp if args.timestamp is not None else int(time.time() * 1000)
    payload, raw_signature = build_payload(ORDER_NO, timestamp)
    query_order(payload, raw_signature)


if __name__ == "__main__":
    main()
