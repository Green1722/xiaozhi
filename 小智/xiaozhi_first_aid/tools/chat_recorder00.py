"""
小智 AI 对话记录器 (实时透明弹窗版)
"""
import sys
import time
from datetime import datetime
from pathlib import Path
import re
import threading
import tkinter as tk
from tkinter import font

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("请先安装 pyserial: pip install pyserial")
    sys.exit(1)

class ChatRecorder:
    def __init__(self):
        self.txt_file = None
        self.last_date = None
        
    def open_file(self):
        # 每天创建一个独立文件夹
        today = datetime.now().strftime('%Y-%m-%d')
        log_dir = Path("chat_logs") / today
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 确保以 utf-8 写入
        self.txt_file = log_dir / f"chat_{datetime.now().strftime('%H%M%S')}.txt"
        with open(self.txt_file, 'w', encoding='utf-8') as f:
            f.write(f"聊天记录开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
    def log(self, role: str, content: str):
        now = datetime.now()
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M:%S')
        name = {"user": "用户", "assistant": "AI"}.get(role, role)
        
        with open(self.txt_file, 'a', encoding='utf-8') as f:
            f.write(f"[{time_str}] {name}: {content}\n")
            
        # 顺便打印到控制台，以便查阅
        print(f"[{time_str}] {name}: {content}")
            
    def close(self):
        if self.txt_file and self.txt_file.exists():
            with open(self.txt_file, 'a', encoding='utf-8') as f:
                f.write(f"\n结束: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("小智 AI 实时对话面板")
        self.geometry("420x650")
        self.attributes('-topmost', True) # 窗口置顶，方便随时看到
        
        # 不透明背景色: 设定浅蓝色
        self.bg_color = '#ADD8E6'  # 浅蓝色背景
        self.trans_color = self.bg_color # 兼容原有变量
        self.configure(bg=self.bg_color)
        # 移除透明属性
        # self.wm_attributes('-transparentcolor', self.trans_color)
        
        # 画布作为主显示区
        self.canvas = tk.Canvas(self, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        
        self.frame = tk.Frame(self.canvas, bg=self.bg_color)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        
        self.frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        
        # 绑定滚轮滚动
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # 准备字体
        self.custom_font = font.Font(family="Microsoft YaHei", size=18)
        self.sys_font = font.Font(family="Microsoft YaHei", size=9)
        
        self.recorder = ChatRecorder()
        self.recorder.open_file()
        
        self.running = True
        
        # UI中展示一条欢迎和拖拽提示
        self.show_system_msg("✨ 小智对话悬浮窗已启动 ✨\n提示: 拖动顶部标题栏可移动窗口")
        
        # 启动后台串口监听线程
        self.serial_thread = threading.Thread(target=self.serial_worker, daemon=True)
        self.serial_thread.start()
        
        # 窗口关闭事件处理
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def on_closing(self):
        self.running = False
        self.recorder.close()
        self.destroy()

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.after(10, lambda: self.canvas.yview_moveto(1.0))
        
    def on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)
        
    def add_message_ui(self, role, text):
        bg_color = "#95EC69" if role == "user" else "#FFFFFF"  # 微信气泡：绿(右)，白(左)
        fg_color = "#000000"
        
        msg_frame = tk.Frame(self.frame, bg=self.trans_color)
        msg_frame.pack(fill="x", padx=10, pady=8)
        
        # 判断靠左还是靠右
        side = "right" if role == "user" else "left"
        
        # 留出左右边距来制造微信对话气泡那种长短效果
        pad_x = (50, 0) if role == "user" else (0, 50)
        
        bubble = tk.Label(
            msg_frame, 
            text=text, 
            bg=bg_color, 
            fg=fg_color, 
            font=self.custom_font, 
            wraplength=280, 
            justify="left",
            padx=14, 
            pady=10, 
            borderwidth=0
        )
        bubble.pack(side=side, padx=pad_x)
        
        # 稍微延迟触发滚动到底部
        self.after(50, lambda: self.canvas.yview_moveto(1.0))
        
    def show_system_msg(self, text):
        msg_frame = tk.Frame(self.frame, bg=self.trans_color)
        msg_frame.pack(fill="x", padx=10, pady=5)
        
        bubble = tk.Label(
            msg_frame, 
            text=text, 
            bg="#CECECE",    # 浅灰色背景
            fg="#444444",    # 深灰色文本
            font=self.sys_font, 
            wraplength=300, 
            padx=10, 
            pady=4, 
            borderwidth=0,
            relief="flat"
        )
        bubble.pack(side="top")
        self.after(50, lambda: self.canvas.yview_moveto(1.0))
        
    def handle_msg(self, role, text):
        self.recorder.log(role, text)
        # 确保 UI 相关更新能在主线程运行
        self.after(0, self.add_message_ui, role, text)

    def find_esp_port(self):
        ports = serial.tools.list_ports.comports()
        for port in ports:
            desc = port.description.upper()
            if "CH340" in desc or "CP210" in desc or "JTAG" in desc or "UART" in desc or "SERIAL" in desc:
                return port.device
        if ports:
            return ports[0].device
        return None

    def serial_worker(self):
        port_name = self.find_esp_port()
        if not port_name:
            self.after(0, self.show_system_msg, "未找到任何支持的串口设备\n请检查是否已连接开发板")
            return
            
        self.after(0, self.show_system_msg, f"正在监听串口: {port_name} (115200波特率) ...")
        
        user_pattern = re.compile(r">> (.+)")
        ai_pattern = re.compile(r"<< (.+)")
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        
        try:
            with serial.Serial(port_name, 115200, timeout=1) as ser:
                while self.running:
                    line = ser.readline()
                    if not line:
                        continue
                        
                    try:
                        text = line.decode('utf-8', errors='ignore').strip()
                        text = ansi_escape.sub('', text)
                        
                        user_match = user_pattern.search(text)
                        if user_match:
                            self.handle_msg("user", user_match.group(1).strip())
                            continue
                            
                        ai_match = ai_pattern.search(text)
                        if ai_match:
                            self.handle_msg("assistant", ai_match.group(1).strip())
                            continue
                            
                    except Exception:
                        pass
        except serial.SerialException as e:
            self.after(0, self.show_system_msg, "串口已断开连接！\n如果被占用，请先关闭其他串口调试软件\n提示：关闭窗口后重新启动本工具")

if __name__ == '__main__':
    app = App()
    app.mainloop()
