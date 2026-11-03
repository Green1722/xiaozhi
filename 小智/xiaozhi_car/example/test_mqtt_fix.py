#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQTT通信测试脚本
用于测试ESP32设备是否能正确接收和响应MQTT消息
"""

import paho.mqtt.client as mqtt
import json
import time
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

# MQTT配置
MQTT_BROKER = "47.97.8.221"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "mqtt-test-client"

# 主题配置
TOPICS = {
    'fan': 'classroom/fan/control',
    'light': 'classroom/light/control',
    'status': 'classroom/status',
    'response': 'classroom/response'
}

class MQTTTester:
    def __init__(self):
        self.client = None
        self.connected = False
        self.responses_received = []
        
    def on_connect(self, client, userdata, flags, rc):
        """MQTT连接回调"""
        if rc == 0:
            print(f"✅ MQTT连接成功 - 服务器: {MQTT_BROKER}:{MQTT_PORT}")
            self.connected = True
            
            # 订阅状态和响应主题
            client.subscribe(TOPICS['status'])
            client.subscribe(TOPICS['response'])
            print(f"✅ 已订阅主题: {TOPICS['status']}, {TOPICS['response']}")
            
        else:
            print(f"❌ MQTT连接失败，错误代码: {rc}")
            self.connected = False

    def on_disconnect(self, client, userdata, rc):
        """MQTT断开连接回调"""
        print(f"❌ MQTT连接断开 (代码: {rc})")
        self.connected = False

    def on_message(self, client, userdata, msg):
        """MQTT消息接收回调"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            timestamp = datetime.now().strftime('%H:%M:%S')
            
            print(f"\n[{timestamp}] 📥 收到消息")
            print(f"主题: {topic}")
            
            # 尝试解析JSON
            try:
                data = json.loads(payload)
                print(f"内容 (JSON):")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                
                # 记录响应消息
                if topic == TOPICS['response']:
                    self.responses_received.append({
                        'timestamp': timestamp,
                        'data': data
                    })
                    print("✅ 收到ESP32设备响应！")
                    
            except json.JSONDecodeError:
                print(f"内容 (文本): {payload}")
            
            print("-" * 40)
            
        except Exception as e:
            print(f"❌ 处理消息时出错: {e}")

    def send_test_message(self, device_type, action, **kwargs):
        """发送测试消息"""
        if not self.connected:
            print("❌ MQTT未连接，无法发送消息")
            return False
        
        topic = TOPICS[device_type]
        message = {
            'action': action,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # 添加额外参数
        message.update(kwargs)
        
        try:
            payload = json.dumps(message, ensure_ascii=False)
            result = self.client.publish(topic, payload, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"📤 已发送{device_type}控制消息到 {topic}")
                print(f"内容: {payload}")
                return True
            else:
                print(f"❌ 发送消息失败，错误代码: {result.rc}")
                return False
        except Exception as e:
            print(f"❌ 发送消息时出错: {e}")
            return False

    def start_test(self):
        """开始测试"""
        try:
            # 创建MQTT客户端
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, MQTT_CLIENT_ID)
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_message = self.on_message
            
            print(f"正在连接到MQTT服务器: {MQTT_BROKER}:{MQTT_PORT}")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            
            # 启动MQTT循环
            self.client.loop_start()
            
            # 等待连接建立
            time.sleep(2)
            
            if not self.connected:
                print("❌ 连接超时，请检查网络和MQTT服务器状态")
                return False
            
            print("\n" + "="*60)
            print("🧪 开始MQTT通信测试")
            print("="*60)
            
            # 测试1: 风扇控制
            print("\n🔧 测试1: 风扇控制")
            self.send_test_message('fan', 'on', speed=2)
            time.sleep(3)  # 等待响应
            
            self.send_test_message('fan', 'off')
            time.sleep(3)  # 等待响应
            
            # 测试2: 电灯控制
            print("\n💡 测试2: 电灯控制")
            self.send_test_message('light', 'on', brightness=80)
            time.sleep(3)  # 等待响应
            
            self.send_test_message('light', 'off')
            time.sleep(3)  # 等待响应
            
            # 测试结果
            print("\n" + "="*60)
            print("📊 测试结果")
            print("="*60)
            print(f"发送的测试消息: 4条")
            print(f"收到的响应消息: {len(self.responses_received)}条")
            
            if self.responses_received:
                print("\n✅ ESP32设备响应详情:")
                for i, resp in enumerate(self.responses_received, 1):
                    print(f"  {i}. [{resp['timestamp']}] 设备ID: {resp['data'].get('device_id', 'N/A')}")
                    print(f"     状态: {resp['data'].get('status', 'N/A')}")
                    print(f"     消息: {resp['data'].get('message', 'N/A')}")
            else:
                print("\n❌ 未收到ESP32设备响应")
                print("可能的原因:")
                print("  1. ESP32设备未连接到MQTT服务器")
                print("  2. ESP32设备未订阅正确的主题")
                print("  3. ESP32设备代码需要重新上传")
                print("  4. 网络连接问题")
            
            return len(self.responses_received) > 0
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
        finally:
            self.cleanup()

    def cleanup(self):
        """清理资源"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            print("\n🔌 MQTT连接已断开")

def main():
    """主函数"""
    print("🧪 MQTT通信测试工具")
    print("用于测试ESP32设备是否能正确接收和响应MQTT消息")
    print()
    
    tester = MQTTTester()
    success = tester.start_test()
    
    if success:
        print("\n✅ 测试通过！ESP32设备通信正常")
        sys.exit(0)
    else:
        print("\n❌ 测试失败！请检查ESP32设备配置")
        sys.exit(1)

if __name__ == "__main__":
    main()

