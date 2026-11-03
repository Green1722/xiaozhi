#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQTT订阅监听程序
用于监听和显示MQTT消息，支持多种主题和消息过滤

使用方法:
    python mcp_listener.py                    # 监听所有主题
    python mcp_listener.py --topic fan        # 只监听风扇主题
    python mcp_listener.py --topic light      # 只监听电灯主题
    python mcp_listener.py --topic status     # 只监听状态主题
    python mcp_listener.py --all              # 监听所有主题（默认）
    python mcp_listener.py --filter "action"  # 过滤包含特定关键词的消息
"""

import paho.mqtt.client as mqtt
import json
import time
import sys
import argparse
import signal
from datetime import datetime
from typing import Dict, List, Optional

# 修复Windows控制台UTF-8编码
if sys.platform == 'win32':
    import os
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        sys.stderr.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# MQTT配置（复用项目配置）
MQTT_BROKER = "47.97.8.221"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "mqtt-listener"

# 主题配置
TOPICS = {
    'fan': 'classroom/fan/control',
    'light': 'classroom/light/control', 
    'status': 'classroom/status',
    'all': ['classroom/fan/control', 'classroom/light/control', 'classroom/status']
}

class MQTTListener:
    def __init__(self, topics: List[str], filter_keywords: Optional[List[str]] = None):
        self.topics = topics
        self.filter_keywords = filter_keywords or []
        self.client = None
        self.connected = False
        self.message_count = 0
        
        # 安全限制配置
        self.max_messages_per_minute = 100  # 每分钟最大消息数
        self.max_messages_per_hour = 1000   # 每小时最大消息数
        self.message_timestamps = []        # 消息时间戳记录
        self.last_message_time = 0          # 最后消息时间
        self.min_message_interval = 0.1     # 最小消息间隔(秒)
        
        # 连接重试限制
        self.max_retry_attempts = 5         # 最大重试次数
        self.retry_count = 0                # 当前重试次数
        self.retry_delay = 5                # 重试延迟(秒)
        
    def on_connect(self, client, userdata, flags, rc):
        """MQTT连接回调"""
        if rc == 0:
            print(f"MQTT连接成功 - 服务器: {MQTT_BROKER}:{MQTT_PORT}")
            self.connected = True
            self.retry_count = 0  # 重置重试计数
            
            # 订阅指定主题，使用QoS 0减少服务器负担
            for topic in self.topics:
                client.subscribe(topic, qos=0)  # 改为QoS 0
                print(f"已订阅主题: {topic} (QoS 0)")
            
            print(f"\n开始监听消息... (按 Ctrl+C 停止)")
            print(f"安全限制: 每分钟最多{self.max_messages_per_minute}条消息")
            print("=" * 60)
            
        else:
            print(f"MQTT连接失败，错误代码: {rc}")
            self.connected = False
            self.retry_count += 1

    def on_disconnect(self, client, userdata, rc):
        """MQTT断开连接回调"""
        print(f"\nMQTT连接断开 (代码: {rc})")
        self.connected = False

    def _check_message_rate_limit(self) -> bool:
        """检查消息频率限制"""
        current_time = time.time()
        
        # 检查最小消息间隔
        if current_time - self.last_message_time < self.min_message_interval:
            return False
        
        # 清理旧的时间戳（超过1小时）
        self.message_timestamps = [t for t in self.message_timestamps if current_time - t < 3600]
        
        # 检查每分钟限制
        recent_messages = [t for t in self.message_timestamps if current_time - t < 60]
        if len(recent_messages) >= self.max_messages_per_minute:
            print(f"消息频率过高，已限制处理 (每分钟最多{self.max_messages_per_minute}条)")
            return False
        
        # 检查每小时限制
        if len(self.message_timestamps) >= self.max_messages_per_hour:
            print(f"消息频率过高，已限制处理 (每小时最多{self.max_messages_per_hour}条)")
            return False
        
        return True

    def on_message(self, client, userdata, msg):
        """MQTT消息接收回调"""
        try:
            # 检查消息频率限制
            if not self._check_message_rate_limit():
                return
            
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            timestamp = datetime.now().strftime('%H:%M:%S')
            current_time = time.time()
            
            # 记录消息时间戳
            self.message_timestamps.append(current_time)
            self.last_message_time = current_time
            
            # 应用关键词过滤
            if self.filter_keywords:
                if not any(keyword.lower() in payload.lower() for keyword in self.filter_keywords):
                    return
            
            self.message_count += 1
            
            # 格式化输出
            print(f"\n[{timestamp}] 消息 #{self.message_count}")
            print(f"主题: {topic}")
            
            # 尝试解析JSON
            try:
                data = json.loads(payload)
                print(f"内容 (JSON):")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                
                # 特殊处理设备控制消息
                if 'action' in data:
                    device_type = "风扇" if 'fan' in topic else "电灯" if 'light' in topic else "设备"
                    action = data['action']
                    if action == 'on':
                        if 'speed' in data:
                            print(f"操作: {device_type}开启，速度{data['speed']}档")
                        elif 'brightness' in data:
                            print(f"操作: {device_type}开启，亮度{data['brightness']}%")
                        else:
                            print(f"操作: {device_type}开启")
                    elif action == 'off':
                        print(f"操作: {device_type}关闭")
                    elif action == 'speed':
                        print(f"操作: {device_type}速度调整为{data.get('speed', 'N/A')}档")
                    elif action == 'brightness':
                        print(f"操作: {device_type}亮度调整为{data.get('brightness', 'N/A')}%")
                    else:
                        print(f"操作: {device_type} - {action}")
                        
            except json.JSONDecodeError:
                print(f"内容 (文本): {payload}")
            
            print("-" * 40)
            
        except Exception as e:
            print(f"处理消息时出错: {e}")

    def on_log(self, client, userdata, level, buf):
        """MQTT日志回调（调试用）"""
        if level == mqtt.MQTT_LOG_ERR:
            print(f"MQTT错误: {buf}")

    def start_listening(self):
        """开始监听MQTT消息"""
        try:
            # 创建MQTT客户端，添加唯一ID避免冲突
            import uuid
            unique_id = f"{MQTT_CLIENT_ID}-{uuid.uuid4().hex[:8]}"
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, unique_id)
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_message = self.on_message
            self.client.on_log = self.on_log
            
            # 设置连接参数，增加超时控制
            self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)  # 30秒心跳
            
            # 启动MQTT循环
            self.client.loop_start()
            
            # 等待连接建立，增加超时检查
            connection_timeout = 10  # 10秒连接超时
            start_time = time.time()
            while not self.connected and (time.time() - start_time) < connection_timeout:
                time.sleep(0.1)
            
            if not self.connected:
                print("连接超时，请检查网络和MQTT服务器状态")
                return False
            
            # 保持运行直到用户中断
            try:
                while True:
                    time.sleep(1)
                    
                    # 定期检查连接状态
                    if not self.connected and self.retry_count < self.max_retry_attempts:
                        print(f"尝试重新连接... ({self.retry_count}/{self.max_retry_attempts})")
                        time.sleep(self.retry_delay)
                        self.client.reconnect()
                    elif self.retry_count >= self.max_retry_attempts:
                        print("达到最大重试次数，停止连接")
                        break
                        
            except KeyboardInterrupt:
                print(f"\n\n用户中断，共接收到 {self.message_count} 条消息")
                return True
                
        except Exception as e:
            print(f"启动监听失败: {e}")
            return False
        finally:
            self.cleanup()

    def cleanup(self):
        """清理资源"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            print("MQTT连接已断开")

def signal_handler(sig, frame):
    """信号处理器"""
    print(f"\n接收到中断信号，正在停止...")
    sys.exit(0)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="MQTT订阅监听程序",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python mqtt_listener.py                    # 监听所有主题
  python mqtt_listener.py --topic fan        # 只监听风扇主题
  python mqtt_listener.py --topic light      # 只监听电灯主题
  python mqtt_listener.py --topic status     # 只监听状态主题
  python mqtt_listener.py --all              # 监听所有主题（默认）
  python mqtt_listener.py --filter "action"  # 过滤包含特定关键词的消息
  python mqtt_listener.py --filter "on off"  # 过滤包含多个关键词的消息
        """
    )
    
    parser.add_argument(
        '--topic', 
        choices=['fan', 'light', 'status'],
        help='指定要监听的主题类型'
    )
    
    parser.add_argument(
        '--all', 
        action='store_true',
        help='监听所有主题（默认行为）'
    )
    
    parser.add_argument(
        '--filter',
        type=str,
        help='过滤消息关键词，多个关键词用空格分隔'
    )
    
    parser.add_argument(
        '--max-per-minute',
        type=int,
        default=100,
        help='每分钟最大消息处理数量 (默认: 100)'
    )
    
    parser.add_argument(
        '--max-per-hour',
        type=int,
        default=1000,
        help='每小时最大消息处理数量 (默认: 1000)'
    )
    
    parser.add_argument(
        '--min-interval',
        type=float,
        default=0.1,
        help='最小消息处理间隔(秒) (默认: 0.1)'
    )
    
    args = parser.parse_args()
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    
    # 确定要监听的主题
    if args.topic:
        topics = [TOPICS[args.topic]]
        print(f"监听主题: {args.topic} ({TOPICS[args.topic]})")
    else:
        topics = TOPICS['all']
        print("监听所有主题:")
        for topic_name, topic_path in TOPICS.items():
            if topic_name != 'all':
                print(f"   - {topic_name}: {topic_path}")
    
    # 解析过滤关键词
    filter_keywords = []
    if args.filter:
        filter_keywords = args.filter.split()
        print(f"消息过滤关键词: {', '.join(filter_keywords)}")
    
    print()
    
    # 创建监听器并开始监听
    listener = MQTTListener(topics, filter_keywords)
    
    # 应用命令行参数的安全限制
    listener.max_messages_per_minute = args.max_per_minute
    listener.max_messages_per_hour = args.max_per_hour
    listener.min_message_interval = args.min_interval
    
    print(f"安全配置:")
    print(f"   - 每分钟最大消息数: {listener.max_messages_per_minute}")
    print(f"   - 每小时最大消息数: {listener.max_messages_per_hour}")
    print(f"   - 最小消息间隔: {listener.min_message_interval}秒")
    print()
    
    success = listener.start_listening()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
