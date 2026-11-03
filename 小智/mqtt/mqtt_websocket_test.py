#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQTT WebSocket连接诊断脚本
用于测试微信小程序使用的WebSocket MQTT连接
"""

import asyncio
import websockets
import json
import sys
from datetime import datetime

# 修复Windows控制台UTF-8编码
if sys.platform == 'win32':
    import os
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        sys.stderr.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# 配置
WS_URL = "ws://124.222.47.162:8084/mqtt"
USERNAME = "admin"
PASSWORD = "REPLACE_ME"

def create_mqtt_connect_packet():
    """创建MQTT CONNECT数据包的字节"""
    # 这是一个简化的MQTT CONNECT包
    # 实际的MQTT协议很复杂，这里只是为了测试WebSocket连接
    client_id = "test-client"
    protocol_name = "MQTT"
    protocol_version = 4  # MQTT 3.1.1

    # CONNECT包结构 (简化版)
    packet = bytearray()

    # Fixed header: CONNECT packet type (1) + flags (0)
    packet.append(0x10)  # CONNECT packet

    # Remaining length (可变长度编码，这里简化)
    packet.append(0x00)  # 简化长度

    # 实际的MQTT包需要更多的字节，这里只是测试WebSocket连接
    return packet

async def test_websocket_connection():
    """测试WebSocket连接"""
    print(f"🔍 测试WebSocket连接到: {WS_URL}")
    print("=" * 60)

    try:
        async with websockets.connect(WS_URL) as websocket:
            print("✅ WebSocket连接成功!")

            # 发送MQTT CONNECT数据包 (简化测试)
            connect_packet = create_mqtt_connect_packet()
            await websocket.send(connect_packet)
            print("📤 已发送MQTT CONNECT包")

            # 等待响应
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"📥 收到响应: {response}")
            except asyncio.TimeoutError:
                print("⏰ 等待响应超时")

            # 保持连接一小段时间
            await asyncio.sleep(2)

    except websockets.exceptions.ConnectionClosedError as e:
        print(f"❌ WebSocket连接被关闭: {e}")
    except websockets.exceptions.InvalidURI as e:
        print(f"❌ 无效的URI: {e}")
    except websockets.exceptions.InvalidHandshake as e:
        print(f"❌ WebSocket握手失败: {e}")
    except Exception as e:
        print(f"❌ 连接失败: {e}")

async def test_http_connection():
    """测试基础HTTP连接"""
    import aiohttp

    http_url = "http://124.222.47.162:8084/mqtt"
    print(f"\n🌐 测试HTTP连接到: {http_url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(http_url) as response:
                print(f"✅ HTTP响应状态: {response.status}")
                if response.status == 200:
                    text = await response.text()
                    print(f"📄 响应内容 (前200字符): {text[:200]}...")
                else:
                    print(f"❌ HTTP请求失败，状态码: {response.status}")

    except Exception as e:
        print(f"❌ HTTP连接失败: {e}")

def main():
    """主函数"""
    print("🔧 MQTT WebSocket连接诊断工具")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 测试WebSocket连接
    asyncio.run(test_websocket_connection())

    # 测试HTTP连接
    try:
        asyncio.run(test_http_connection())
    except ImportError:
        print("\n⚠️  需要安装aiohttp才能测试HTTP连接")
        print("   pip install aiohttp")

if __name__ == "__main__":
    main()

