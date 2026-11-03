# physical_exam_control.py
# 体检中心小智MCP服务 - 根据身高体重给出医学建议，并触发小智主动播报
from mcp.server.fastmcp import FastMCP
import sys
import logging
import paho.mqtt.client as mqtt
import json
import threading
import time
from typing import Dict, Any, Optional
import os
import urllib.request
import urllib.error

# 配置日志 - 输出到stderr，避免干扰MCP stdio通信
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr  # 输出到stderr，不影响MCP stdio通信
)

logger = logging.getLogger('HealthExamService')

# 串口读取支持（可选）
try:
    from serial_reader import SerialReader
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    # 使用stderr输出警告，不影响MCP通信
    sys.stderr.write("警告: 串口模块未找到，串口功能将不可用\n")

# Fix UTF-8 encoding for Windows console
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        sys.stderr.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Create MCP server
mcp = FastMCP("HealthExamService")

# MQTT 配置（参考 example 中的参数）
MQTT_BROKER = "47.97.8.221"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "health-exam-service-mcp"

# 主题配置
TOPICS = {
    # 仪器发布身高体重数据的主题（体检仪器发布到此）
    'instrument_data': '体检中心/仪器/身高体重',
    # 小智播报主题（向此主题发布内容，小智收到后主动说话）
    'xiaozhi_speak': '体检中心/小智/播报',
    # 数据上传确认/状态主题（可选）
    'upload_status': '体检中心/数据/状态',
}

# 小智备选播报主题（若小智监听的主题不同，设置此环境变量可同时发布到该主题）
# 例如: set XIAOZHI_SPEAK_TOPIC_ALT=device/xxx/tts
XIAOZHI_SPEAK_TOPIC_ALT = os.environ.get('XIAOZHI_SPEAK_TOPIC_ALT', '')

# 数据上传配置（可通过环境变量覆盖）
UPLOAD_URL = os.environ.get('PHYSICAL_EXAM_UPLOAD_URL', '')
UPLOAD_ENABLED = os.environ.get('PHYSICAL_EXAM_UPLOAD_ENABLED', 'false').lower() == 'true'

# 小智 TTS 推送（据 websocket.md，设备通过 WebSocket 从服务器接收 type:"tts" 与音频；若平台提供 HTTP 接口可在此配置）
XIAOZHI_TTS_PUSH_URL = os.environ.get('XIAOZHI_TTS_PUSH_URL', '')
XIAOZHI_TTS_PUSH_ENABLED = os.environ.get('XIAOZHI_TTS_PUSH_ENABLED', 'false').lower() == 'true'

# 最近体检记录（内存存储，最多100条）
exam_records = []
exam_records_lock = threading.Lock()

# 去重：记录最近处理的数据，避免重复处理（5秒内相同数据只处理一次）
last_processed_data = None
last_processed_time = 0
data_dedup_lock = threading.Lock()
DEDUP_TIME_WINDOW = 5  # 去重时间窗口（秒）

# MQTT 客户端
mqtt_client = None
device_status = {'mqtt_connected': False}

# 串口读取器（可选）
serial_reader = None

# 串口配置（可通过环境变量覆盖）
SERIAL_PORT = os.environ.get('SERIAL_PORT', '/dev/ttyUSB0')
SERIAL_BAUDRATE = int(os.environ.get('SERIAL_BAUDRATE', '115200'))  # 默认115200，已测试确认
SERIAL_ENABLED = os.environ.get('SERIAL_ENABLED', 'false').lower() == 'true'

# MQTT 连接参数：心跳间隔(秒)、重连延迟
MQTT_KEEPALIVE = 120
MQTT_RECONNECT_DELAY_MIN = 1
MQTT_RECONNECT_DELAY_MAX = 120


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    """计算 BMI：体重(kg) / 身高(m)^2"""
    if height_cm <= 0:
        return 0.0
    height_m = height_cm / 100.0
    return round(weight_kg / (height_m ** 2), 1)


# def get_medical_advice(weight_kg: float, height_cm: float, bmi: float) -> str:
#     """根据 BMI 生成医学建议"""
#     if bmi <= 0:
#         return "身高或体重数据异常，请重新测量。"
# 
#     # 中国成人 BMI 标准参考
#     if bmi < 18.5:
#         status = "偏瘦"
#         advice = "您的体重偏轻，建议适当增加营养摄入，多食用富含蛋白质的食物，适当进行力量训练以增强体质。"
#     elif bmi < 24:
#         status = "正常"
#         advice = "您的体重在正常范围内，请保持均衡饮食和适量运动，维持健康生活方式。"
#     elif bmi < 28:
#         status = "超重"
#         advice = "您存在超重情况，建议控制饮食热量，减少高脂高糖食物摄入，增加有氧运动如快走、游泳等，每周至少150分钟中等强度运动。"
#     else:
#         status = "肥胖"
#         advice = "您的体重偏高，建议咨询医生制定减重计划，控制饮食、增加运动，必要时进行医学干预，定期复查相关指标。"
# 
#     return f"您的身高为{height_cm}厘米，体重为{weight_kg}公斤，BMI指数为{bmi}，属于{status}范围。{advice}"


def push_tts_to_xiaozhi(text: str) -> bool:
    """通过 HTTP 向小智平台推送 TTS 文本（需平台提供接口）。据 websocket.md，设备端通过 WebSocket 接收服务器下发的 type:tts 与音频。"""
    if not XIAOZHI_TTS_PUSH_ENABLED or not XIAOZHI_TTS_PUSH_URL:
        return False
    try:
        data = json.dumps({"text": text}, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            XIAOZHI_TTS_PUSH_URL,
            data=data,
            headers={'Content-Type': 'application/json; charset=utf-8'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = 200 <= resp.status < 300
            if not ok:
                logger.warning(f"TTS 推送返回: {resp.status}")
            return ok
    except Exception as e:
        logger.error(f"TTS 推送失败: {e}")
        return False


def upload_exam_data(record: Dict[str, Any]) -> bool:
    """上传体检数据到配置的服务器"""
    if not UPLOAD_ENABLED or not UPLOAD_URL:
        logger.debug("数据上传未配置或已禁用，跳过上传")
        return False

    try:
        data = json.dumps(record, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            UPLOAD_URL,
            data=data,
            headers={'Content-Type': 'application/json; charset=utf-8'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if 200 <= resp.status < 300:
                logger.info(f"体检数据上传成功: {record.get('id', '')}")
                return True
            else:
                logger.warning(f"上传返回状态码: {resp.status}")
                return False
    except urllib.error.URLError as e:
        logger.error(f"上传体检数据失败: {e}")
        return False
    except Exception as e:
        logger.error(f"上传异常: {e}")
        return False


def on_mqtt_connect(client, userdata, flags, rc):
    """MQTT 连接回调"""
    if rc == 0:
        logger.info("MQTT 连接成功")
        device_status['mqtt_connected'] = True
        client.subscribe(TOPICS['instrument_data'], qos=2)
        client.subscribe(TOPICS['upload_status'], qos=2)
        logger.info(f"已订阅主题: {TOPICS['instrument_data']}, {TOPICS['upload_status']}")
    else:
        logger.error(f"MQTT 连接失败，错误代码: {rc}")
        device_status['mqtt_connected'] = False


def on_mqtt_disconnect(client, userdata, rc):
    """MQTT 断开连接回调"""
    device_status['mqtt_connected'] = False
    if rc == 0:
        logger.info("MQTT 正常断开")
    else:
        logger.warning(f"MQTT 连接断开 (rc={rc})，将自动重连")


def on_mqtt_message(client, userdata, msg):
    """MQTT 消息接收 - 处理仪器上报的身高体重数据"""
    try:
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        logger.debug(f"收到MQTT消息 - 主题: {topic}")

        if topic == TOPICS['instrument_data']:
            try:
                data = json.loads(payload)
                height = data.get('height', data.get('height_cm', 0))
                weight = data.get('weight', data.get('weight_kg', 0))
                record_id = data.get('id', data.get('record_id', f"exam_{int(time.time())}"))
                instrument_id = data.get('instrument_id', '')

                if height > 0 and weight > 0:
                    result = process_and_speak(height, weight, record_id, instrument_id)
                    logger.debug(f"自动处理仪器数据完成: BMI={result['record']['bmi']}")
                else:
                    logger.warning(f"仪器数据无效: height={height}, weight={weight}")
            except json.JSONDecodeError as e:
                logger.warning(f"无法解析仪器数据: {payload}, 错误: {e}")

    except Exception as e:
        logger.error(f"处理 MQTT 消息时出错: {e}")


def on_serial_data(height_cm: float, weight_kg: float):
    """串口数据回调函数 - 当从串口读取到身高体重数据时调用（606协议）"""
    global last_processed_data, last_processed_time
    
    try:
        current_time = time.time()
        
        # 去重检查：5秒内相同数据只处理一次
        with data_dedup_lock:
            if (last_processed_data is not None and 
                last_processed_data == (height_cm, weight_kg) and 
                current_time - last_processed_time < DEDUP_TIME_WINDOW):
                logger.debug(f"跳过重复数据: 身高={height_cm}cm, 体重={weight_kg}kg")
                return
            
            last_processed_data = (height_cm, weight_kg)
            last_processed_time = current_time
        
        logger.info(f"收到体检数据: 身高={height_cm}cm, 体重={weight_kg}kg")
        record_id = f"serial_{int(time.time() * 1000)}"
        result = process_and_speak(height_cm, weight_kg, record_id)
        logger.debug(f"数据处理完成: BMI={result['record']['bmi']}, 播报={'成功' if result['advice_spoken'] else '失败'}")
    except Exception as e:
        logger.error(f"处理串口数据时出错: {e}")


def init_serial():
    """初始化串口读取（支持606协议）- 失败不影响MCP服务"""
    global serial_reader
    
    if not SERIAL_ENABLED:
        logger.info("串口功能已禁用（设置 SERIAL_ENABLED=true 启用）")
        return False
    
    if not SERIAL_AVAILABLE:
        logger.warning("串口模块不可用，请安装 pyserial: pip install pyserial")
        return False
    
    try:
        serial_reader = SerialReader(
            port=SERIAL_PORT,
            baudrate=SERIAL_BAUDRATE,
            data_callback=on_serial_data
        )
        if serial_reader.start():
            logger.info(f"串口读取器已启动: {SERIAL_PORT} (波特率: {SERIAL_BAUDRATE})")
            logger.info("支持606协议，自动解析身高体重测量数据")
            return True
        else:
            logger.warning("串口读取器启动失败（串口可能被占用或设备不存在）")
            logger.warning("MCP服务继续运行，串口功能将不可用")
            serial_reader = None  # 确保为None，避免后续调用出错
            return False
    except Exception as e:
        # 检查是否是串口相关异常
        error_str = str(e).lower()
        error_type = type(e).__name__
        
        if 'SerialException' in error_type or 'serial' in error_str or 'port' in error_str or 'device' in error_str:
            logger.warning(f"串口打开失败: {e}")
        else:
            logger.error(f"初始化串口失败: {e}")
        logger.warning("MCP服务继续运行，串口功能将不可用")
        serial_reader = None
        return False


def process_and_speak(
    height_cm: float,
    weight_kg: float,
    record_id: str = "",
    instrument_id: str = "",
) -> Dict[str, Any]:
    """
    处理身高体重数据：计算 BMI、生成建议、触发小智播报、上传数据
    """
    bmi = calculate_bmi(weight_kg, height_cm)
    # advice_text = get_medical_advice(weight_kg, height_cm, bmi)  # 已注释
    advice_text = f"您的身高为{height_cm}厘米，体重为{weight_kg}公斤，BMI指数为{bmi}。"  # 临时替代方案

    record = {
        'id': record_id or f"exam_{int(time.time() * 1000)}",
        'instrument_id': instrument_id,
        'height_cm': height_cm,
        'weight_kg': weight_kg,
        'bmi': bmi,
        'advice': advice_text,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
    }

    with exam_records_lock:
        exam_records.append(record)
        if len(exam_records) > 100:
            exam_records.pop(0)

    upload_ok = upload_exam_data(record)

    speak_msg = {
        'text': advice_text,
        'type': 'physical_exam_advice',
        'record_id': record['id'],
        'bmi': bmi,
        'timestamp': record['timestamp'],
    }
    speak_ok = publish_mqtt_message(TOPICS['xiaozhi_speak'], speak_msg)
    if XIAOZHI_SPEAK_TOPIC_ALT:
        publish_mqtt_message(XIAOZHI_SPEAK_TOPIC_ALT, speak_msg)
    tts_push_ok = push_tts_to_xiaozhi(advice_text)

    return {
        'success': True,
        'record': record,
        'advice_spoken': speak_ok,
        'data_uploaded': upload_ok,
        'tts_push_ok': tts_push_ok,
        'tts_text': advice_text,
    }


def init_mqtt():
    """初始化 MQTT 连接"""
    global mqtt_client
    try:
        # 使用进程 ID 区分多实例，避免客户端 ID 冲突导致互相踢下线
        client_id = f"{MQTT_CLIENT_ID}-{os.getpid()}"
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id, clean_session=True)
        mqtt_client.on_connect = on_mqtt_connect
        mqtt_client.on_disconnect = on_mqtt_disconnect
        mqtt_client.on_message = on_mqtt_message
        mqtt_client.reconnect_delay_set(min_delay=MQTT_RECONNECT_DELAY_MIN, max_delay=MQTT_RECONNECT_DELAY_MAX)

        logger.info(f"正在连接到 MQTT 服务器: {MQTT_BROKER}:{MQTT_PORT} (keepalive={MQTT_KEEPALIVE}s)")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=MQTT_KEEPALIVE)
        mqtt_client.loop_start()
        time.sleep(1)
        return True
    except Exception as e:
        logger.error(f"MQTT 初始化失败: {e}")
        return False


def publish_mqtt_message(topic: str, message: Dict[str, Any]) -> bool:
    """发布 MQTT 消息"""
    global mqtt_client
    if not mqtt_client or not device_status['mqtt_connected']:
        logger.error("MQTT 客户端未连接")
        return False
    try:
        payload = json.dumps(message, ensure_ascii=False)
        result = mqtt_client.publish(topic, payload, qos=2)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.debug(f"消息已发布到主题 {topic}")
            return True
        else:
            logger.error(f"发布消息失败，错误代码: {result.rc}")
            return False
    except Exception as e:
        logger.error(f"发布 MQTT 消息时出错: {e}")
        return False


# ============ MCP 工具 ============

@mcp.tool()
def process_physical_exam(height_cm: float, weight_kg: float, record_id: str = "") -> dict:
    """处理体检身高体重数据并触发小智播报医学建议

    流程：人站上仪器 → 测出身高体重 → 调用此工具（或仪器直接发布到MQTT）→ 计算BMI → 生成医学建议 → 小智主动播报 → 数据上传

    Args:
        height_cm: 身高，单位厘米
        weight_kg: 体重，单位公斤
        record_id: 可选，体检记录ID

    Returns:
        处理结果，包含BMI、医学建议、播报和上传状态
    """
    try:
        if height_cm <= 0 or weight_kg <= 0:
            return {"success": False, "error": "身高和体重必须大于0"}
        if height_cm > 300 or weight_kg > 300:
            return {"success": False, "error": "身高或体重数值异常，请核对单位（身高厘米、体重公斤）"}

        result = process_and_speak(height_cm, weight_kg, record_id)
        out = {
            "success": True,
            "record": result['record'],
            "advice_spoken": result['advice_spoken'],
            "message": "已成功处理",
            "tts_text": result['tts_text'],
        }
        if result.get('tts_push_ok') is not None:
            out["tts_push_ok"] = result['tts_push_ok']
        return out
    except Exception as e:
        logger.error(f"处理体检数据失败: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def xiaozhi_speak(text: str) -> dict:
    """远程让小智主动说话（播报指定文字）

    据 websocket.md，小智设备通过 WebSocket 从服务器接收 type:tts 与音频后播放。本工具会：
    1) 向 MQTT 播报主题发布内容；2) 若配置了 XIAOZHI_TTS_PUSH_URL 则同时 HTTP 推送 TTS。
    MCP 返回中的 tts_text 供小智服务器收到后向设备下发 TTS（服务器需实现该逻辑）。

    Args:
        text: 要让小智播报的文字内容

    Returns:
        发布结果，含 tts_text 供服务器触发设备 TTS
    """
    try:
        if not text or not text.strip():
            return {"success": False, "error": "播报内容不能为空"}
        text = text.strip()
        speak_msg = {
            'text': text,
            'type': 'manual',
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        success = publish_mqtt_message(TOPICS['xiaozhi_speak'], speak_msg)
        if XIAOZHI_SPEAK_TOPIC_ALT:
            publish_mqtt_message(XIAOZHI_SPEAK_TOPIC_ALT, speak_msg)
        tts_push_ok = push_tts_to_xiaozhi(text)
        return {
            "success": success,
            "message": "已发送播报指令" if success else "MQTT 发布失败",
            "topic": TOPICS['xiaozhi_speak'],
            "tts_text": text,
            "tts_push_ok": tts_push_ok,
        }
    except Exception as e:
        logger.error(f"小智播报失败: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_exam_records(limit: int = 10, instrument_id: str = "") -> dict:
    """获取最近的体检记录

    Args:
        limit: 返回记录数量，默认10条；0 表示返回全部。
        instrument_id: 仪器序号（如 "HW-001"）。不为空时只返回该仪器的记录；
                       留空则返回所有仪器的记录。

    Returns:
        体检记录列表
    """
    try:
        with exam_records_lock:
            all_records = exam_records.copy()

        # 按仪器序号筛选
        if instrument_id:
            filtered = [r for r in all_records if r.get('instrument_id', '') == instrument_id]
        else:
            filtered = all_records

        recent = filtered[-limit:] if limit > 0 else filtered
        
        # 为了防止大模型在空数据时幻觉捏造数据，加强提示
        if len(recent) == 0:
            return {
                "success": True,
                "records": [],
                "total_count": 0,
                "message": "【注意：重要系统指令】目前系统中没有任何体检记录。你必须明确告知用户『当前没有历史记录』，严禁捏造或猜测任何假的身高或体重数据！",
                "filter_instrument_id": instrument_id or "(全部)"
            }

        return {
            "success": True,
            "records": recent,
            "total_count": len(filtered),
            "returned_count": len(recent),
            "filter_instrument_id": instrument_id or "(全部)",
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        }
    except Exception as e:
        logger.error(f"获取体检记录失败: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_mqtt_status() -> dict:
    """获取 MQTT 连接状态和主题配置"""
    return {
        "success": True,
        "mqtt_connected": device_status['mqtt_connected'],
        "topics": TOPICS,
        "xiaozhi_speak_topic_alt": XIAOZHI_SPEAK_TOPIC_ALT or "(未配置)",
        "upload_enabled": UPLOAD_ENABLED,
        "xiaozhi_tts_push_enabled": XIAOZHI_TTS_PUSH_ENABLED,
        "xiaozhi_tts_push_url": XIAOZHI_TTS_PUSH_URL or "(未配置)",
        "serial_enabled": SERIAL_ENABLED,
        "serial_port": SERIAL_PORT if SERIAL_ENABLED else "(未启用)",
        "serial_baudrate": SERIAL_BAUDRATE if SERIAL_ENABLED else "(未启用)",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
    }


@mcp.tool()
def start_serial_measurement() -> dict:
    """通过串口发送开始测量指令（606协议：身高体重测量 0x47）
    
    向体检机发送开始测量指令，设备会自动测量身高体重并通过串口返回数据。
    测量完成后，数据会自动处理并触发小智播报。
    
    Returns:
        发送结果
    """
    global serial_reader
    
    if not SERIAL_ENABLED:
        return {
            "success": False,
            "error": "串口功能未启用",
            "message": "请设置 SERIAL_ENABLED=true 启用串口功能"
        }
    
    if not serial_reader:
        return {
            "success": False,
            "error": "串口读取器未初始化",
            "message": "串口读取器可能启动失败，请检查日志"
        }
    
    try:
        success = serial_reader.start_measurement()
        if success:
            return {
                "success": True,
                "message": "已发送开始测量指令，等待设备测量完成...",
                "command": "0x47 (身高体重开始测量)",
                "note": "测量完成后，数据会自动处理并触发小智播报"
            }
        else:
            return {
                "success": False,
                "error": "发送指令失败",
                "message": "无法向串口发送指令，请检查串口连接"
            }
    except Exception as e:
        logger.error(f"发送测量指令失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"发送指令时发生异常: {e}"
        }


@mcp.tool()
def get_last_person_height_weight(instrument_id: str = "") -> dict:
    """获取最后一个人的身高体重数据并推送到服务器
    
    从最近的体检记录中获取最后一个人的身高体重数据，并向配置的服务器推送。
    若没有符合条件的真实记录，直接返回错误，不再随机生成数据。

    Args:
        instrument_id: 仪器序号（如 "HW-001"）。不为空时只在该仪器的历史记录中查找最后一条；
                       留空则在所有仪器记录中取最后一条。

    Returns:
        包含最后一个人的身高体重信息及推送状态的结果
    """
    try:
        # 获取最后一条体检记录（按仪器序号筛选）
        with exam_records_lock:
            if instrument_id:
                candidate_records = [r for r in exam_records if r.get('instrument_id', '') == instrument_id]
            else:
                candidate_records = exam_records.copy()
            has_records = len(candidate_records) > 0

        if not has_records:
            msg = f"仪器 {instrument_id} 暂无体检记录" if instrument_id else "系统刚重启或暂未收到任何测量数据"
            logger.warning(msg)
            return {
                "success": False,
                "error": "暂无真实体检数据",
                "message": f"【注意：重要系统指令】{msg}。你必须严格如实回复用户：“暂时没有找到任何体检记录”，绝对不可捏造、猜测或随机生成任何假的身高或体重数据！",
                "filter_instrument_id": instrument_id or "(全部)",
                "uploaded": False,
            }

        last_record = candidate_records[-1]
        # 提取身高体重数据
        height_cm = last_record.get('height_cm', 0)
        weight_kg = last_record.get('weight_kg', 0)
        record_id = last_record.get('id', '')
        timestamp = last_record.get('timestamp', '')
        bmi = last_record.get('bmi', 0)

        if height_cm <= 0 or weight_kg <= 0:
            return {
                "success": False,
                "error": "最后一条记录数据无效",
                "message": f"height_cm={height_cm}, weight_kg={weight_kg}",
                "filter_instrument_id": instrument_id or "(全部)",
                "uploaded": False,
            }
        
        # 构建推送数据（仅包含身高体重）
        push_data = {
            'id': record_id,
            'height_cm': height_cm,
            'weight_kg': weight_kg,
            'bmi': bmi,
            'timestamp': timestamp,
        }
        
        # 向服务器推送
        upload_ok = upload_exam_data(push_data)
        
        if upload_ok:
            message = "已成功向服务器推送最后一条体检数据"
            logger.info(f"成功推送数据: 身高={height_cm}cm, 体重={weight_kg}kg, BMI={bmi}")
            return {
                "success": True,
                "message": message,
                "filter_instrument_id": instrument_id or "(全部)",
                "data": {
                    "height_cm": height_cm,
                    "weight_kg": weight_kg,
                    "bmi": bmi,
                    "instrument_id": last_record.get('instrument_id', ''),
                    "record_id": record_id,
                    "timestamp": timestamp,
                },
                "uploaded": True,
            }
        else:
            # 如果上传未启用，认为获取数据本身成功
            if not UPLOAD_ENABLED or not UPLOAD_URL:
                return {
                    "success": True,
                    "message": "已成功获取体检数据",
                    "data": {
                        "height_cm": height_cm,
                        "weight_kg": weight_kg,
                        "bmi": bmi,
                        "record_id": record_id,
                        "timestamp": timestamp,
                        "instrument_id": last_record.get('instrument_id', ''),
                    }
                }
            else:
                return {
                    "success": False,
                    "error": "推送失败",
                    "message": "向服务器推送数据时发生错误，请检查网络连接和服务器状态",
                    "data": {
                        "height_cm": height_cm,
                        "weight_kg": weight_kg,
                        "bmi": bmi,
                        "record_id": record_id,
                        "timestamp": timestamp,
                        "instrument_id": last_record.get('instrument_id', ''),
                    },
                    "uploaded": False,
                }
    except Exception as e:
        logger.error(f"推送最后一条体检数据失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"推送过程中发生异常: {e}",
        }


if __name__ == "__main__":
    if init_mqtt():
        logger.info("体检中心小智 MCP 服务已启动")
        logger.info(f"MQTT 服务器: {MQTT_BROKER}:{MQTT_PORT}")
        logger.info(f"仪器数据主题: {TOPICS['instrument_data']}")
        logger.info(f"小智播报主题: {TOPICS['xiaozhi_speak']}")
        logger.info("可用工具: process_physical_exam, xiaozhi_speak, get_exam_records(instrument_id), get_mqtt_status, get_last_person_height_weight(instrument_id), start_serial_measurement")
        
        # 初始化串口（如果启用）- 失败不影响MCP服务启动
        if SERIAL_ENABLED:
            try:
                serial_init_result = init_serial()
                if not serial_init_result:
                    logger.warning("串口初始化失败，但MCP服务继续运行（串口功能将不可用）")
            except Exception as e:
                logger.error(f"串口初始化异常: {e}，MCP服务继续运行")
                import traceback
                traceback.print_exc(file=sys.stderr)
        else:
            logger.info("串口功能未启用（设置 SERIAL_ENABLED=true 启用）")
    else:
        logger.error("MQTT 初始化失败，服务启动中止")
        sys.exit(1)

    try:
        # 启动MCP服务（使用stdio传输）
        # 注意：MCP服务通过stdio与外部通信，所有日志已配置输出到stderr
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("服务被用户中断")
    except Exception as e:
        # 错误信息输出到stderr，不影响MCP通信
        sys.stderr.write(f"MCP服务运行出错: {e}\n")
        import traceback
        traceback.print_exc(file=sys.stderr)
    finally:
        # 清理资源
        if serial_reader:
            try:
                serial_reader.stop()
            except:
                pass
        if mqtt_client:
            try:
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
            except:
                pass
