#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 classroom_control.py 是否能收到 classroom/response 信息
"""

import paho.mqtt.client as mqtt
import json
import time
import sys
import threading
import subprocess
import os

# MQTT配置
MQTT_BROKER = "47.97.8.221"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "test-response-client"

# 主题配置
TOPICS = {
    'fan': 'classroom/fan/control',
    'light': 'classroom/light/control',
    'status': 'classroom/status',
    'response': 'classroom/response'
}

class ResponseTester:
    def __init__(self):
        self.client = None
        self.connected = False
        self.response_received = False
        self.response_messages = []
        
    def on_connect(self, client, userdata, flags, rc):
        """MQTT连接回调"""
        if rc == 0:
            print("✅ MQTT连接成功")
            self.connected = True
            # 订阅响应主题
            client.subscribe(TOPICS['response'])
            print(f"📡 已订阅响应主题: {TOPICS['response']}")
        else:
            print(f"❌ MQTT连接失败，错误代码: {rc}")
            self.connected = False

    def on_disconnect(self, client, userdata, rc):
        """MQTT断开连接回调"""
        print("🔌 MQTT连接断开")
        self.connected = False

    def on_message(self, client, userdata, msg):
        """MQTT消息接收回调"""
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        timestamp = time.strftime('%H:%M:%S')
        
        print(f"\n📨 [{timestamp}] 收到响应消息:")
        print(f"   主题: {topic}")
        print(f"   内容: {payload}")
        
        # 尝试解析JSON
        try:
            data = json.loads(payload)
            print(f"   JSON解析: {json.dumps(data, indent=2, ensure_ascii=False)}")
        except json.JSONDecodeError:
            print(f"   原始文本: {payload}")
        
        self.response_received = True
        self.response_messages.append({
            'topic': topic,
            'payload': payload,
            'timestamp': timestamp
        })
        
        print("-" * 50)

    def start_listening(self):
        """开始监听响应消息"""
        try:
            # 创建MQTT客户端
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, MQTT_CLIENT_ID)
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_message = self.on_message
            
            print(f"🔗 正在连接到MQTT服务器: {MQTT_BROKER}:{MQTT_PORT}")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            
            # 启动MQTT循环
            self.client.loop_start()
            
            # 等待连接建立
            time.sleep(2)
            
            if not self.connected:
                print("❌ 连接失败")
                return False
                
            return True
            
        except Exception as e:
            print(f"❌ 启动监听失败: {e}")
            return False

    def cleanup(self):
        """清理资源"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            print("🔌 MQTT连接已断开")

def send_test_message(topic, message):
    """发送测试消息"""
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "test-sender")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        
        payload = json.dumps(message, ensure_ascii=False)
        result = client.publish(topic, payload, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"✅ 测试消息已发送到 {topic}")
            print(f"   内容: {payload}")
        else:
            print(f"❌ 发送消息失败，错误代码: {result.rc}")
            
        client.disconnect()
        return result.rc == mqtt.MQTT_ERR_SUCCESS
        
    except Exception as e:
        print(f"❌ 发送消息时出错: {e}")
        return False

def test_classroom_control_response():
    """测试 classroom_control.py 的响应功能"""
    print("=" * 60)
    print("🧪 测试 classroom_control.py 响应功能")
    print("=" * 60)
    
    # 创建响应监听器
    tester = ResponseTester()
    
    try:
        # 启动监听
        if not tester.start_listening():
            print("❌ 无法启动响应监听")
            return False
            
        print("\n📋 测试步骤:")
        print("1. 发送风扇控制消息")
        print("2. 发送电灯控制消息") 
        print("3. 等待响应消息")
        print("4. 检查是否收到响应")
        
        # 测试1: 发送风扇控制消息
        print(f"\n🔧 测试1: 发送风扇控制消息")
        fan_message = {
            "action": "on",
            "speed": 2,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "test": True,
            "request_id": "test_fan_001"
        }
        
        if send_test_message(TOPICS['fan'], fan_message):
            print("⏳ 等待响应消息...")
            time.sleep(3)
        
        # 测试2: 发送电灯控制消息
        print(f"\n💡 测试2: 发送电灯控制消息")
        light_message = {
            "action": "brightness",
            "brightness": 75,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "test": True,
            "request_id": "test_light_001"
        }
        
        if send_test_message(TOPICS['light'], light_message):
            print("⏳ 等待响应消息...")
            time.sleep(3)
        
        # 测试3: 发送状态查询消息
        print(f"\n📊 测试3: 发送状态查询消息")
        status_message = {
            "action": "query",
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "test": True,
            "request_id": "test_status_001"
        }
        
        if send_test_message(TOPICS['status'], status_message):
            print("⏳ 等待响应消息...")
            time.sleep(3)
        
        # 检查结果
        print(f"\n📊 测试结果:")
        print(f"   收到响应消息数量: {len(tester.response_messages)}")
        
        if tester.response_received:
            print("✅ 成功！classroom_control.py 能够收到 classroom/response 信息")
            print("\n📨 收到的响应消息:")
            for i, msg in enumerate(tester.response_messages, 1):
                print(f"   {i}. [{msg['timestamp']}] {msg['payload']}")
        else:
            print("❌ 失败！未收到任何响应消息")
            print("\n🔍 可能的原因:")
            print("   1. classroom_control.py 服务未运行")
            print("   2. classroom_control.py 未正确订阅 classroom/response 主题")
            print("   3. 硬件设备未发送响应消息")
            print("   4. 网络连接问题")
            
        return tester.response_received
        
    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        return False
        
    finally:
        tester.cleanup()

def check_classroom_control_running():
    """检查 classroom_control.py 是否在运行"""
    print("\n🔍 检查 classroom_control.py 服务状态...")
    
    try:
        # 检查是否有Python进程在运行classroom_control.py
        result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python.exe'], 
                              capture_output=True, text=True, shell=True)
        
        if 'python.exe' in result.stdout:
            print("✅ 发现Python进程正在运行")
            # 进一步检查是否包含classroom_control
            if 'classroom_control' in result.stdout:
                print("✅ classroom_control.py 可能正在运行")
                return True
            else:
                print("⚠️  Python进程运行中，但不确定是否包含classroom_control.py")
                return False
        else:
            print("❌ 未发现Python进程运行")
            return False
            
    except Exception as e:
        print(f"⚠️  无法检查进程状态: {e}")
        return False

def main():
    """主函数"""
    print("🚀 开始测试 classroom_control.py 响应功能")
    
    # 检查服务状态
    if not check_classroom_control_running():
        print("\n⚠️  建议:")
        print("   1. 确保 classroom_control.py 正在运行")
        print("   2. 可以通过以下命令启动:")
        print("      python classroom_control.py")
        print("   3. 或者通过 MCP 管道启动:")
        print("      python mcp_pipe.py classroom-control")
        
        response = input("\n是否继续测试? (y/n): ")
        if response.lower() != 'y':
            print("测试已取消")
            return
    
    # 执行测试
    success = test_classroom_control_response()
    
    print(f"\n{'='*60}")
    if success:
        print("🎉 测试通过！classroom_control.py 能够正常接收响应消息")
    else:
        print("❌ 测试失败！需要检查配置和服务状态")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()

