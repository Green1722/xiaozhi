#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
串口读取模块 - 从体检机读取身高体重数据（支持606协议）
"""
import serial
import serial.tools.list_ports
import threading
import logging
import time
import re
import json
from typing import Optional, Callable

logger = logging.getLogger('SerialReader')

# 606协议常量
FRAME_HEADER_SEND = 0x5E  # 发送帧头
FRAME_HEADER_RESP = 0x5F  # 应答帧头
FRAME_TAIL = 0x0D  # 帧尾

class SerialReader:
    """串口读取器，用于从体检机读取数据"""
    
    def __init__(self, 
                 port: str = '/dev/ttyUSB0',
                 baudrate: int = 115200,  # 默认115200，已测试确认
                 timeout: float = 1.0,
                 data_callback: Optional[Callable] = None):
        """
        初始化串口读取器
        
        参数:
            port: 串口设备路径
            baudrate: 波特率
            timeout: 超时时间（秒）
            data_callback: 数据回调函数，接收(height_cm, weight_kg)参数
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.data_callback = data_callback
        self.ser: Optional[serial.Serial] = None
        self.running = False
        self.read_thread: Optional[threading.Thread] = None
        # 记录最近一次完整测量结果，用于去重
        self._last_measurement = None  # (height_cm, weight_kg)
        # 最近一次“重复上报”提示的时间，用于限制日志频率
        self._last_duplicate_log_time = 0.0
        # 重复上报提示最小间隔（秒）- 默认更保守，避免刷屏
        self._duplicate_log_interval = 30.0
        # 是否检测到“测量中”的过程：用来判断是否真的开始了新测量
        self._measurement_in_progress = False
        self._last_progress_time = 0.0
        # 认为“测量中→测量完成”为同一次测量的最长间隔（秒）
        self._progress_expiry = 15.0
        
    def start(self) -> bool:
        """启动串口读取"""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            logger.info(f"串口 {self.port} 打开成功 (波特率: {self.baudrate})")
            
            # 等待串口稳定
            time.sleep(0.5)
            self.ser.reset_input_buffer()
            
            # 启动读取线程
            self.running = True
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            logger.info("串口读取线程已启动")
            return True
            
        except serial.SerialException as e:
            logger.error(f"串口打开失败: {e}")
            return False
        except Exception as e:
            logger.error(f"启动串口读取器失败: {e}")
            return False
    
    def send_command(self, cmd_byte: int, data: bytes = b'', timeout: float = 2.0) -> bool:
        """
        发送606协议指令
        
        参数:
            cmd_byte: 命令字节（如 0x47 表示身高体重测量）
            data: 数据部分（可选）
            timeout: 超时时间（秒）
        
        返回: 是否发送成功
        """
        if not self.ser or not self.ser.is_open:
            logger.error("串口未打开，无法发送指令")
            return False
        
        try:
            # 构建606协议帧：帧头(0x5E) + 长度(1+len(data)) + 命令(1) + 数据 + 帧尾(0x0D)
            length = 1 + len(data)  # 命令(1) + 数据长度
            frame = bytes([FRAME_HEADER_SEND, length, cmd_byte]) + data + bytes([FRAME_TAIL])
            
            self.ser.write(frame)
            self.ser.flush()
            logger.info(f"已发送606协议指令: 命令=0x{cmd_byte:02X}, 数据长度={len(data)}")
            return True
        except Exception as e:
            logger.error(f"发送606协议指令失败: {e}")
            return False
    
    def start_measurement(self) -> bool:
        """
        发送开始测量指令（身高体重，0x47）
        
        返回: 是否发送成功
        """
        return self.send_command(0x47)
    
    def stop(self):
        """停止串口读取"""
        self.running = False
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=2)
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info(f"串口 {self.port} 已关闭")
    
    def _read_loop(self):
        """读取循环（在独立线程中运行）- 支持606协议"""
        buffer = b''
        
        while self.running:
            try:
                if self.ser and self.ser.in_waiting > 0:
                    # 读取数据
                    data = self.ser.read(self.ser.in_waiting)
                    buffer += data
                    
                    # 优先尝试解析606协议帧
                    frame = self._parse_606_frame_from_buffer(buffer)
                    if frame:
                        # 成功解析606协议帧
                        buffer = buffer[len(frame['raw']):]  # 移除已解析的帧
                        self._handle_606_frame(frame)
                        continue
                    
                    # 如果不是606协议，尝试文本格式解析（向后兼容）
                    if len(buffer) > 0 and buffer[0] not in (FRAME_HEADER_SEND, FRAME_HEADER_RESP):
                        # 可能是文本格式，尝试解析
                        try:
                            text = buffer.decode('utf-8', errors='ignore')
                            lines = text.split('\n')
                            
                            # 处理完整的行
                            for line in lines[:-1]:  # 最后一行可能不完整
                                line = line.strip()
                                if line:
                                    self._parse_line(line)
                            
                            # 保留最后一行（可能不完整）
                            buffer = lines[-1].encode('utf-8') if lines else b''
                            
                        except Exception as e:
                            logger.debug(f"解析文本数据时出错: {e}")
                            # 如果第一个字节不是606协议帧头，丢弃第一个字节
                            if len(buffer) > 0:
                                buffer = buffer[1:]
                    elif len(buffer) > 256:
                        # 缓冲区过大，可能是数据错误，清空
                        logger.warning("缓冲区过大，清空缓冲区")
                        buffer = b''
                
                else:
                    time.sleep(0.1)  # 没有数据时短暂休眠
                    
            except Exception as e:
                logger.error(f"读取串口数据时出错: {e}")
                time.sleep(1)
    
    def _parse_606_frame_from_buffer(self, buffer: bytes):
        """
        从缓冲区解析606协议帧
        
        返回: 解析后的帧数据或None
        """
        if len(buffer) < 4:  # 至少需要：帧头+长度+命令+帧尾
            return None
        
        # 查找帧头
        frame_start = -1
        for i in range(len(buffer)):
            if buffer[i] in (FRAME_HEADER_SEND, FRAME_HEADER_RESP):
                frame_start = i
                break
        
        if frame_start == -1:
            return None  # 没有找到帧头
        
        # 从帧头开始解析
        if frame_start > 0:
            # 有非协议数据，先丢弃
            logger.debug(f"丢弃 {frame_start} 字节非协议数据")
            buffer = buffer[frame_start:]
        
        # 检查帧头
        if buffer[0] not in (FRAME_HEADER_SEND, FRAME_HEADER_RESP):
            return None
        
        if len(buffer) < 2:
            return None  # 需要更多数据
        
        # 读取长度字段（命令+数据的长度）
        length = buffer[1]
        
        # 计算完整帧长度：帧头(1) + 长度(1) + 数据(length) + 帧尾(1)
        total_length = 1 + 1 + length + 1
        
        if len(buffer) < total_length:
            return None  # 数据不完整，需要等待更多数据
        
        # 检查帧尾
        if buffer[total_length - 1] != FRAME_TAIL:
            return None  # 帧尾错误
        
        # 提取命令和数据
        cmd = buffer[2]
        payload = buffer[3:total_length-1] if length > 1 else b''
        
        return {
            'valid': True,
            'frame_type': '发送' if buffer[0] == FRAME_HEADER_SEND else '应答',
            'cmd': cmd,
            'payload': payload,
            'length': length,
            'raw': buffer[:total_length]
        }
    
    def _handle_606_frame(self, frame: dict):
        """处理606协议帧"""
        cmd = frame['cmd']
        payload = frame['payload']
        
        logger.debug(f"收到606协议帧: 命令=0x{cmd:02X}, 类型={frame['frame_type']}")
        
        # 处理身高体重测量响应 (0x47)
        if cmd == 0x47 and len(payload) >= 6:
            height_h = payload[0]
            height_l = payload[1]
            height_status = payload[2]
            weight_h = payload[3]
            weight_l = payload[4]
            weight_status = payload[5]
            
            height_cm = ((height_h << 8) | height_l) / 100.0
            weight_kg = ((weight_h << 8) | weight_l) / 100.0
            
            now = time.time()
            # “测量中”状态：标记开始了新测量过程
            if height_status == 0x00 or weight_status == 0x00:
                self._measurement_in_progress = True
                self._last_progress_time = now
                logger.debug(f"606协议: 测量中 - 身高={height_cm}cm, 体重={weight_kg}kg")
                return

            # 测量完成：只有当检测到“测量中→测量完成”过程时，才认为是新信息
            if height_status == 0x01 and weight_status == 0x01:
                has_recent_progress = (
                    self._measurement_in_progress
                    and (now - self._last_progress_time) <= self._progress_expiry
                )

                if has_recent_progress:
                    # 这是一次新的测量完成（哪怕数值与上次一样，也算新测量）
                    self._measurement_in_progress = False
                    self._last_measurement = (height_cm, weight_kg)
                    logger.debug(f"606协议: 新测量完成 - 身高={height_cm}cm, 体重={weight_kg}kg")
                    if self.data_callback:
                        try:
                            self.data_callback(height_cm, weight_kg)
                        except Exception as e:
                            logger.error(f"回调函数执行失败: {e}")
                    return

                # 没检测到“测量中”过程：通常是设备在重复上报上次结果
                if self._last_measurement == (height_cm, weight_kg):
                    if now - self._last_duplicate_log_time >= self._duplicate_log_interval:
                        logger.info(
                            f"未收到最新的身高体重信息（设备重复上报上次结果: 身高={height_cm}cm, 体重={weight_kg}kg）"
                        )
                        self._last_duplicate_log_time = now
                    else:
                        logger.debug(
                            f"重复上报的身高体重数据（身高={height_cm}cm, 体重={weight_kg}kg），已忽略"
                        )
                    return

                # 数值变化但也没看到“测量中”过程：保守处理为新数据（避免漏掉某些设备直接上报完成态）
                self._last_measurement = (height_cm, weight_kg)
                logger.debug(f"606协议: 测量完成(无测量中过程) - 身高={height_cm}cm, 体重={weight_kg}kg")
                if self.data_callback:
                    try:
                        self.data_callback(height_cm, weight_kg)
                    except Exception as e:
                        logger.error(f"回调函数执行失败: {e}")
                return

            else:
                logger.warning(f"606协议: 测量失败 - 身高状态=0x{height_status:02X}, 体重状态=0x{weight_status:02X}")
        
        # 处理身高测量响应 (0x42)
        elif cmd == 0x42 and len(payload) >= 3:
            height_h = payload[0]
            height_l = payload[1]
            status = payload[2]
            height_cm = ((height_h << 8) | height_l) / 10.0
            
            if status == 0x01:
                logger.info(f"606协议: 身高测量完成 - {height_cm}cm")
            elif status == 0x00:
                logger.debug(f"606协议: 身高测量中 - {height_cm}cm")
            else:
                logger.warning(f"606协议: 身高测量失败")
        
        # 处理体重测量响应 (0x43)
        elif cmd == 0x43 and len(payload) >= 3:
            weight_h = payload[0]
            weight_l = payload[1]
            status = payload[2]
            weight_kg = ((weight_h << 8) | weight_l) / 10.0
            
            if status == 0x01:
                logger.info(f"606协议: 体重测量完成 - {weight_kg}kg")
            elif status == 0x00:
                logger.debug(f"606协议: 体重测量中 - {weight_kg}kg")
            else:
                logger.warning(f"606协议: 体重测量失败")
        
        # 其他命令（版本号、温湿度等）只记录日志
        else:
            logger.debug(f"606协议: 收到命令 0x{cmd:02X}，暂不处理")
    
    def _parse_line(self, line: str):
        """
        解析一行数据，提取身高体重
        
        支持的格式示例：
        - "H:170 W:65"
        - "Height:170 Weight:65"
        - "170,65"
        - JSON: {"height":170,"weight":65}
        """
        logger.debug(f"收到数据: {line}")
        
        height = None
        weight = None
        
        # 方法1: 尝试解析JSON
        try:
            data = json.loads(line)
            height = data.get('height', data.get('height_cm', None))
            weight = data.get('weight', data.get('weight_kg', None))
        except:
            pass
        
        # 方法2: 正则表达式匹配 "H:170 W:65" 格式
        if height is None or weight is None:
            match = re.search(r'H[:\s]*(\d+\.?\d*)', line, re.IGNORECASE)
            if match:
                height = float(match.group(1))
            
            match = re.search(r'W[:\s]*(\d+\.?\d*)', line, re.IGNORECASE)
            if match:
                weight = float(match.group(1))
        
        # 方法3: 正则表达式匹配 "Height:170 Weight:65" 格式
        if height is None or weight is None:
            match = re.search(r'Height[:\s]*(\d+\.?\d*)', line, re.IGNORECASE)
            if match:
                height = float(match.group(1))
            
            match = re.search(r'Weight[:\s]*(\d+\.?\d*)', line, re.IGNORECASE)
            if match:
                weight = float(match.group(1))
        
        # 方法4: 逗号分隔格式 "170,65"
        if height is None or weight is None:
            match = re.search(r'(\d+\.?\d*)[,\s]+(\d+\.?\d*)', line)
            if match:
                height = float(match.group(1))
                weight = float(match.group(2))
        
        # 如果成功解析，调用回调函数
        if height is not None and weight is not None:
            logger.info(f"解析到数据: 身高={height}cm, 体重={weight}kg")
            if self.data_callback:
                try:
                    self.data_callback(height, weight)
                except Exception as e:
                    logger.error(f"回调函数执行失败: {e}")
        else:
            logger.debug(f"无法解析数据: {line}")

def list_serial_ports():
    """列出所有可用的串口"""
    ports = serial.tools.list_ports.comports()
    result = []
    for port in ports:
        result.append({
            'device': port.device,
            'description': port.description,
            'hwid': port.hwid
        })
    return result

if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    def on_data(height, weight):
        print(f"收到体检数据: 身高={height}cm, 体重={weight}kg")
    
    reader = SerialReader(
        port='/dev/ttyUSB0',
        baudrate=115200,  # 已确认的波特率
        data_callback=on_data
    )
    
    try:
        if reader.start():
            print("串口读取器已启动，按 Ctrl+C 停止...")
            while True:
                time.sleep(1)
        else:
            print("启动失败")
    except KeyboardInterrupt:
        print("\n正在停止...")
        reader.stop()
        print("已停止")

