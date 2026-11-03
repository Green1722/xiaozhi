import os
from dotenv import load_dotenv

from mcp_server_wechat_sse.WechatServer import WeChatServer

# 加载环境变量
load_dotenv()

# 默认配置（可通过环境变量覆盖）
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 3000
DEFAULT_FOLDER_PATH = "C://Users//Administrator//Documents//mcp_wechat_history"

async def serve(default_folder_path=None, host=None, port=None):
    """启动微信MCP服务器（SSE模式）"""
    # 优先使用环境变量配置
    host = host or os.environ.get("MCP_HOST", DEFAULT_HOST)
    port = port or int(os.environ.get("MCP_PORT", DEFAULT_PORT))
    default_folder_path = default_folder_path or os.environ.get("MCP_FOLDER_PATH", DEFAULT_FOLDER_PATH)
    
    server = WeChatServer(default_folder_path=default_folder_path, host=host, port=port)
    await server.serve()

def main():
    """提供微信交互功能的MCP服务器"""
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(
        description="给模型提供微信聊天记录获取和消息发送功能的MCP服务器（SSE模式）"
    )
    parser.add_argument("--folder-path", default=None,
                        help="默认保存聊天记录的文件夹路径（环境变量：MCP_FOLDER_PATH）")
    parser.add_argument("--host", default=None,
                        help="SSE服务器监听地址（环境变量：MCP_HOST，默认：0.0.0.0）")
    parser.add_argument("--port", type=int, default=None,
                        help="SSE服务器监听端口（环境变量：MCP_PORT，默认：3000）")
    args = parser.parse_args()

    asyncio.run(serve(
        default_folder_path=args.folder_path,
        host=args.host,
        port=args.port
    ))

if __name__ == "__main__":
    main()
