# car_control.py - 小车控制MCP服务 (精简版)
# 支持：普通遥控模式（字符串/JSON指令）+ 跟随模式
from mcp.server.fastmcp import FastMCP
import sys
import logging
import paho.mqtt.client as mqtt
import json
import threading
import time
import math
from typing import Dict, Any, Optional, Union

logger = logging.getLogger('CarControl')

# ==================== 默认参数配置 ====================
DEFAULT_LINEAR = 0.3        # 默认线速度 (m/s)
DEFAULT_ANGULAR = 0.6       # 默认角速度 (rad/s)
SPEED_SLOW_FACTOR = 0.5     # 慢速倍数
SPEED_FAST_FACTOR = 1.5     # 快速倍数
DURATION_SHORT_SEC = 2.0    # 短时长 (秒)
DURATION_MEDIUM_SEC = 5.0   # 中时长 (秒)
ROTATE_DEFAULT_DEG = 90.0   # 默认旋转角度 (度)
ANGLE_COMPENSATION = 1.23   # 角度补偿系数

# 速度档位配置
SPEED_GEARS = {
    'speed_slow': {'linear': DEFAULT_LINEAR * SPEED_SLOW_FACTOR, 'angular': DEFAULT_ANGULAR * SPEED_SLOW_FACTOR},
    'speed_medium': {'linear': DEFAULT_LINEAR, 'angular': DEFAULT_ANGULAR},
    'speed_fast': {'linear': DEFAULT_LINEAR * SPEED_FAST_FACTOR, 'angular': DEFAULT_ANGULAR * SPEED_FAST_FACTOR}
}

# 持续时间档位配置
DURATION_GEARS = {
    'duration_short': DURATION_SHORT_SEC,
    'duration_medium': DURATION_MEDIUM_SEC,
    'duration_infinite': 0  # 0表示无限持续
}

# Fix UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import os
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        sys.stderr.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Create MCP server
mcp = FastMCP("CarControl")

# ==================== MQTT配置 ====================
MQTT_BROKER = "47.97.8.221"
MQTT_PORT = 1883
MQTT_CLIENT_ID = f"car-control-mcp-{int(time.time())}"

TOPICS = {
    'command': 'yahboomcar/cmd',
    'status': 'yahboomcar/status',
    'response': 'yahboomcar/response'
}

# ==================== 全局状态 ====================
car_state = {
    # 运动状态
    'moving': False,
    'linear_x': 0.0,
    'linear_y': 0.0,
    'angular_z': 0.0,
    # MQTT状态
    'mqtt_connected': False,
    # 档位设置
    'speed_gear': 'speed_medium',
    'linear_speed': DEFAULT_LINEAR,
    'angular_speed': DEFAULT_ANGULAR,
    'duration_gear': 'duration_short',
    'duration': DURATION_SHORT_SEC,
    # 跟随模式
    'follow_mode': False
}

mqtt_client = None
mqtt_lock = threading.Lock()
response_messages = []

# ==================== 指令队列系统 ====================
command_queue = []  # 指令队列
queue_lock = threading.Lock()
queue_thread = None
queue_running = False
current_command_end_time = 0  # 当前指令结束时间戳

# ==================== MQTT回调函数 ====================
def on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("MQTT连接成功")
        car_state['mqtt_connected'] = True
        client.subscribe(TOPICS['status'], qos=1)
        client.subscribe(TOPICS['response'], qos=1)
    else:
        logger.error(f"MQTT连接失败，代码: {rc}")
        car_state['mqtt_connected'] = False

def on_mqtt_disconnect(client, userdata, rc):
    logger.warning(f"MQTT断开连接，代码: {rc}")
    car_state['mqtt_connected'] = False
    if rc != 0:
        try:
            client.reconnect()
        except Exception as e:
            logger.error(f"重连失败: {e}")

def on_mqtt_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
        logger.info(f"收到消息 [{msg.topic}]: {payload}")
        
        if msg.topic == TOPICS['response']:
            try:
                data = json.loads(payload)
                data['received_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            except json.JSONDecodeError:
                data = {'raw': payload, 'received_at': time.strftime('%Y-%m-%d %H:%M:%S')}
            response_messages.append(data)
            if len(response_messages) > 100:
                response_messages.pop(0)
    except Exception as e:
        logger.error(f"处理消息出错: {e}")

def init_mqtt():
    global mqtt_client
    try:
        mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID, protocol=mqtt.MQTTv311)
        mqtt_client.on_connect = on_mqtt_connect
        mqtt_client.on_disconnect = on_mqtt_disconnect
        mqtt_client.on_message = on_mqtt_message
        mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
        
        logger.info(f"连接MQTT: {MQTT_BROKER}:{MQTT_PORT}")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)
        mqtt_client.loop_start()
        
        # 等待连接
        for _ in range(50):
            if car_state['mqtt_connected']:
                return True
            time.sleep(0.1)
        return False
    except Exception as e:
        logger.error(f"MQTT初始化失败: {e}")
        return False

def publish_command(message: Union[Dict, str]) -> bool:
    """发布MQTT命令"""
    if not mqtt_client or not car_state['mqtt_connected']:
        logger.error("MQTT未连接")
        return False
    try:
        payload = json.dumps(message, ensure_ascii=False) if isinstance(message, dict) else message
        result = mqtt_client.publish(TOPICS['command'], payload, qos=1)
        logger.info(f"发送命令: {payload}")
        return result.rc == mqtt.MQTT_ERR_SUCCESS
    except Exception as e:
        logger.error(f"发送失败: {e}")
        return False

# ==================== 指令队列处理 ====================
def queue_processor():
    """指令队列处理线程"""
    global current_command_end_time, queue_running
    
    while queue_running:
        cmd_to_execute = None
        
        with queue_lock:
            # 检查当前指令是否已结束
            current_time = time.time()
            if current_command_end_time > 0 and current_time < current_command_end_time:
                # 当前指令还在执行，等待
                pass
            elif command_queue:
                # 取出下一条指令
                cmd_to_execute = command_queue.pop(0)
                logger.info(f"队列取出指令，剩余 {len(command_queue)} 条")
        
        if cmd_to_execute:
            # 执行指令
            cmd_type = cmd_to_execute.get('_type')
            cmd_data = cmd_to_execute.get('_data')
            duration = cmd_to_execute.get('_duration', 0)
            
            if cmd_type == 'json':
                _execute_json_command_internal(cmd_data)
            elif cmd_type == 'string':
                _execute_string_command_internal(cmd_data)
            
            # 设置当前指令结束时间
            if duration > 0:
                current_command_end_time = time.time() + duration
                logger.info(f"指令将在 {duration:.1f} 秒后结束")
            else:
                current_command_end_time = 0
        
        time.sleep(0.05)  # 50ms检查间隔

def start_queue_processor():
    """启动指令队列处理线程"""
    global queue_thread, queue_running
    if queue_thread is None or not queue_thread.is_alive():
        queue_running = True
        queue_thread = threading.Thread(target=queue_processor, daemon=True)
        queue_thread.start()
        logger.info("指令队列处理线程已启动")

def stop_queue_processor():
    """停止指令队列处理线程"""
    global queue_running
    queue_running = False

def add_to_queue(cmd_type: str, cmd_data: Any, duration: float = 0) -> int:
    """添加指令到队列
    
    Args:
        cmd_type: 指令类型 ('json' 或 'string')
        cmd_data: 指令数据
        duration: 指令持续时间(秒)
    
    Returns:
        队列中的位置
    """
    with queue_lock:
        command_queue.append({
            '_type': cmd_type,
            '_data': cmd_data,
            '_duration': duration,
            '_added_at': time.time()
        })
        position = len(command_queue)
        logger.info(f"指令已加入队列，位置: {position}")
        return position

def clear_queue() -> int:
    """清空指令队列
    
    Returns:
        被清除的指令数量
    """
    global current_command_end_time
    with queue_lock:
        count = len(command_queue)
        command_queue.clear()
        current_command_end_time = 0
        logger.info(f"队列已清空，清除 {count} 条指令")
        return count

def get_queue_status() -> dict:
    """获取队列状态"""
    with queue_lock:
        remaining_time = max(0, current_command_end_time - time.time()) if current_command_end_time > 0 else 0
        return {
            'queue_length': len(command_queue),
            'current_command_remaining': round(remaining_time, 2),
            'commands': [{'type': c['_type'], 'duration': c['_duration']} for c in command_queue]
        }

# ==================== 核心控制函数 ====================
def calculate_rotate_duration(angular_z: float, rotate_deg: float) -> float:
    """根据角速度和角度计算旋转持续时间"""
    rotate_rad = abs(rotate_deg) * math.pi / 180.0
    return (rotate_rad / abs(angular_z)) * ANGLE_COMPENSATION

def _execute_json_command_internal(cmd: Dict[str, Any]) -> dict:
    """内部执行JSON格式指令（直接发送，不经过队列）"""
    try:
        # 处理action字段（跟随模式）
        action = cmd.get('action')
        if action:
            if action == 'follow':
                car_state['follow_mode'] = True
                publish_command({'action': 'follow'})
                return {"success": True, "action": "follow", "message": "开启跟随模式"}
            elif action in ['stop_follow', 'stop']:
                car_state['follow_mode'] = False
                car_state['moving'] = False
                publish_command({'action': 'stop'})
                return {"success": True, "action": action, "message": "停止跟随/运动"}
        
        # 处理stop字段
        if cmd.get('stop') is True:
            car_state['moving'] = False
            car_state['linear_x'] = 0.0
            car_state['linear_y'] = 0.0
            car_state['angular_z'] = 0.0
            publish_command({'stop': True})
            return {"success": True, "message": "急停"}
        
        # 提取运动参数
        linear_x = cmd.get('linear_x', 0.0)
        linear_y = cmd.get('linear_y', 0.0)
        angular_z = cmd.get('angular_z', 0.0)
        duration = cmd.get('duration', 0.0)
        rotate_deg = cmd.get('rotate_deg')
        
        # 如果指定了rotate_deg且duration<=0，自动计算持续时间
        if rotate_deg is not None and angular_z != 0 and duration <= 0:
            duration = calculate_rotate_duration(angular_z, rotate_deg)
        
        # 构建MQTT消息
        mqtt_msg = {
            'linear_x': linear_x,
            'linear_y': linear_y,
            'angular_z': angular_z,
            'duration': duration
        }
        
        # 更新状态
        car_state['moving'] = (linear_x != 0 or linear_y != 0 or angular_z != 0)
        car_state['linear_x'] = linear_x
        car_state['linear_y'] = linear_y
        car_state['angular_z'] = angular_z
        
        success = publish_command(mqtt_msg)
        
        # 生成描述
        desc_parts = []
        if linear_x > 0: desc_parts.append(f"前进{linear_x:.2f}m/s")
        elif linear_x < 0: desc_parts.append(f"后退{abs(linear_x):.2f}m/s")
        if linear_y > 0: desc_parts.append(f"左移{linear_y:.2f}m/s")
        elif linear_y < 0: desc_parts.append(f"右移{abs(linear_y):.2f}m/s")
        if angular_z > 0: desc_parts.append(f"左转{angular_z:.2f}rad/s")
        elif angular_z < 0: desc_parts.append(f"右转{abs(angular_z):.2f}rad/s")
        
        desc = " + ".join(desc_parts) if desc_parts else "停止"
        if duration > 0:
            desc += f"，持续{duration:.1f}秒"
        elif rotate_deg:
            desc += f"，旋转{rotate_deg}度"
        
        return {"success": success, "command": mqtt_msg, "description": desc, "duration": duration}
        
    except Exception as e:
        logger.error(f"执行JSON指令失败: {e}")
        return {"success": False, "error": str(e)}

def _execute_string_command_internal(cmd: str) -> dict:
    """内部执行字符串格式指令（直接发送，不经过队列）"""
    cmd = cmd.strip().lower()
    
    # 速度档位
    if cmd in SPEED_GEARS:
        car_state['speed_gear'] = cmd
        car_state['linear_speed'] = SPEED_GEARS[cmd]['linear']
        car_state['angular_speed'] = SPEED_GEARS[cmd]['angular']
        return {
            "success": True, 
            "gear": cmd,
            "linear_speed": car_state['linear_speed'],
            "angular_speed": car_state['angular_speed'],
            "message": f"速度档位: {cmd}"
        }
    
    # 持续时间档位
    if cmd in DURATION_GEARS:
        car_state['duration_gear'] = cmd
        car_state['duration'] = DURATION_GEARS[cmd]
        dur_desc = "无限" if car_state['duration'] == 0 else f"{car_state['duration']}秒"
        return {"success": True, "gear": cmd, "duration": car_state['duration'], "message": f"持续时间: {dur_desc}"}
    
    # 获取当前档位参数
    linear = car_state['linear_speed']
    angular = car_state['angular_speed']
    duration = car_state['duration']
    
    # 基础运动指令
    cmd_map = {
        'forward': {'linear_x': linear, 'duration': duration},
        'back': {'linear_x': -linear, 'duration': duration},
        'strafe_left': {'linear_y': linear, 'duration': duration},
        'strafe_right': {'linear_y': -linear, 'duration': duration},
        'rotate_left': {'angular_z': angular, 'rotate_deg': ROTATE_DEFAULT_DEG},
        'rotate_right': {'angular_z': -angular, 'rotate_deg': ROTATE_DEFAULT_DEG},
        'stop': {'stop': True}
    }
    
    if cmd in cmd_map:
        return _execute_json_command_internal(cmd_map[cmd])
    
    return {"success": False, "error": f"未知命令: {cmd}"}

def _get_command_duration(cmd: Union[Dict, str]) -> float:
    """获取指令的持续时间"""
    if isinstance(cmd, dict):
        duration = cmd.get('duration', 0.0)
        rotate_deg = cmd.get('rotate_deg')
        angular_z = cmd.get('angular_z', 0.0)
        
        # 如果有旋转角度，计算持续时间
        if rotate_deg is not None and angular_z != 0 and duration <= 0:
            duration = calculate_rotate_duration(angular_z, rotate_deg)
        return duration
    elif isinstance(cmd, str):
        cmd = cmd.strip().lower()
        # 档位设置指令没有持续时间
        if cmd in SPEED_GEARS or cmd in DURATION_GEARS:
            return 0
        # stop指令没有持续时间
        if cmd == 'stop':
            return 0
        # 其他运动指令使用当前档位的持续时间
        if cmd in ['forward', 'back', 'strafe_left', 'strafe_right']:
            return car_state['duration']
        # 旋转指令计算持续时间
        if cmd in ['rotate_left', 'rotate_right']:
            return calculate_rotate_duration(car_state['angular_speed'], ROTATE_DEFAULT_DEG)
    return 0

def execute_json_command(cmd: Dict[str, Any], use_queue: bool = True) -> dict:
    """执行JSON格式指令
    
    Args:
        cmd: JSON指令
        use_queue: 是否使用队列（默认True）
    """
    # stop和action指令立即执行，不进队列
    if cmd.get('stop') is True or cmd.get('action'):
        # 清空队列并立即执行
        if cmd.get('stop') is True:
            clear_queue()
        return _execute_json_command_internal(cmd)
    
    if use_queue:
        duration = _get_command_duration(cmd)
        position = add_to_queue('json', cmd, duration)
        return {
            "success": True, 
            "queued": True, 
            "position": position,
            "duration": duration,
            "message": f"指令已加入队列，位置: {position}"
        }
    else:
        return _execute_json_command_internal(cmd)

def execute_string_command(cmd: str, use_queue: bool = True) -> dict:
    """执行字符串格式指令
    
    Args:
        cmd: 字符串指令
        use_queue: 是否使用队列（默认True）
    """
    cmd_lower = cmd.strip().lower()
    
    # 档位设置和stop指令立即执行
    if cmd_lower in SPEED_GEARS or cmd_lower in DURATION_GEARS:
        return _execute_string_command_internal(cmd)
    
    if cmd_lower == 'stop':
        clear_queue()
        return _execute_string_command_internal(cmd)
    
    if use_queue:
        duration = _get_command_duration(cmd)
        position = add_to_queue('string', cmd, duration)
        return {
            "success": True,
            "queued": True,
            "position": position,
            "duration": duration,
            "message": f"指令已加入队列，位置: {position}"
        }
    else:
        return _execute_string_command_internal(cmd)


# ==================== MCP工具定义 ====================

@mcp.tool()
def control(command: str) -> dict:
    """统一控制接口 - 支持字符串指令和JSON指令
    
    【字符串指令】简洁，适合手动测试：
    - 直线/平移/旋转/停止：forward, back, strafe_left, strafe_right, rotate_left, rotate_right, stop
    - 速度档位：speed_slow, speed_medium, speed_fast
    - 持续时间档位：duration_short(2s), duration_medium(5s), duration_infinite(需手动stop)
    
    【JSON指令】灵活，可组合参数：
    {
        "linear_x": 0.3,      // 前后速度(m/s)，+前进，-后退
        "linear_y": 0.0,      // 平移速度(m/s)，+左移，-右移
        "angular_z": 0.6,     // 角速度(rad/s)，+左转，-右转
        "duration": 2.0,      // 持续时间(秒)，0=持续运行
        "rotate_deg": 90,     // 旋转角度(度)，自动计算时长
        "stop": false,        // true=急停
        "action": "follow"    // 跟随模式：follow/stop_follow/stop
    }
    
    【跟随模式】
    - 开启：{"action": "follow"}
    - 停止：{"action": "stop_follow"} 或 {"action": "stop"}
    
    Args:
        command: 字符串指令或JSON字符串
    
    Returns:
        操作结果
    """
    try:
        # 尝试解析为JSON
        if command.strip().startswith('{'):
            try:
                cmd_dict = json.loads(command)
                return execute_json_command(cmd_dict)
            except json.JSONDecodeError:
                return {"success": False, "error": "JSON格式错误"}
        else:
            # 字符串指令
            return execute_string_command(command)
    except Exception as e:
        logger.error(f"控制指令执行失败: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def move(linear_x: float = 0.0, linear_y: float = 0.0, angular_z: float = 0.0, 
         duration: float = 0.0, rotate_deg: float = None) -> dict:
    """精确运动控制
    
    Args:
        linear_x: 前后速度(m/s)，正=前进，负=后退，范围[-0.6, 0.6]
        linear_y: 平移速度(m/s)，正=左移，负=右移，范围[-0.6, 0.6]
        angular_z: 角速度(rad/s)，正=左转，负=右转，范围[-1.5, 1.5]
        duration: 持续时间(秒)，0=持续运行直到stop
        rotate_deg: 旋转角度(度)，指定后自动计算duration
    
    Returns:
        操作结果
    """
    cmd = {
        'linear_x': linear_x,
        'linear_y': linear_y,
        'angular_z': angular_z,
        'duration': duration
    }
    if rotate_deg is not None:
        cmd['rotate_deg'] = rotate_deg
    return execute_json_command(cmd)


@mcp.tool()
def stop() -> dict:
    """急停 - 立即停止所有运动"""
    return execute_json_command({'stop': True})


@mcp.tool()
def follow(enable: bool = True) -> dict:
    """跟随模式控制
    
    Args:
        enable: True=开启跟随，False=停止跟随
    
    Returns:
        操作结果
    """
    action = 'follow' if enable else 'stop_follow'
    return execute_json_command({'action': action})


@mcp.tool()
def set_gear(speed: str = None, duration: str = None) -> dict:
    """设置速度/持续时间档位
    
    Args:
        speed: 速度档位 - speed_slow/speed_medium/speed_fast
        duration: 持续时间档位 - duration_short(2s)/duration_medium(5s)/duration_infinite
    
    Returns:
        当前档位设置
    """
    result = {"success": True}
    
    if speed:
        if speed in SPEED_GEARS:
            car_state['speed_gear'] = speed
            car_state['linear_speed'] = SPEED_GEARS[speed]['linear']
            car_state['angular_speed'] = SPEED_GEARS[speed]['angular']
            result['speed_gear'] = speed
        else:
            return {"success": False, "error": f"无效速度档位: {speed}"}
    
    if duration:
        if duration in DURATION_GEARS:
            car_state['duration_gear'] = duration
            car_state['duration'] = DURATION_GEARS[duration]
            result['duration_gear'] = duration
        else:
            return {"success": False, "error": f"无效持续时间档位: {duration}"}
    
    result['current'] = {
        'speed_gear': car_state['speed_gear'],
        'linear_speed': car_state['linear_speed'],
        'angular_speed': car_state['angular_speed'],
        'duration_gear': car_state['duration_gear'],
        'duration': car_state['duration']
    }
    return result


@mcp.tool()
def status() -> dict:
    """获取小车当前状态"""
    return {
        "success": True,
        "state": car_state.copy(),
        "mqtt_connected": car_state['mqtt_connected'],
        "follow_mode": car_state['follow_mode'],
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
    }


@mcp.tool()
def get_responses(limit: int = 10) -> dict:
    """获取最近的响应消息
    
    Args:
        limit: 返回消息数量限制
    
    Returns:
        响应消息列表
    """
    msgs = response_messages[-limit:] if limit > 0 else response_messages
    return {
        "success": True,
        "messages": msgs,
        "total": len(response_messages),
        "returned": len(msgs)
    }


@mcp.tool()
def sequence(commands: str) -> dict:
    """执行指令序列 - 多条指令按顺序执行，每条指令等待上一条完成后再发送
    
    指令之间用逗号、分号或换行分隔。每条指令会在上一条指令的持续时间结束后才发送。
    
    Args:
        commands: 指令序列，支持字符串指令和JSON指令混合
                  例如: "forward, rotate_left, back"
                  或: "forward; {\"linear_x\": 0.5, \"duration\": 3}; rotate_right"
    
    Returns:
        队列状态和添加的指令信息
    """
    import re
    
    # 分割指令（支持逗号、分号、换行）
    cmd_list = re.split(r'[,;\n]+', commands)
    cmd_list = [c.strip() for c in cmd_list if c.strip()]
    
    if not cmd_list:
        return {"success": False, "error": "没有有效指令"}
    
    results = []
    total_duration = 0
    
    for cmd in cmd_list:
        # 判断是JSON还是字符串指令
        if cmd.startswith('{'):
            try:
                cmd_dict = json.loads(cmd)
                duration = _get_command_duration(cmd_dict)
                position = add_to_queue('json', cmd_dict, duration)
                results.append({
                    "command": cmd,
                    "type": "json",
                    "position": position,
                    "duration": duration
                })
                total_duration += duration
            except json.JSONDecodeError:
                results.append({"command": cmd, "error": "JSON格式错误"})
        else:
            duration = _get_command_duration(cmd)
            position = add_to_queue('string', cmd, duration)
            results.append({
                "command": cmd,
                "type": "string",
                "position": position,
                "duration": duration
            })
            total_duration += duration
    
    return {
        "success": True,
        "commands_added": len(results),
        "total_duration": round(total_duration, 2),
        "details": results,
        "queue_status": get_queue_status()
    }


@mcp.tool()
def queue_status() -> dict:
    """获取指令队列状态
    
    Returns:
        队列长度、当前指令剩余时间、待执行指令列表
    """
    return {
        "success": True,
        **get_queue_status()
    }


@mcp.tool()
def queue_clear() -> dict:
    """清空指令队列并停止当前指令
    
    Returns:
        被清除的指令数量
    """
    count = clear_queue()
    # 同时发送停止指令
    _execute_json_command_internal({'stop': True})
    return {
        "success": True,
        "cleared_count": count,
        "message": f"已清空队列并停止，清除 {count} 条指令"
    }


# ==================== 便捷指令工具 ====================

@mcp.tool()
def forward(duration: float = None) -> dict:
    """向前移动
    
    Args:
        duration: 持续时间(秒)，None=使用当前档位设置
    """
    dur = duration if duration is not None else car_state['duration']
    return execute_json_command({'linear_x': car_state['linear_speed'], 'duration': dur})


@mcp.tool()
def back(duration: float = None) -> dict:
    """向后移动
    
    Args:
        duration: 持续时间(秒)，None=使用当前档位设置
    """
    dur = duration if duration is not None else car_state['duration']
    return execute_json_command({'linear_x': -car_state['linear_speed'], 'duration': dur})


@mcp.tool()
def strafe_left(duration: float = None) -> dict:
    """向左平移
    
    Args:
        duration: 持续时间(秒)，None=使用当前档位设置
    """
    dur = duration if duration is not None else car_state['duration']
    return execute_json_command({'linear_y': car_state['linear_speed'], 'duration': dur})


@mcp.tool()
def strafe_right(duration: float = None) -> dict:
    """向右平移
    
    Args:
        duration: 持续时间(秒)，None=使用当前档位设置
    """
    dur = duration if duration is not None else car_state['duration']
    return execute_json_command({'linear_y': -car_state['linear_speed'], 'duration': dur})


@mcp.tool()
def rotate_left(degrees: float = 90) -> dict:
    """原地左转
    
    Args:
        degrees: 旋转角度(度)，默认90度
    """
    return execute_json_command({'angular_z': car_state['angular_speed'], 'rotate_deg': degrees})


@mcp.tool()
def rotate_right(degrees: float = 90) -> dict:
    """原地右转
    
    Args:
        degrees: 旋转角度(度)，默认90度
    """
    return execute_json_command({'angular_z': -car_state['angular_speed'], 'rotate_deg': degrees})


# ==================== 启动入口 ====================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if init_mqtt():
        # 启动指令队列处理线程
        start_queue_processor()
        
        logger.info("=" * 50)
        logger.info("小车控制MCP服务已启动")
        logger.info(f"MQTT: {MQTT_BROKER}:{MQTT_PORT}")
        logger.info("=" * 50)
        logger.info("【可用工具】")
        logger.info("  control    - 统一控制(字符串/JSON)")
        logger.info("  move       - 精确运动控制")
        logger.info("  stop       - 急停")
        logger.info("  follow     - 跟随模式")
        logger.info("  set_gear   - 设置档位")
        logger.info("  status     - 获取状态")
        logger.info("  sequence   - 指令序列(按时序执行)")
        logger.info("  queue_status - 查看队列状态")
        logger.info("  queue_clear  - 清空队列")
        logger.info("  forward/back/strafe_left/strafe_right - 方向移动")
        logger.info("  rotate_left/rotate_right - 原地旋转")
        logger.info("=" * 50)
        logger.info("【字符串指令】")
        logger.info("  forward, back, strafe_left, strafe_right")
        logger.info("  rotate_left, rotate_right, stop")
        logger.info("  speed_slow, speed_medium, speed_fast")
        logger.info("  duration_short, duration_medium, duration_infinite")
        logger.info("=" * 50)
        logger.info(f"当前档位: {car_state['speed_gear']}, {car_state['duration_gear']}")
        logger.info("服务就绪，等待指令...")
    else:
        logger.error("MQTT初始化失败")
        sys.exit(1)
    
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("服务被中断")
    finally:
        stop_queue_processor()
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
