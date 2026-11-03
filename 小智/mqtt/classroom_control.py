# classroom_control.py
from mcp.server.fastmcp import FastMCP
import sys
import logging
import paho.mqtt.client as mqtt
import json
import threading
import time
from typing import Dict, Any

logger = logging.getLogger('ClassroomControl')

# Fix UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import os
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        sys.stderr.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Create an MCP server
mcp = FastMCP("ClassroomControl")

# MQTT配置
MQTT_BROKER = "47.97.8.221"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "classroom-control-mcp"

# 主题配置
TOPICS = {
    'fan': 'classroom/fan/control',
    'light': 'classroom/light/control',
    'status': 'classroom/status',
    'response': 'classroom/response'
}

# 设备状态
device_status = {
    'fan': {'on': False, 'speed': 0},
    'light': {'on': False, 'brightness': 100},
    'mqtt_connected': False
}

# 响应消息存储
response_messages = []

# MQTT客户端
mqtt_client = None
mqtt_lock = threading.Lock()

def on_mqtt_connect(client, userdata, flags, rc):
    """MQTT连接回调"""
    if rc == 0:
        logger.info("MQTT连接成功")
        device_status['mqtt_connected'] = True
        # 订阅状态主题和响应主题
        client.subscribe(TOPICS['status'])
        client.subscribe(TOPICS['response'])
        logger.info(f"已订阅主题: {TOPICS['status']}, {TOPICS['response']}")
    else:
        logger.error(f"MQTT连接失败，错误代码: {rc}")
        device_status['mqtt_connected'] = False

def on_mqtt_disconnect(client, userdata, rc):
    """MQTT断开连接回调"""
    logger.warning("MQTT连接断开")
    device_status['mqtt_connected'] = False

def on_mqtt_message(client, userdata, msg):
    """MQTT消息接收回调"""
    try:
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        logger.info(f"收到消息 - 主题: {topic}, 内容: {payload}")
        
        # 处理状态更新消息
        if topic == TOPICS['status']:
            try:
                status_data = json.loads(payload)
                # 更新设备状态
                if 'fan' in status_data:
                    device_status['fan'].update(status_data['fan'])
                if 'light' in status_data:
                    device_status['light'].update(status_data['light'])
            except json.JSONDecodeError:
                logger.warning(f"无法解析状态消息: {payload}")
        
        # 处理响应消息
        elif topic == TOPICS['response']:
            try:
                response_data = json.loads(payload)
                # 添加时间戳
                response_data['received_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
                # 存储响应消息（最多保留100条）
                response_messages.append(response_data)
                if len(response_messages) > 100:
                    response_messages.pop(0)
                logger.info(f"收到响应消息: {response_data}")
            except json.JSONDecodeError:
                logger.warning(f"无法解析响应消息: {payload}")
                # 即使无法解析JSON，也存储原始消息
                response_messages.append({
                    'raw_message': payload,
                    'received_at': time.strftime('%Y-%m-%d %H:%M:%S')
                })
                if len(response_messages) > 100:
                    response_messages.pop(0)
    except Exception as e:
        logger.error(f"处理MQTT消息时出错: {e}")

def init_mqtt():
    """初始化MQTT连接"""
    global mqtt_client
    
    try:
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, MQTT_CLIENT_ID)
        mqtt_client.on_connect = on_mqtt_connect
        mqtt_client.on_disconnect = on_mqtt_disconnect
        mqtt_client.on_message = on_mqtt_message
        
        logger.info(f"正在连接到MQTT服务器: {MQTT_BROKER}:{MQTT_PORT}")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        
        # 启动MQTT循环
        mqtt_client.loop_start()
        
        # 等待连接建立
        time.sleep(1)
        
        return True
    except Exception as e:
        logger.error(f"MQTT初始化失败: {e}")
        return False

def publish_mqtt_message(topic: str, message: Dict[str, Any]) -> bool:
    """发布MQTT消息"""
    global mqtt_client
    
    if not mqtt_client or not device_status['mqtt_connected']:
        logger.error("MQTT客户端未连接")
        return False
    
    try:
        payload = json.dumps(message, ensure_ascii=False)
        result = mqtt_client.publish(topic, payload, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"消息已发布到主题 {topic}: {payload}")
            return True
        else:
            logger.error(f"发布消息失败，错误代码: {result.rc}")
            return False
    except Exception as e:
        logger.error(f"发布MQTT消息时出错: {e}")
        return False

# 风扇控制工具
@mcp.tool()
def control_fan(action: str, speed: int = None) -> dict:
    """控制教室风扇的开关和速度
    
    Args:
        action: 风扇操作 ('on', 'off', 'speed')
        speed: 风扇速度档位 (0-3档，仅在action为'speed'或'on'时有效)
    
    Returns:
        操作结果字典
    """
    try:
        message = {
            'action': action,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        if action == 'on':
            if speed is None:
                speed = 1  # 默认1档
            if speed < 0 or speed > 3:
                return {"success": False, "error": "风扇速度必须在0-3档之间"}
            
            device_status['fan']['on'] = True
            device_status['fan']['speed'] = speed
            message['speed'] = speed
            
        elif action == 'off':
            device_status['fan']['on'] = False
            device_status['fan']['speed'] = 0
            message['speed'] = 0
            
        elif action == 'speed':
            if speed is None:
                return {"success": False, "error": "调整速度时必须指定speed参数"}
            if speed < 0 or speed > 3:
                return {"success": False, "error": "风扇速度必须在0-3档之间"}
            
            device_status['fan']['speed'] = speed
            device_status['fan']['on'] = speed > 0
            message['speed'] = speed
            
        else:
            return {"success": False, "error": "无效的风扇操作，支持的操作: on, off, speed"}
        
        # 发布MQTT消息
        success = publish_mqtt_message(TOPICS['fan'], message)
        
        if success:
            action_desc = {
                'on': f'已开启，设置为{speed}档',
                'off': '已关闭',
                'speed': f'速度已调整为{speed}档'
            }
            
            return {
                "success": True,
                "device": "fan",
                "action": action,
                "current_state": device_status['fan'].copy(),
                "message": f"风扇{action_desc[action]}"
            }
        else:
            return {"success": False, "error": "MQTT消息发布失败"}
            
    except Exception as e:
        logger.error(f"风扇控制失败: {e}")
        return {"success": False, "error": str(e)}

# 电灯控制工具
@mcp.tool()
def control_light(action: str, brightness: int = None) -> dict:
    """控制教室电灯的开关和亮度
    
    Args:
        action: 电灯操作 ('on', 'off', 'brightness')
        brightness: 电灯亮度百分比 (0-100%，仅在action为'brightness'或'on'时有效)
    
    Returns:
        操作结果字典
    """
    try:
        message = {
            'action': action,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        if action == 'on':
            if brightness is None:
                brightness = 100  # 默认100%亮度
            if brightness < 0 or brightness > 100:
                return {"success": False, "error": "亮度必须在0-100%之间"}
            
            device_status['light']['on'] = True
            device_status['light']['brightness'] = brightness
            message['brightness'] = brightness
            
        elif action == 'off':
            device_status['light']['on'] = False
            device_status['light']['brightness'] = 0
            message['brightness'] = 0
            
        elif action == 'brightness':
            if brightness is None:
                return {"success": False, "error": "调整亮度时必须指定brightness参数"}
            if brightness < 0 or brightness > 100:
                return {"success": False, "error": "亮度必须在0-100%之间"}
            
            device_status['light']['brightness'] = brightness
            device_status['light']['on'] = brightness > 0
            message['brightness'] = brightness
            
        else:
            return {"success": False, "error": "无效的电灯操作，支持的操作: on, off, brightness"}
        
        # 发布MQTT消息
        success = publish_mqtt_message(TOPICS['light'], message)
        
        if success:
            action_desc = {
                'on': f'已开启，亮度设置为{brightness}%',
                'off': '已关闭',
                'brightness': f'亮度已调整为{brightness}%'
            }
            
            return {
                "success": True,
                "device": "light",
                "action": action,
                "current_state": device_status['light'].copy(),
                "message": f"电灯{action_desc[action]}"
            }
        else:
            return {"success": False, "error": "MQTT消息发布失败"}
            
    except Exception as e:
        logger.error(f"电灯控制失败: {e}")
        return {"success": False, "error": str(e)}

# 获取设备状态工具
@mcp.tool()
def get_device_status() -> dict:
    """获取所有设备的当前状态
    
    Returns:
        设备状态字典
    """
    try:
        return {
            "success": True,
            "devices": {
                "fan": device_status['fan'].copy(),
                "light": device_status['light'].copy()
            },
            "mqtt_connected": device_status['mqtt_connected'],
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        logger.error(f"获取设备状态失败: {e}")
        return {"success": False, "error": str(e)}

# 获取响应消息工具
@mcp.tool()
def get_response_messages(limit: int = 10) -> dict:
    """获取最近收到的响应消息
    
    Args:
        limit: 返回的消息数量限制，默认为10条
    
    Returns:
        响应消息列表
    """
    try:
        # 获取最近的响应消息
        recent_messages = response_messages[-limit:] if limit > 0 else response_messages
        
        return {
            "success": True,
            "messages": recent_messages,
            "total_count": len(response_messages),
            "returned_count": len(recent_messages),
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        logger.error(f"获取响应消息失败: {e}")
        return {"success": False, "error": str(e)}

# 清空响应消息工具
@mcp.tool()
def clear_response_messages() -> dict:
    """清空所有存储的响应消息
    
    Returns:
        操作结果
    """
    try:
        global response_messages
        cleared_count = len(response_messages)
        response_messages = []
        
        return {
            "success": True,
            "message": f"已清空 {cleared_count} 条响应消息",
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        logger.error(f"清空响应消息失败: {e}")
        return {"success": False, "error": str(e)}

# 批量控制工具
@mcp.tool()
def control_multiple_devices(commands: list) -> dict:
    """批量控制多个设备
    
    Args:
        commands: 命令列表，每个命令包含device, action, value字段
    
    Returns:
        批量操作结果
    """
    try:
        results = []
        
        for command in commands:
            device = command.get('device')
            action = command.get('action')
            value = command.get('value')
            
            if device == 'fan':
                result = control_fan(action, value)
            elif device == 'light':
                result = control_light(action, value)
            else:
                result = {
                    "success": False,
                    "device": device,
                    "error": "不支持的设备类型"
                }
            
            results.append(result)
        
        return {
            "success": True,
            "results": results,
            "total_commands": len(commands),
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
    except Exception as e:
        logger.error(f"批量控制失败: {e}")
        return {"success": False, "error": str(e)}

# 启动服务器
if __name__ == "__main__":
    # 初始化MQTT连接
    if init_mqtt():
        logger.info("教室控制MCP服务已启动")
        logger.info(f"MQTT服务器: {MQTT_BROKER}:{MQTT_PORT}")
        logger.info("可用工具: control_fan, control_light, get_device_status, control_multiple_devices, get_response_messages, clear_response_messages")
        logger.info(f"监听主题: {', '.join(TOPICS.values())}")
    else:
        logger.error("MQTT初始化失败，服务启动中止")
        sys.exit(1)
    
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("服务被用户中断")
    finally:
        # 清理MQTT连接
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
            logger.info("MQTT连接已断开")
