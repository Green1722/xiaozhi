#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQTT诊断脚本
用于检查MQTT服务器状态和ESP32设备连接情况
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

def check_mqtt_server():
    """检查MQTT服务器状态"""
    print("🔍 检查MQTT服务器状态...")
    
    try:
        # 创建测试客户端
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "diagnostic-client")
        
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print(f"✅ MQTT服务器连接成功: {MQTT_BROKER}:{MQTT_PORT}")
            else:
                print(f"❌ MQTT服务器连接失败，错误代码: {rc}")
        
        def on_disconnect(client, userdata, rc):
            print(f"🔌 MQTT连接断开 (代码: {rc})")
        
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        
        # 尝试连接
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        
        # 等待连接结果
        time.sleep(2)
        
        # 断开连接
        client.loop_stop()
        client.disconnect()
        
        return True
        
    except Exception as e:
        print(f"❌ MQTT服务器检查失败: {e}")
        return False

def monitor_all_topics():
    """监控所有相关主题"""
    print("\n📡 开始监控所有MQTT主题...")
    print("监听主题:")
    print("  - classroom/fan/control")
    print("  - classroom/light/control") 
    print("  - classroom/status")
    print("  - classroom/response")
    print("\n按 Ctrl+C 停止监控")
    print("="*60)
    
    topics = [
        'classroom/fan/control',
        'classroom/light/control',
        'classroom/status',
        'classroom/response'
    ]
    
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "monitor-client")
        
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print("✅ 监控客户端连接成功")
                for topic in topics:
                    client.subscribe(topic)
                    print(f"✅ 已订阅: {topic}")
            else:
                print(f"❌ 监控客户端连接失败: {rc}")
        
        def on_message(client, userdata, msg):
            timestamp = datetime.now().strftime('%H:%M:%S')
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            print(f"\n[{timestamp}] 📥 收到消息")
            print(f"主题: {topic}")
            
            try:
                data = json.loads(payload)
                print(f"内容: {json.dumps(data, indent=2, ensure_ascii=False)}")
            except:
                print(f"内容: {payload}")
            
            print("-" * 40)
        
        client.on_connect = on_connect
        client.on_message = on_message
        
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        
        # 保持运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n🛑 用户中断监控")
        
        client.loop_stop()
        client.disconnect()
        
    except Exception as e:
        print(f"❌ 监控失败: {e}")

def send_test_message():
    """发送测试消息"""
    print("\n🧪 发送测试消息...")
    
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "test-sender")
        
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print("✅ 测试发送客户端连接成功")
                
                # 发送测试消息
                test_message = {
                    'action': 'test',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'message': 'This is a test message'
                }
                
                topic = 'classroom/fan/control'
                payload = json.dumps(test_message, ensure_ascii=False)
                
                result = client.publish(topic, payload, qos=1)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    print(f"📤 测试消息已发送到 {topic}")
                    print(f"内容: {payload}")
                else:
                    print(f"❌ 发送失败，错误代码: {result.rc}")
            else:
                print(f"❌ 测试发送客户端连接失败: {rc}")
        
        client.on_connect = on_connect
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        
        time.sleep(2)
        
        client.loop_stop()
        client.disconnect()
        
    except Exception as e:
        print(f"❌ 发送测试消息失败: {e}")

def main():
    """主函数"""
    print("🔧 MQTT诊断工具")
    print("="*60)
    
    # 1. 检查MQTT服务器
    server_ok = check_mqtt_server()
    
    if not server_ok:
        print("\n❌ MQTT服务器不可用，请检查网络连接和服务器状态")
        return
    
    # 2. 发送测试消息
    send_test_message()
    
    # 3. 监控主题
    monitor_all_topics()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 诊断工具已退出")
    except Exception as e:
        print(f"\n❌ 诊断工具出错: {e}")

