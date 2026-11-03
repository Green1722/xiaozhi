#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESP32 摄像头照片接收保存工具
================================
监听 ESP32 的 USB 串口输出，自动识别并保存拍摄的照片到本地目录。

用法:
  python photo_saver.py                         # 交互式选择串口
  python photo_saver.py COM3                    # 直接指定串口
  python photo_saver.py COM3 ./我的照片         # 指定串口和保存目录
  python photo_saver.py /dev/ttyUSB0 ./photos  # Linux/Mac

参数:
  port       串口号 (如 COM3, /dev/ttyUSB0)，不填则交互式选择
  save_dir   照片保存目录，默认 ./esp32_photos
  --baudrate  波特率，默认 115200
  --no-log   不打印 ESP32 的普通日志输出

协议说明:
  ESP32 固件在拍照后通过串口输出以下格式的数据:
    <<<PHOTO_BEGIN:photo_<timestamp>.jpg>>>
    <Base64 编码的 JPEG 数据，每行 76 个字符>
    <<<PHOTO_END>>>
"""

import serial
import serial.tools.list_ports
import base64
import os
import sys
import time
import re
import argparse
import datetime

PHOTO_BEGIN_PREFIX = "<<<PHOTO_BEGIN:"
PHOTO_END_MARKER = "<<<PHOTO_END>>>"
DEFAULT_SAVE_DIR = "./esp32_photos"

# Base64 合法字符集
_B64_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")


def list_serial_ports():
    """列出所有可用串口"""
    ports = serial.tools.list_ports.comports()
    return [(p.device, p.description) for p in ports]


def strip_esp_log_prefix(line: str) -> str:
    """
    去除 ESP-IDF 日志前缀，如:
      'I (12345) Esp32Camera: DATA' -> 'DATA'
    """
    # 匹配 ESP-IDF 日志格式: [IWEDC] (nnn) TAG: content
    m = re.match(r'^[IWEDC]\s*\(\s*\d+\)\s*[^:]+:\s*(.*)', line)
    if m:
        return m.group(1).strip()
    return line.strip()


def is_base64_line(s: str) -> bool:
    """判断字符串是否为纯 Base64 内容（允许尾部填充=）"""
    if not s:
        return False
    return all(c in _B64_CHARS for c in s)


def save_photo(jpeg_data: bytes, filename: str, save_dir: str) -> str:
    """保存 JPEG 文件到目录，返回完整路径"""
    os.makedirs(save_dir, exist_ok=True)
    # 若重名则加时间戳后缀
    filepath = os.path.join(save_dir, filename)
    if os.path.exists(filepath):
        name, ext = os.path.splitext(filename)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(save_dir, f"{name}_{ts}{ext}")
    with open(filepath, 'wb') as f:
        f.write(jpeg_data)
    return filepath


def monitor_serial(port: str, baudrate: int = 115200,
                   save_dir: str = DEFAULT_SAVE_DIR,
                   show_log: bool = True):
    """持续监听串口，识别并保存照片"""
    print(f"[INFO] 打开串口: {port} @ {baudrate} baud")
    print(f"[INFO] 照片保存目录: {os.path.abspath(save_dir)}")
    print("[INFO] 等待 ESP32 拍照... (按 Ctrl+C 退出)\n")

    try:
        ser = serial.Serial(port, baudrate, timeout=1.0)
    except serial.SerialException as e:
        print(f"[ERROR] 无法打开串口 {port}: {e}")
        return

    in_photo = False
    filename = None
    b64_lines = []
    photo_count = 0

    try:
        while True:
            try:
                raw = ser.readline()
            except serial.SerialException as e:
                print(f"\n[ERROR] 串口读取失败: {e}")
                break

            if not raw:
                continue

            try:
                line = raw.decode('utf-8', errors='ignore').rstrip('\r\n')
            except Exception:
                continue

            # 处理照片帧外的普通输出
            if not in_photo:
                if show_log and line:
                    print(line, flush=True)

                if PHOTO_BEGIN_PREFIX in line:
                    # 提取文件名: <<<PHOTO_BEGIN:photo_xxx.jpg>>>
                    idx = line.index(PHOTO_BEGIN_PREFIX)
                    rest = line[idx + len(PHOTO_BEGIN_PREFIX):]
                    if '>>>' in rest:
                        filename = rest[:rest.index('>>>')]
                    else:
                        filename = f"photo_{int(time.time())}.jpg"
                    in_photo = True
                    b64_lines = []
                    print(f"\n[>>>] 开始接收照片: {filename}", flush=True)

            else:
                # 在照片帧内
                if PHOTO_END_MARKER in line:
                    # 完成接收，解码并保存
                    b64_data = ''.join(b64_lines)
                    if b64_data:
                        try:
                            jpeg_data = base64.b64decode(b64_data, validate=False)
                            filepath = save_photo(jpeg_data, filename, save_dir)
                            photo_count += 1
                            size_kb = len(jpeg_data) / 1024
                            print(f"[OK] 照片已保存: {filepath}  ({size_kb:.1f} KB)", flush=True)
                        except Exception as e:
                            print(f"[ERROR] 解码照片失败: {e}", flush=True)
                    else:
                        print("[WARN] 收到空照片数据，已跳过", flush=True)

                    in_photo = False
                    filename = None
                    b64_lines = []
                else:
                    # 收集 Base64 数据行
                    # 去除可能存在的 ESP 日志前缀
                    clean = strip_esp_log_prefix(line)
                    if is_base64_line(clean):
                        b64_lines.append(clean)
                        # 实时进度（每 50 行打印一次）
                        if len(b64_lines) % 50 == 0:
                            approx_kb = len(b64_lines) * 57 / 1024
                            print(f"  ... 已接收 ~{approx_kb:.1f} KB", flush=True)

    except KeyboardInterrupt:
        print(f"\n[INFO] 已停止监听。共保存 {photo_count} 张照片。")
    finally:
        ser.close()


def main():
    parser = argparse.ArgumentParser(
        description="监听 ESP32 USB 串口，自动保存摄像头拍摄的照片",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('port', nargs='?', help='串口号 (如 COM3 或 /dev/ttyUSB0)，不填则列出可用串口供选择')
    parser.add_argument('save_dir', nargs='?', default=DEFAULT_SAVE_DIR, help=f'照片保存目录 (默认: {DEFAULT_SAVE_DIR})')
    parser.add_argument('--baudrate', '-b', type=int, default=115200, help='串口波特率 (默认: 115200)')
    parser.add_argument('--no-log', action='store_true', help='不打印 ESP32 普通日志')
    args = parser.parse_args()

    port = args.port

    if port is None:
        ports = list_serial_ports()
        if not ports:
            print("[ERROR] 未找到任何可用串口，请检查 USB 数据线连接。")
            sys.exit(1)

        print("可用串口:")
        for i, (dev, desc) in enumerate(ports):
            print(f"  [{i}] {dev}  —  {desc}")

        choice = input("\n请输入串口编号 (回车选 0): ").strip()
        if choice == '':
            choice = '0'
        try:
            port = ports[int(choice)][0]
        except (ValueError, IndexError):
            print("[ERROR] 无效选择")
            sys.exit(1)

    monitor_serial(port, args.baudrate, args.save_dir, not args.no_log)


if __name__ == '__main__':
    main()
