#!/usr/bin/env python
"""
Gmail API 集成的配置脚本。

此脚本通过以下步骤完成 Gmail API 的 OAuth 授权：
1. 如不存在则创建 .secrets 目录
2. 使用 .secrets/secrets.json 中的凭据进行认证
3. 打开浏览器窗口供用户授权
4. 将访问令牌存储到 .secrets/token.json
"""

import os
import sys
import json
from pathlib import Path

# 将项目根目录加入 sys.path，确保导入正常工作
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../")))

# 导入所需的 Google 库
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

def main():
    """执行 Gmail 身份验证配置。"""
    # 创建 .secrets 目录
    secrets_dir = Path(__file__).parent.absolute() / ".secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    
    # 检查 secrets.json 是否存在
    secrets_path = secrets_dir / "secrets.json"
    if not secrets_path.exists():
        print(f"错误：未找到客户端密钥文件：{secrets_path}")
        print("请从 Google Cloud Console 下载 OAuth 客户端 ID JSON 文件")
        print("并将其保存为 .secrets/secrets.json")
        return 1
    
    print("正在启动 Gmail API 身份验证流程……")
    print("将打开浏览器窗口，请在其中授权访问。")
    
    # 这会触发 OAuth 流程并创建 token.json
    try:
        # 定义所需的权限范围
        SCOPES = [
            'https://www.googleapis.com/auth/gmail.modify',
            'https://www.googleapis.com/auth/calendar'
        ]
        
        # 加载客户端密钥
        with open(secrets_path, 'r') as f:
            client_config = json.load(f)
        
        # 使用 client_secrets.json 格式创建流程
        flow = InstalledAppFlow.from_client_secrets_file(
            str(secrets_path),
            SCOPES
        )
        
        # 运行 OAuth 流程
        credentials = flow.run_local_server(port=0)
        
        # 将凭据保存至 token.json
        token_path = secrets_dir / "token.json"
        token_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes,
            'universe_domain': 'googleapis.com',
            'account': '',
            'expiry': credentials.expiry.isoformat() + "Z"
        }
        
        with open(token_path, 'w') as token_file:
            json.dump(token_data, token_file)
            
        print("\n身份验证成功！")
        print(f"访问令牌已保存至：{token_path}")
        return 0
    except Exception as e:
        print(f"身份验证失败：{str(e)}")
        return 1

if __name__ == "__main__":
    exit(main())
