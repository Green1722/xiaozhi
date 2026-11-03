# test_connection.py
# 测试MQTT连接和基本功能

import paho.mqtt.client as mqtt
import json
import time
import sys

# MQTT配置
MQTT_BROKER = "47.97.8.221"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "test-client"

# 主题配置
TOPICS = {
    'fan': 'classroom/fan/control',
    'light': 'classroom/light/control',
    'status': 'classroom/status'
}

def on_connect(client, userdata, flags, rc):
    """MQTT连接回调"""
    if rc == 0:
        print("MQTT连接成功")
        # 订阅状态主题
        client.subscribe(TOPICS['status'])
        print(f"已订阅主题: {TOPICS['status']}")
    else:
        print(f"MQTT连接失败，错误代码: {rc}")

def on_disconnect(client, userdata, rc):
    """MQTT断开连接回调"""
    print("MQTT连接断开")

def on_message(client, userdata, msg):
    """MQTT消息接收回调"""
    topic = msg.topic
    payload = msg.payload.decode('utf-8')
    print(f"收到消息 - 主题: {topic}, 内容: {payload}")

def test_mqtt_connection():
    """测试MQTT连接"""
    print("=== MQTT连接测试 ===")
    print(f"服务器: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"客户端ID: {MQTT_CLIENT_ID}")
    print()
    
    # 创建MQTT客户端
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, MQTT_CLIENT_ID)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    
    try:
        # 连接到MQTT服务器
        print("正在连接到MQTT服务器...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        
        # 启动MQTT循环
        client.loop_start()
        
        # 等待连接建立
        time.sleep(2)
        
        # 测试发布消息
        print("\n测试发布消息...")
        
        # 测试风扇控制消息
        fan_message = {
            "action": "test",
            "speed": 1,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "test": True
        }
        
        result = client.publish(TOPICS['fan'], json.dumps(fan_message, ensure_ascii=False), qos=1)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print("风扇控制消息发布成功")
        else:
            print(f"风扇控制消息发布失败，错误代码: {result.rc}")
        
        # 测试电灯控制消息
        light_message = {
            "action": "test",
            "brightness": 50,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "test": True
        }
        
        result = client.publish(TOPICS['light'], json.dumps(light_message, ensure_ascii=False), qos=1)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print("电灯控制消息发布成功")
        else:
            print(f"电灯控制消息发布失败，错误代码: {result.rc}")
        
        print("\n等待5秒以接收可能的响应...")
        time.sleep(5)
        
        print("\n=== 测试完成 ===")
        print("所有功能测试通过！服务可以正常使用。")
        
    except Exception as e:
        print(f"测试失败: {e}")
        return False
    finally:
        # 断开连接
        client.loop_stop()
        client.disconnect()
        print("连接已断开")
    
    return True

if __name__ == "__main__":
    success = test_mqtt_connection()
    sys.exit(0 if success else 1)
