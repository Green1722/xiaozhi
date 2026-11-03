"""
串口数据调试工具
实时显示ESP32发送的所有数据，帮助诊断聊天记录问题
"""
import serial
import serial.tools.list_ports
import re
import sys
import time

def list_ports():
    """列出所有可用串口"""
    ports = list(serial.tools.list_ports.comports())
    print(f"检测到 {len(ports)} 个串口设备:")
    for i, p in enumerate(ports):
        print(f"  [{i}] {p.device} - {p.description}")
    return ports

def monitor_serial(port_name, baudrate=115200, duration=30):
    """监控串口数据"""
    print(f"\n正在连接到 {port_name} @ {baudrate}...")
    print("=" * 60)
    print("提示: 请对ESP32说话或让它回复，观察输出数据")
    print("=" * 60)
    print()
    
    # 尝试多种解码方式
    encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    
    try:
        ser = serial.Serial(port_name, baudrate, timeout=1)
        print(f"✅ 串口已打开\n")
        
        # 显示当前使用的消息模式
        print("程序正在查找以下格式的消息:")
        print("  - 用户消息: '>> ' 开头")
        print("  - AI消息:   '<< ' 开头")
        print()
        print("-" * 60)
        
        start_time = time.time()
        line_count = 0
        
        while time.time() - start_time < duration:
            try:
                line = ser.readline()
                if line:
                    line_count += 1
                    
                    # 尝试多种编码
                    decoded_text = None
                    for enc in encodings:
                        try:
                            decoded_text = line.decode(enc).strip()
                            break
                        except:
                            continue
                    
                    if decoded_text is None:
                        decoded_text = line.decode('utf-8', errors='ignore').strip()
                    
                    # 移除ANSI转义序列
                    clean_text = ansi_escape.sub('', decoded_text)
                    
                    # 分析数据
                    print(f"[{line_count:3d}] RAW: {repr(line)[:80]}")
                    print(f"      CLEAN: {clean_text[:100]}")
                    
                    # 检查是否匹配聊天格式
                    if clean_text.startswith(">> "):
                        print(f"      ✅ 检测到用户消息: {clean_text[3:]}")
                    elif clean_text.startswith("<< "):
                        print(f"      ✅ 检测到AI消息: {clean_text[3:]}")
                    elif clean_text.strip():
                        # 非空但格式不匹配
                        print(f"      ⚠️ 格式不匹配（非 >> 或 << 开头）")
                    print()
                    
            except Exception as e:
                print(f"读取错误: {e}")
                break
        
        print("-" * 60)
        print(f"共接收 {line_count} 行数据")
        ser.close()
        
    except serial.SerialException as e:
        print(f"❌ 无法打开串口: {e}")
        return False
    
    return True

def main():
    # 列出可用串口
    ports = list_ports()
    
    if not ports:
        print("\n❌ 未检测到任何串口设备")
        return
    
    # 让用户选择端口
    if len(ports) == 1:
        port_name = ports[0].device
    else:
        print("\n请选择要监控的串口编号:", end=" ")
        try:
            choice = int(input().strip())
            if choice < 0 or choice >= len(ports):
                print("无效选择")
                return
            port_name = ports[choice].device
        except ValueError:
            print("请输入有效数字")
            return
    
    # 可选波特率
    print(f"\n使用的波特率: 115200")
    print("按 Ctrl+C 停止监控")
    time.sleep(0.5)
    
    monitor_serial(port_name, baudrate=115200, duration=60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n监控已停止")
