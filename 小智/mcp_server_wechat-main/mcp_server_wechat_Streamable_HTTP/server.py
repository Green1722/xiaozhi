import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any, Optional

import anyio
import click
from dotenv import load_dotenv
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

# 加载环境变量
load_dotenv()

from .WechatClient import WeChatClient

# 默认配置（可通过环境变量覆盖）
DEFAULT_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.environ.get("MCP_PORT", 3000))
DEFAULT_FOLDER_PATH = os.environ.get("MCP_FOLDER_PATH", "C://Users//Administrator//Documents//mcp_wechat_history")
DEFAULT_LOG_LEVEL = os.environ.get("MCP_LOG_LEVEL", "INFO")


@click.command()
@click.option("--host", default=DEFAULT_HOST, help="HTTP 服务监听地址（环境变量：MCP_HOST）")
@click.option("--port", default=DEFAULT_PORT, help="HTTP 服务监听端口（环境变量：MCP_PORT）")
@click.option(
    "--folder-path",
    default=DEFAULT_FOLDER_PATH,
    help="默认保存聊天记录的文件夹路径（环境变量：MCP_FOLDER_PATH）",
)
@click.option(
    "--log-level",
    default=DEFAULT_LOG_LEVEL,
    help="日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)（环境变量：MCP_LOG_LEVEL）",
)
@click.option(
    "--json-response",
    is_flag=True,
    default=False,
    help="启用 JSON 响应模式（禁用 SSE 流式推送）",
)
def main(host: str, port: int, folder_path: Optional[str], log_level: str, json_response: bool) -> int:
    """运行微信 MCP 服务器（Streamable HTTP 传输）"""

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger("wechat-mcp-server")

    wechat_client = WeChatClient(default_folder_path=folder_path)

    app = Server("mcp-streamable-http-wechat")

    @app.list_resources()
    async def handle_list_resources():
        return [
            {
                "uri": "wechat://chats/history",
                "name": "微信聊天记录",
                "description": "获取微信聊天记录",
                "mimeType": "application/json",
            }
        ]

    @app.read_resource()
    async def handle_read_resource(uri: str):
        if uri.startswith("wechat://"):
            return [
                types.TextResourceContents(
                    uri=uri,
                    mimeType="application/json",
                    text=json.dumps({"message": "请使用工具接口获取微信聊天记录"}, ensure_ascii=False)
                )
            ]
        raise ValueError(f"不支持的URI: {uri}")

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        """列出可用的微信工具"""
        return [
            types.Tool(
                name="wechat_get_chat_history",
                description="获取特定日期的微信聊天记录",
                inputSchema={
                    "type": "object",
                    "required": ["to_user", "target_date"],
                    "properties": {
                        "to_user": {
                            "type": "string",
                            "description": "好友或群聊备注或昵称",
                        },
                        "target_date": {
                            "type": "string",
                            "description": "目标日期，格式为 YY/M/D，如 '25/3/22'",
                        },
                    },
                },
            ),
            types.Tool(
                name="wechat_send_message",
                description="向单个微信好友发送单条消息",
                inputSchema={
                    "type": "object",
                    "required": ["to_user", "message"],
                    "properties": {
                        "to_user": {
                            "type": "string",
                            "description": "好友或群聊备注或昵称",
                        },
                        "message": {
                            "type": "string",
                            "description": "要发送的消息",
                        },
                    },
                },
            ),
            types.Tool(
                name="wechat_send_multiple_messages",
                description="向单个微信好友发送多条消息",
                inputSchema={
                    "type": "object",
                    "required": ["to_user", "messages"],
                    "properties": {
                        "to_user": {
                            "type": "string",
                            "description": "好友或群聊备注或昵称",
                        },
                        "messages": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要发送的消息列表",
                        },
                    },
                },
            ),
            types.Tool(
                name="wechat_send_to_multiple_friends",
                description="向多个微信好友发送单条或多条消息",
                inputSchema={
                    "type": "object",
                    "required": ["to_user", "message"],
                    "properties": {
                        "to_user": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "好友或群聊备注或昵称列表",
                        },
                        "message": {
                            "type": "string",
                            "description": "要发送的消息（单条消息会群发；用逗号分隔的多条消息将分别发送）",
                        },
                    },
                },
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        """处理工具调用请求"""
        ctx = app.request_context

        try:
            if name == "wechat_get_chat_history":
                friend = arguments.get("to_user")
                target_date = arguments.get("target_date")
                if not friend or not target_date:
                    raise ValueError("缺少必要参数: to_user 或 target_date")

                await ctx.session.send_log_message(
                    level="info",
                    data=f"开始获取与 {friend} 在 {target_date} 的聊天记录...",
                    logger="wechat",
                    related_request_id=ctx.request_id,
                )

                async def progress_callback(message: str):
                    await ctx.session.send_log_message(
                        level="info",
                        data=message,
                        logger="wechat",
                        related_request_id=ctx.request_id,
                    )

                try:
                    folder_path = arguments.get("folder_path")
                    search_pages = arguments.get("search_pages", 5)
                    scroll_delay = arguments.get("scroll_delay", 0.01)

                    chat_history = await wechat_client.get_chat_history_by_date(
                        friend=friend,
                        target_date=target_date,
                        folder_path=folder_path,
                        search_pages=search_pages,
                        scroll_delay=scroll_delay,
                        progress_callback=progress_callback,
                    )

                    records = json.loads(chat_history)

                    await ctx.session.send_log_message(
                        level="info",
                        data=f"✅ 成功获取 {len(records)} 条聊天记录！",
                        logger="wechat",
                        related_request_id=ctx.request_id,
                    )

                    if not records:
                        output = f"未找到与 {friend} 在 {target_date} 的聊天记录"
                    else:
                        output = f"获取到 {len(records)} 条与 {friend} 在 {target_date} 的聊天记录\n\n"
                        for record in records:
                            output += f"发送者: {record['发送者']}\n"
                            output += f"时间: {record['时间']}\n"
                            output += f"消息: {record['消息']}\n"
                            output += "-" * 30 + "\n"

                    return [types.TextContent(type="text", text=output)]

                except Exception as err:
                    await ctx.session.send_log_message(
                        level="error",
                        data=f"获取聊天记录失败: {str(err)}",
                        logger="wechat",
                        related_request_id=ctx.request_id,
                    )
                    raise

            elif name == "wechat_send_message":
                friend = arguments.get("to_user")
                message = arguments.get("message")
                delay = arguments.get("delay", 1.0)
                if not friend or not message:
                    raise ValueError("缺少必要参数: to_user 或 message")

                await ctx.session.send_log_message(
                    level="info",
                    data=f"准备向 {friend} 发送消息...",
                    logger="wechat",
                    related_request_id=ctx.request_id,
                )

                async def progress_callback(msg: str):
                    await ctx.session.send_log_message(
                        level="info",
                        data=msg,
                        logger="wechat",
                        related_request_id=ctx.request_id,
                    )

                try:
                    search_pages = arguments.get("search_pages", 0)
                    result = await wechat_client.send_message_to_friend(
                        friend=friend,
                        message=message,
                        search_pages=search_pages,
                        delay=delay,
                        progress_callback=progress_callback,
                    )

                    await ctx.session.send_log_message(
                        level="info",
                        data="消息发送完成！",
                        logger="wechat",
                        related_request_id=ctx.request_id,
                    )

                    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

                except Exception as err:
                    await ctx.session.send_log_message(
                        level="error",
                        data=f"发送消息失败: {str(err)}",
                        logger="wechat",
                        related_request_id=ctx.request_id,
                    )
                    raise

            elif name == "wechat_send_multiple_messages":
                friend = arguments.get("to_user")
                messages = arguments.get("messages")
                delay = arguments.get("delay", 1.0)

                if not friend or not messages:
                    raise ValueError("缺少必要参数: to_user 或 messages")

                if isinstance(messages, str):
                    try:
                        messages = json.loads(messages)
                    except json.JSONDecodeError:
                        for separator in ['，', '；', ';', '\n']:
                            messages = messages.replace(separator, ',')
                        messages = [msg.strip() for msg in messages.split(',')]
                        messages = [msg for msg in messages if msg]

                if not isinstance(messages, list):
                    messages = [messages]

                await ctx.session.send_log_message(
                    level="info",
                    data=f"准备向 {friend} 发送 {len(messages)} 条消息...",
                    logger="wechat",
                    related_request_id=ctx.request_id,
                )

                async def progress_callback(msg: str):
                    await ctx.session.send_log_message(
                        level="info",
                        data=msg,
                        logger="wechat",
                        related_request_id=ctx.request_id,
                    )

                try:
                    search_pages = arguments.get("search_pages", 0)
                    result = await wechat_client.send_messages_to_friend(
                        friend=friend,
                        messages=messages,
                        search_pages=search_pages,
                        delay=delay,
                        progress_callback=progress_callback,
                    )

                    await ctx.session.send_log_message(
                        level="info",
                        data="所有消息发送完成！",
                        logger="wechat",
                        related_request_id=ctx.request_id,
                    )

                    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

                except Exception as err:
                    await ctx.session.send_log_message(
                        level="error",
                        data=f"发送消息失败: {str(err)}",
                        logger="wechat",
                        related_request_id=ctx.request_id,
                    )
                    raise

            elif name == "wechat_send_to_multiple_friends":
                friends = arguments.get("to_user")
                message = arguments.get("message")
                delay = arguments.get("delay", 1.0)

                if not friends or not message:
                    raise ValueError("缺少必要参数: to_user 或 message")

                if isinstance(friends, str):
                    try:
                        friends = json.loads(friends)
                    except json.JSONDecodeError:
                        friends = [f.strip() for f in friends.split(',')]

                if not isinstance(friends, list):
                    friends = [friends]

                if isinstance(message, str):
                    if message.count('","') > 0 and message.count('","') == (len(friends) - 1):
                        try:
                            parsed_messages = json.loads(f'[{message}]')
                            messages = parsed_messages
                        except json.JSONDecodeError:
                            messages = []
                            msg_parts = message.split('","')
                            for i, part in enumerate(msg_parts):
                                if i == 0 and part.startswith('"'):
                                    part = part[1:]
                                if i == len(msg_parts) - 1 and part.endswith('"'):
                                    part = part[:-1]
                                messages.append(part)
                    else:
                        messages = [message] * len(friends)
                elif isinstance(message, list):
                    messages = message
                else:
                    messages = [str(message)] * len(friends)

                if len(messages) < len(friends):
                    last_message = messages[-1] if messages else ""
                    messages.extend([last_message] * (len(friends) - len(messages)))
                elif len(messages) > len(friends):
                    messages = messages[:len(friends)]

                await ctx.session.send_log_message(
                    level="info",
                    data=f"准备向 {len(friends)} 位好友发送消息...",
                    logger="wechat",
                    related_request_id=ctx.request_id,
                )

                async def progress_callback(msg: str):
                    await ctx.session.send_log_message(
                        level="info",
                        data=msg,
                        logger="wechat",
                        related_request_id=ctx.request_id,
                    )

                try:
                    result = await wechat_client.send_message_to_friends(
                        friends=friends,
                        message=messages,
                        delay=delay,
                        progress_callback=progress_callback,
                    )

                    await ctx.session.send_log_message(
                        level="info",
                        data="所有消息发送完成！",
                        logger="wechat",
                        related_request_id=ctx.request_id,
                    )

                    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

                except Exception as err:
                    await ctx.session.send_log_message(
                        level="error",
                        data=f"发送消息失败: {str(err)}",
                        logger="wechat",
                        related_request_id=ctx.request_id,
                    )
                    raise

            return [types.TextContent(type="text", text=f"不支持的工具: {name}")]

        except Exception as e:
            logger.error(f"工具调用错误: {e}", exc_info=True)
            raise

    session_manager = StreamableHTTPSessionManager(
        app=app,
        event_store=None,
        json_response=json_response,
        stateless=True,
    )

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        """处理 HTTP 请求"""
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(starlette_app: Starlette) -> AsyncIterator[None]:
        """应用生命周期管理"""
        async with session_manager.run():
            logger.info("微信 MCP 服务器已启动！")
            logger.info(f"监听端口: {port}")
            logger.info(f"聊天记录保存路径: {folder_path or '未设置'}")
            try:
                yield
            finally:
                logger.info("微信 MCP 服务器正在关闭...")

    starlette_app = Starlette(
        debug=False,
        routes=[Mount("/mcp", app=handle_streamable_http)],
        lifespan=lifespan,
    )

    import uvicorn

    uvicorn.run(starlette_app, host=host, port=port)

    return 0


if __name__ == "__main__":
    main()

