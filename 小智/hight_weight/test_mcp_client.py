import asyncio
import json
import os
import sys

# Windows 平台环境兼容
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

async def test_mcp():
    print("🚀 启动本地 MCP 测试...")
    try:
        # 启动 MCP 服务进程
        process = await asyncio.create_subprocess_exec(
            sys.executable, "zhudong_mcp/physical_exam_control.py",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=sys.stderr  # 让标准错误直接打印到控制台
        )
        
        async def send_msg(msg_dict):
            msg = json.dumps(msg_dict)
            process.stdin.write((msg + "\n").encode('utf-8'))
            await process.stdin.drain()
            
        async def read_resp():
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                resp = json.loads(line.decode('utf-8'))
                return resp
                
        # 1. 模拟客户端发送 Initialize 请求
        await send_msg({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        })
        print("📨 发送: Initialize")
        init_resp = await read_resp()
        print(f"📥 收到: {json.dumps(init_resp, ensure_ascii=False, indent=2)}\n")
        
        # 发送 initialized 通知
        await send_msg({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })

        # 2. 获取可用工具列表
        await send_msg({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        })
        print("📨 发送: 获取工具列表")
        tools_resp = await read_resp()
        print(f"📥 可用工具: {json.dumps(tools_resp, ensure_ascii=False, indent=2)}\n")

        # 3. 模拟调用 process_physical_exam 工具
        print("📨 发送: 模拟调用 process_physical_exam 工具 (身高175, 体重70)")
        await send_msg({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "process_physical_exam",
                "arguments": {
                    "height_cm": 175.0,
                    "weight_kg": 70.0
                }
            }
        })
        call_resp = await read_resp()
        print(f"📥 调用结果: {json.dumps(call_resp, ensure_ascii=False, indent=2)}\n")

    except Exception as e:
        print(f"测试出错: {e}")
    finally:
        if 'process' in locals():
            process.terminate()
            print("🛑 测试结束，已关闭服务。")

if __name__ == "__main__":
    asyncio.run(test_mcp())