#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试 classroom_control.py 的响应功能
直接发送响应消息到 classroom/response 主题
"""

import paho.mqtt.client as mqtt
import json
import time
import sys

# MQTT配置
MQTT_BROKER = "47.97.8.221"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "response-test-sender"

# 主题配置
RESPONSE_TOPIC = 'classroom/response'

def send_response_message():
    """发送测试响应消息"""
    try:
        print("🔗 连接到MQTT服务器...")
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, MQTT_CLIENT_ID)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        
        # 发送测试响应消息
        test_responses = [
            {
                "type": "fan_response",
                "action": "on",
                "speed": 2,
                "status": "success",
                "message": "风扇已开启，速度设置为2档",
                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                "request_id": "test_fan_001"
            },
            {
                "type": "light_response", 
                "action": "brightness",
                "brightness": 75,
                "status": "success",
                "message": "电灯亮度已调整为75%",
                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                "request_id": "test_light_001"
            },
            {
                "type": "status_response",
                "devices": {
                    "fan": {"on": True, "speed": 2},
                    "light": {"on": True, "brightness": 75}
                },
                "status": "success",
                "message": "设备状态查询完成",
                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                "request_id": "test_status_001"
            }
        ]
        
        print(f"📡 发送测试响应消息到主题: {RESPONSE_TOPIC}")
        
        for i, response in enumerate(test_responses, 1):
            payload = json.dumps(response, ensure_ascii=False)
            result = client.publish(RESPONSE_TOPIC, payload, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"✅ 响应消息 {i} 发送成功")
                print(f"   内容: {payload[:100]}...")
            else:
                print(f"❌ 响应消息 {i} 发送失败，错误代码: {result.rc}")
            
            time.sleep(1)  # 间隔1秒
        
        client.disconnect()
        print("🔌 连接已断开")
        
        print(f"\n📋 测试完成！")
        print(f"   已发送 {len(test_responses)} 条响应消息到 {RESPONSE_TOPIC}")
        print(f"   如果 classroom_control.py 正在运行并正确订阅了该主题，")
        print(f"   应该能在其日志中看到这些消息。")
        
        return True
        
    except Exception as e:
        print(f"❌ 发送响应消息时出错: {e}")
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("🧪 测试 classroom/response 主题消息发送")
    print("=" * 60)
    
    success = send_response_message()
    
    if success:
        print("\n✅ 测试完成！请检查 classroom_control.py 的日志输出")
        print("   如果看到 '收到响应消息' 的日志，说明功能正常")
    else:
        print("\n❌ 测试失败！")

if __name__ == "__main__":
    main()

