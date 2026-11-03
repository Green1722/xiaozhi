"""
小智 AI 对话记录器 (微信风格优化版)
"""
import sys
import time
from datetime import datetime
from pathlib import Path
import re
import threading
import tkinter as tk
from tkinter import font, Scrollbar, messagebox, simpledialog, filedialog
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import os
import shutil
import json

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("请先安装 pyserial: pip install pyserial")
    sys.exit(1)


class SerialPortSelector:
    """串口选择对话框"""
    def __init__(self, parent):
        self.parent = parent
        self.selected_port = None
        self.baudrate = 115200
        self.dialog = None
        
    def show(self):
        """显示串口选择对话框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("选择串口")
        self.dialog.geometry("450x350")
        self.dialog.resizable(False, False)
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # 居中显示
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (450 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (350 // 2)
        self.dialog.geometry(f"450x350+{x}+{y}")
        
        # 主框架
        main_frame = tk.Frame(self.dialog, bg="#F5F5F5", padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)
        
        # 标题
        title_label = tk.Label(
            main_frame,
            text="串口设置",
            font=font.Font(family="Microsoft YaHei", size=16, weight="bold"),
            bg="#F5F5F5",
            fg="#333333"
        )
        title_label.pack(pady=(0, 15))
        
        # 串口列表框架
        list_frame = tk.Frame(main_frame, bg="#FFFFFF", bd=1, relief="solid")
        list_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        # 创建列表框和滚动条
        scrollbar = Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.port_listbox = tk.Listbox(
            list_frame,
            font=font.Font(family="Microsoft YaHei", size=12),
            yscrollcommand=scrollbar.set,
            selectmode="single",
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg="#FFFFFF"
        )
        self.port_listbox.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.config(command=self.port_listbox.yview)
        
        # 填充串口列表
        self.refresh_ports()
        
        # 绑定双击事件
        self.port_listbox.bind("<Double-Button-1>", lambda e: self.on_confirm())
        
        # 波特率选择框架
        baud_frame = tk.Frame(main_frame, bg="#F5F5F5")
        baud_frame.pack(fill="x", pady=(0, 15))
        
        baud_label = tk.Label(
            baud_frame,
            text="波特率:",
            font=font.Font(family="Microsoft YaHei", size=12),
            bg="#F5F5F5",
            fg="#333333"
        )
        baud_label.pack(side="left")
        
        baudrates = ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]
        self.baudrate_var = tk.StringVar(value="115200")
        self.baudrate_combo = tk.ttk.Combobox(
            baud_frame,
            textvariable=self.baudrate_var,
            values=baudrates,
            width=10,
            state="readonly"
        )
        self.baudrate_combo.pack(side="left", padx=10)
        
        # 刷新按钮
        refresh_btn = tk.Button(
            baud_frame,
            text="刷新串口",
            font=font.Font(family="Microsoft YaHei", size=10),
            bg="#1890FF",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self.refresh_ports
        )
        refresh_btn.pack(side="right")
        
        # 按钮框架
        btn_frame = tk.Frame(main_frame, bg="#F5F5F5")
        btn_frame.pack(fill="x")
        
        # 取消按钮
        cancel_btn = tk.Button(
            btn_frame,
            text="取消",
            font=font.Font(family="Microsoft YaHei", size=12),
            bg="#FFFFFF",
            fg="#666666",
            relief="solid",
            bd=1,
            cursor="hand2",
            command=self.on_cancel,
            width=10
        )
        cancel_btn.pack(side="left", padx=(0, 10))
        
        # 确认按钮
        confirm_btn = tk.Button(
            btn_frame,
            text="连接",
            font=font.Font(family="Microsoft YaHei", size=12),
            bg="#52C41A",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self.on_confirm,
            width=10
        )
        confirm_btn.pack(side="right")
        
        # 尝试选中第一个
        if self.port_listbox.size() > 0:
            self.port_listbox.selection_set(0)
        
        self.dialog.protocol("WM_DELETE_WINDOW", self.on_cancel)
        
    def refresh_ports(self):
        """刷新串口列表"""
        self.port_listbox.delete(0, tk.END)
        ports = serial.tools.list_ports.comports()
        
        if not ports:
            self.port_listbox.insert(0, "未检测到串口设备")
            self.port_listbox.itemconfig(0, fg="#999999")
        else:
            for i, port in enumerate(ports):
                desc = port.description if port.description else "未知设备"
                # 特殊设备标记
                desc_upper = desc.upper()
                if any(kw in desc_upper for kw in ["CH340", "CP210", "JTAG", "UART", "SERIAL", "USB"]):
                    display_text = f"{port.device}  -  {desc}  ★"
                else:
                    display_text = f"{port.device}  -  {desc}"
                self.port_listbox.insert(tk.END, display_text)
        
        self.port_listbox.selection_clear(0, tk.END)
        if self.port_listbox.size() > 0:
            self.port_listbox.selection_set(0)
    
    def on_confirm(self):
        """确认选择"""
        selection = self.port_listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个串口", parent=self.dialog)
            return
            
        if self.port_listbox.get(0) == "未检测到串口设备":
            messagebox.showwarning("提示", "未检测到串口设备", parent=self.dialog)
            return
        
        try:
            port_text = self.port_listbox.get(selection[0])
            self.selected_port = port_text.split("  -  ")[0].strip()
            self.baudrate = int(self.baudrate_var.get())
        except Exception as e:
            messagebox.showerror("错误", f"解析串口信息失败: {str(e)}", parent=self.dialog)
            return
            
        self.dialog.destroy()
        
    def on_cancel(self):
        """取消选择"""
        self.selected_port = None
        self.dialog.destroy()

class AvatarGenerator:
    """头像生成器"""
    
    @staticmethod
    def create_default_avatar(role, size=40):
        """创建默认头像"""
        img = Image.new('RGBA', (size, size), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        
        # 背景颜色
        if role == "user":
            bg_color = (66, 133, 244)  # 蓝色
            emoji = "👤"
        elif role == "assistant":
            bg_color = (52, 168, 83)   # 绿色
            emoji = "🤖"
        else:
            bg_color = (158, 158, 158)  # 灰色
            emoji = "📝"
        
        # 绘制圆形背景
        draw.ellipse([(0, 0), (size, size)], fill=bg_color)
        
        # 尝试使用系统字体绘制emoji
        try:
            # Windows系统字体
            font = ImageFont.truetype("seguisym.ttf", size=size//2)
        except:
            try:
                # 其他系统字体
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size=size//2)
            except:
                # 使用默认字体
                font = ImageFont.load_default()
        
        # 获取文本边界框
        bbox = draw.textbbox((0, 0), emoji, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # 计算文字位置使其居中
        x = (size - text_width) // 2
        y = (size - text_height) // 2
        
        # 绘制文本
        draw.text((x, y), emoji, fill=(255, 255, 255), font=font)
        
        return img
    
    @staticmethod
    def load_custom_avatar(role, size=40):
        """加载自定义头像，如果没有则创建默认"""
        avatar_dir = Path("avatars")
        avatar_file = avatar_dir / f"{role}.png"
        
        if avatar_file.exists():
            try:
                img = Image.open(avatar_file)
                img = img.resize((size, size), Image.Resampling.LANCZOS)
                return img
            except Exception as e:
                print(f"加载头像失败: {e}")
        
        return AvatarGenerator.create_default_avatar(role, size)

class MessageWidget:
    """单个消息组件"""
    def __init__(self, parent, role, text, timestamp=None, avatar_size=40):
        self.parent = parent
        self.role = role
        self.text = text
        self.timestamp = timestamp or datetime.now()
        self.avatar_size = avatar_size
        
        self.frame = tk.Frame(parent, bg=parent['bg'])
        self.avatar_photo = None  # 保持头像引用
        self.create_widgets()
        
    def create_widgets(self):
        """创建消息组件"""
        self.frame.pack(fill="x", padx=10, pady=8)
        
        # 创建水平布局
        inner_frame = tk.Frame(self.frame, bg=self.frame['bg'])
        inner_frame.pack(fill="x")
        
        if self.role == "user":
            # 用户消息：头像在右侧，气泡在右侧
            # 左侧空白占位
            left_spacer = tk.Frame(inner_frame, bg=inner_frame['bg'])
            left_spacer.pack(side="left", expand=True, fill="x")
            
            # 气泡和头像容器（右侧）
            right_container = tk.Frame(inner_frame, bg=inner_frame['bg'])
            right_container.pack(side="right")
            
            # 先放气泡，再放头像（这样头像就在气泡右侧）
            self.create_bubble(right_container, side="right", pack_side="left")
            self.create_avatar(right_container, side="right", pack_side="right")
            
        else:
            # AI消息：头像在左侧，气泡在左侧
            left_container = tk.Frame(inner_frame, bg=inner_frame['bg'])
            left_container.pack(side="left")
            
            # 先放头像，再放气泡（头像在气泡左侧）
            self.create_avatar(left_container, side="left", pack_side="left")
            self.create_bubble(left_container, side="left", pack_side="left")
            
            # 右侧空白占位
            right_spacer = tk.Frame(inner_frame, bg=inner_frame['bg'])
            right_spacer.pack(side="right", expand=True, fill="x")
            
    def create_avatar(self, parent, side, pack_side):
        """创建头像"""
        avatar_frame = tk.Frame(parent, bg=parent['bg'])
        avatar_frame.pack(side=pack_side, padx=(5 if side == "left" else 0, 5 if side == "right" else 0))
        
        # 加载头像
        img = AvatarGenerator.load_custom_avatar(self.role, self.avatar_size)
        self.avatar_photo = ImageTk.PhotoImage(img)
        
        avatar_label = tk.Label(avatar_frame, image=self.avatar_photo, bg=parent['bg'])
        avatar_label.image = self.avatar_photo  # 保持引用
        avatar_label.pack()
        
        # 添加名称标签
        name = "我" if self.role == "user" else "小智AI"
        name_label = tk.Label(
            avatar_frame, 
            text=name, 
            font=font.Font(family="Microsoft YaHei", size=10),
            bg=parent['bg'],
            fg="#666666"
        )
        name_label.pack(pady=(2, 0))
        
    def create_bubble(self, parent, side, pack_side):
        """创建聊天气泡"""
        bubble_frame = tk.Frame(parent, bg=parent['bg'])
        bubble_frame.pack(side=pack_side, padx=8)
        
        # 气泡颜色和对齐方式
        if self.role == "user":
            bg_color = "#95EC69"  # 微信绿
            fg_color = "#000000"
            text_align = "right"
        else:
            bg_color = "#FFFFFF"  # 白色
            fg_color = "#000000"
            text_align = "left"
        
        # 创建气泡标签
        bubble = tk.Label(
            bubble_frame,
            text=self.text,
            bg=bg_color,
            fg=fg_color,
            font=font.Font(family="Microsoft YaHei", size=16),
            wraplength=280,
            justify=text_align,
            padx=14,
            pady=10,
            borderwidth=0,
            relief="flat"
        )
        bubble.pack()
        
        # 添加时间戳
        time_str = self.timestamp.strftime("%H:%M")
        time_label = tk.Label(
            bubble_frame,
            text=time_str,
            font=font.Font(family="Microsoft YaHei", size=8),
            bg=parent['bg'],
            fg="#999999"
        )
        time_label.pack(anchor="e" if self.role == "user" else "w", pady=(2, 0))


def get_config_path():
    """获取配置文件路径（放在exe同目录下，exe部署后也能读写）"""
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys.executable).parent
    else:
        base_dir = Path.cwd()
    return base_dir / "serial_config.json"


def load_serial_config():
    """加载上次保存的串口配置"""
    config_path = get_config_path()
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                return cfg.get('port'), cfg.get('baudrate', 115200)
        except Exception:
            pass
    return None, 115200


def save_serial_config(port, baudrate):
    """保存当前串口配置"""
    config_path = get_config_path()
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump({'port': port, 'baudrate': baudrate}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class ChatRecorder:
    """聊天记录器 - 还原原有功能"""
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
        self.geometry("450x700")
        self.attributes('-topmost', True)
        
        # 设置背景色（微信聊天背景）
        self.bg_color = "#EDEDED"
        self.configure(bg=self.bg_color)
        
        # 创建主布局
        self.create_main_layout()
        
        # 创建菜单栏
        self.create_menu()
        
        # 初始化组件
        self.init_components()
        
        # 启动串口监听
        self.start_serial_listener()
        
        # 窗口关闭事件
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def create_main_layout(self):
        """创建主布局"""
        # 顶部工具栏
        self.toolbar = tk.Frame(self, bg="#F5F5F5", height=60)
        self.toolbar.pack(fill="x", side="top")
        self.toolbar.pack_propagate(False)
        
        # 工具栏内容
        title_label = tk.Label(
            self.toolbar,
            text="小智AI对话",
            font=font.Font(family="Microsoft YaHei", size=16, weight="bold"),
            bg="#F5F5F5",
            fg="#333333"
        )
        title_label.pack(side="left", padx=15, pady=15)
        
        # 在线状态指示
        self.status_label = tk.Label(
            self.toolbar,
            text="● 未连接",
            font=font.Font(family="Microsoft YaHei", size=10),
            bg="#F5F5F5",
            fg="#FF4D4F"
        )
        self.status_label.pack(side="right", padx=5)
        
        # 串口选择按钮
        serial_btn = tk.Button(
            self.toolbar,
            text="选择串口 ▼",
            font=font.Font(family="Microsoft YaHei", size=10),
            bg="#1890FF",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self.show_serial_selector
        )
        serial_btn.pack(side="right", padx=5, pady=10)
        
        # 聊天区域框架
        chat_frame = tk.Frame(self, bg=self.bg_color)
        chat_frame.pack(fill="both", expand=True)
        
        # 画布和滚动条
        self.canvas = tk.Canvas(chat_frame, bg=self.bg_color, highlightthickness=0)
        self.scrollbar = Scrollbar(chat_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        
        # 内部框架用于放置消息
        self.message_frame = tk.Frame(self.canvas, bg=self.bg_color)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.message_frame, anchor="nw")
        
        self.message_frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        
        # 绑定滚轮事件
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_mousewheel)
        self.bind_all("<Button-5>", self._on_mousewheel)
        
        # 底部控制栏
        self.control_bar = tk.Frame(self, bg="#F5F5F5", height=50)
        self.control_bar.pack(fill="x", side="bottom")
        self.control_bar.pack_propagate(False)
        
        # 自动滚动复选框
        self.auto_scroll = tk.BooleanVar(value=True)
        auto_scroll_cb = tk.Checkbutton(
            self.control_bar,
            text="自动滚动",
            variable=self.auto_scroll,
            bg="#F5F5F5",
            font=font.Font(family="Microsoft YaHei", size=10),
            command=self.on_auto_scroll_toggle
        )
        auto_scroll_cb.pack(side="left", padx=15, pady=15)
        
        # 清除聊天记录按钮
        clear_btn = tk.Button(
            self.control_bar,
            text="清除记录",
            font=font.Font(family="Microsoft YaHei", size=10),
            bg="#FF6B6B",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self.clear_messages
        )
        clear_btn.pack(side="right", padx=15, pady=10)
        
        # 导出聊天记录按钮
        export_btn = tk.Button(
            self.control_bar,
            text="导出记录",
            font=font.Font(family="Microsoft YaHei", size=10),
            bg="#4CAF50",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self.export_chat_log
        )
        export_btn.pack(side="right", padx=10, pady=10)
        
    def create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="导出聊天记录", command=self.export_chat_log)
        file_menu.add_command(label="清除聊天记录", command=self.clear_messages)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.on_closing)
        
        # 设置菜单
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=settings_menu)
        settings_menu.add_command(label="选择串口", command=self.show_serial_selector)
        settings_menu.add_command(label="更换头像", command=self.change_avatar)
        settings_menu.add_separator()
        settings_menu.add_command(label="断开串口", command=self.disconnect_serial)
        settings_menu.add_command(label="重新连接", command=self.reconnect_serial)
        settings_menu.add_command(label="重新检测设备", command=self.manual_reconnect)
        settings_menu.add_separator()
        
        # 自动重连开关
        self.auto_reconnect_var = tk.BooleanVar(value=True)
        settings_menu.add_checkbutton(
            label="自动重连",
            variable=self.auto_reconnect_var,
            command=self.toggle_auto_reconnect
        )
        
        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="关于", command=self.show_about)
        
    def init_components(self):
        """初始化组件"""
        self.recorder = ChatRecorder()
        self.recorder.open_file()
        self.running = True
        self.messages = []  # 存储消息组件
        
        # 串口相关初始化
        self.serial_ser = None
        self.serial_connected = False
        self.current_port = None
        self.current_baudrate = 115200

        # 自动重连相关初始化
        self.reconnect_attempts = 0      # 重连尝试次数
        self.max_reconnect_attempts = 10  # 最大重连次数
        self.reconnect_delay = 2          # 重连延迟（秒）
        self.auto_reconnect = True        # 是否自动重连
        self.auto_reconnect_var = tk.BooleanVar(value=True)  # 菜单绑定变量
        self.reconnect_in_progress = False  # 重连是否正在进行
        self.last_known_port = None       # 上次连接的串口
        self.port_monitor_running = True  # 热插拔检测线程运行标志
        self.known_ports = set()          # 已知的串口列表

        # 加载上次保存的串口配置
        saved_port, saved_baudrate = load_serial_config()
        if saved_port:
            self.current_port = saved_port
            self.current_baudrate = saved_baudrate
        
        # 字体设置
        self.message_font = font.Font(family="Microsoft YaHei", size=16)
        self.sys_font = font.Font(family="Microsoft YaHei", size=9)
        
        # 启动热插拔检测线程
        self.port_monitor_thread = threading.Thread(target=self.port_monitor_worker, daemon=True)
        self.port_monitor_thread.start()
        
        # 欢迎消息
#        self.show_system_message("✨ 小智AI对话系统已启动 ✨")
 #       self.show_system_message("💡 提示：可以向上滚动查看历史消息")
  #      self.show_system_message(f"📁 日志文件: {self.recorder.txt_file}")
        
    def start_serial_listener(self):
        """启动串口监听线程"""
        # 如果有上次保存的配置，自动尝试连接
        if self.current_port:
            self.show_system_message(f"正在恢复上次串口: {self.current_port} @ {self.current_baudrate}...")
        self.serial_thread = threading.Thread(target=self.serial_worker, daemon=True)
        self.serial_thread.start()
    
    def port_monitor_worker(self):
        """热插拔检测线程 - 实时监控串口设备的插入和拔出"""
        while self.port_monitor_running:
            try:
                current_ports = set(p.device for p in serial.tools.list_ports.comports())
                
                # 检测串口拔出（之前有，现在没了）
                if self.last_known_port and self.last_known_port not in current_ports:
                    if self.serial_connected and not self.reconnect_in_progress:
                        self.after(0, self.show_system_message, f"⚠️ 串口设备 {self.last_known_port} 已断开")
                        self.after(0, lambda: self.status_label.config(text="● 连接中断", fg="#FFA500"))
                        # 自动触发重连
                        if self.auto_reconnect:
                            self.after(0, self.schedule_reconnect)
                
                # 检测到新的串口设备（可能是同一个设备重新插入）
                if current_ports - self.known_ports:
                    new_ports = current_ports - self.known_ports
                    for new_port in new_ports:
                        # 检查是否是之前使用的端口
                        if self.last_known_port == new_port or not self.current_port:
                            if self.auto_reconnect and not self.serial_connected and not self.reconnect_in_progress:
                                self.after(0, self.show_system_message, f"🔌 检测到串口设备 {new_port}，准备自动连接...")
                                self.after(0, self.schedule_reconnect)
                                break
                
                self.known_ports = current_ports
                
            except Exception:
                pass
            
            # 每秒检测一次
            time.sleep(1)
    
    def schedule_reconnect(self):
        """安排自动重连（延迟执行，避免频繁重连）"""
        if self.reconnect_in_progress:
            return
        
        self.reconnect_in_progress = True
        self.reconnect_attempts = 0
        
        # 延迟1秒后开始重连
        self.after(1000, lambda: self._do_auto_reconnect_inner())
    
    def _do_auto_reconnect_inner(self):
        """执行自动重连"""
        if not self.auto_reconnect or not self.running:
            self.reconnect_in_progress = False
            return
        
        # 如果已经连接成功，不再重连
        if self.serial_connected and self.serial_ser and self.serial_ser.is_open:
            self.reconnect_in_progress = False
            self.reconnect_attempts = 0
            return
        
        # 检查是否达到最大重连次数
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            self.after(0, self.show_system_message, f"已达最大重连次数({self.max_reconnect_attempts})，请手动检查设备连接")
            self.after(0, lambda: self.status_label.config(text="● 重连失败", fg="#FF4D4F"))
            self.reconnect_in_progress = False
            return
        
        # 检查当前是否有可用串口
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            self.reconnect_attempts += 1
            delay = min(5, self.reconnect_delay * (1 + self.reconnect_attempts // 3))
            self.after(0, lambda: self.status_label.config(text=f"● 等待设备 ({self.reconnect_attempts}/{self.max_reconnect_attempts})", fg="#FFA500"))
            self.after(int(delay * 1000), lambda: self._do_auto_reconnect_inner())
            return
        
        # 优先使用上次连接的端口
        target_port = None
        if self.last_known_port:
            for port in ports:
                if port.device == self.last_known_port:
                    target_port = self.last_known_port
                    break
        
        # 如果上次端口不可用，尝试自动查找
        if not target_port:
            target_port = self.find_esp_port()
        
        if not target_port:
            self.reconnect_attempts += 1
            delay = min(5, self.reconnect_delay * (1 + self.reconnect_attempts // 3))
            self.after(int(delay * 1000), lambda: self._do_auto_reconnect_inner())
            return
        
        # 尝试连接到串口
        self.reconnect_attempts += 1
        self.after(0, lambda: self.status_label.config(text=f"● 重连中 ({self.reconnect_attempts}/{self.max_reconnect_attempts})", fg="#FFA500"))
        self.after(0, self.show_system_message, f"正在尝试连接 {target_port} ({self.reconnect_attempts}/{self.max_reconnect_attempts})...")
        
        try:
            # 尝试打开串口
            test_ser = serial.Serial(target_port, self.current_baudrate, timeout=1)
            test_ser.close()
            
            # 串口可用，更新状态并触发重连
            self.current_port = target_port
            self.after(0, self.show_system_message, f"✅ 找到可用串口 {target_port}，正在连接...")
            
            # 重置重连状态，让 serial_worker 开始连接
            self.reconnect_attempts = 0
            self.reconnect_in_progress = False
            
            # 重新启动串口监听线程
            self.running = False
            time.sleep(0.2)
            self.running = True
            self.serial_thread = threading.Thread(target=self.serial_worker, daemon=True)
            self.serial_thread.start()
            
        except serial.SerialException:
            # 串口仍然不可用，继续重连
            delay = min(5, self.reconnect_delay * (1 + self.reconnect_attempts // 3))
            self.after(int(delay * 1000), lambda: self._do_auto_reconnect_inner())
        
    def on_auto_scroll_toggle(self):
        """自动滚动切换"""
        if self.auto_scroll.get():
            self.scroll_to_bottom()
            
    def scroll_to_bottom(self):
        """滚动到底部"""
        self.canvas.yview_moveto(1.0)
        
    def check_and_scroll(self):
        """检查是否需要自动滚动"""
        if self.auto_scroll.get():
            self.scroll_to_bottom()
            
    def _on_mousewheel(self, event):
        """处理鼠标滚轮事件"""
        # 如果用户向上滚动，暂时关闭自动滚动
        if hasattr(event, 'delta'):
            if event.delta > 0:  # 向上滚动
                self.auto_scroll.set(False)
            else:  # 向下滚动
                if self.is_at_bottom():
                    self.auto_scroll.set(True)
        elif hasattr(event, 'num'):
            if event.num == 4:  # 向上滚动
                self.auto_scroll.set(False)
            elif event.num == 5:  # 向下滚动
                if self.is_at_bottom():
                    self.auto_scroll.set(True)
        
        # 执行滚动
        if hasattr(event, 'delta'):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        elif hasattr(event, 'num'):
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")
                
    def is_at_bottom(self):
        """检查是否在底部"""
        current_pos = self.canvas.yview()[1]
        return current_pos >= 0.99
        
    def on_frame_configure(self, event):
        """框架大小改变时更新滚动区域"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if self.auto_scroll.get():
            self.after(10, self.scroll_to_bottom)
            
    def on_canvas_configure(self, event):
        """画布大小改变时调整内部框架宽度"""
        self.canvas.itemconfig(self.canvas_window, width=event.width)
        
    def add_message(self, role, text, timestamp=None):
        """添加消息"""
        if timestamp is None:
            timestamp = datetime.now()
            
        # 创建消息组件
        msg_widget = MessageWidget(
            self.message_frame,
            role,
            text,
            timestamp,
            avatar_size=40
        )
        
        # 存储消息组件
        self.messages.append(msg_widget)
        
        # 记录到文件
        self.recorder.log(role, text)
        
        # 滚动到底部
        self.after(50, self.check_and_scroll)
        
    def show_system_message(self, text):
        """显示系统消息"""
        sys_frame = tk.Frame(self.message_frame, bg=self.bg_color)
        sys_frame.pack(fill="x", padx=10, pady=5)
        
        sys_label = tk.Label(
            sys_frame,
            text=f"  {text}  ",
            bg="#E0E0E0",
            fg="#666666",
            font=self.sys_font,
            padx=10,
            pady=5,
            relief="flat"
        )
        sys_label.pack(pady=2)
        
        self.after(50, self.check_and_scroll)
        
    def clear_messages(self):
        """清除所有消息"""
        if messagebox.askyesno("确认", "确定要清除所有聊天记录吗？"):
            for widget in self.message_frame.winfo_children():
                widget.destroy()
            self.messages.clear()
            self.show_system_message("聊天记录已清空")
        
    def export_chat_log(self):
        """导出聊天记录"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile=f"chat_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write("小智AI对话记录\n")
                    f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("="*50 + "\n\n")
                    
                    for msg in self.messages:
                        time_str = msg.timestamp.strftime("%H:%M:%S")
                        name = "我" if msg.role == "user" else "小智AI"
                        f.write(f"[{time_str}] {name}: {msg.text}\n")
                        
                messagebox.showinfo("导出成功", f"聊天记录已导出到:\n{filename}")
            except Exception as e:
                messagebox.showerror("导出失败", f"导出失败: {str(e)}")
                
    def change_avatar(self):
        """更换头像"""
        role = simpledialog.askstring("选择角色", "更换哪个角色的头像？\n输入 'user' 或 'assistant'")
        if role not in ['user', 'assistant']:
            messagebox.showwarning("输入错误", "角色输入错误，请输入 user 或 assistant")
            return
            
        filename = filedialog.askopenfilename(
            title=f"选择{role}的头像",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.gif"), ("所有文件", "*.*")]
        )
        
        if filename:
            avatar_dir = Path("avatars")
            avatar_dir.mkdir(exist_ok=True)
            
            try:
                shutil.copy2(filename, avatar_dir / f"{role}.png")
                messagebox.showinfo("成功", f"{role}头像已更新，重启程序后生效")
            except Exception as e:
                messagebox.showerror("失败", f"更新头像失败: {str(e)}")
            
    def show_about(self):
        """显示关于对话框"""
        about_text = """小智AI对话助手 v2.0

一个基于ESP32的智能对话系统
支持实时串口通信和聊天记录保存

功能特点：
• 微信风格界面
• 自定义头像
• 聊天记录导出
• 实时对话显示
• 历史消息滚动

日志保存在: chat_logs/日期/ 目录下
控制台也会输出聊天记录

© 2024 小智AI团队
"""
        messagebox.showinfo("关于", about_text)
        
    def show_serial_selector(self):
        """显示串口选择对话框"""
        selector = SerialPortSelector(self)
        selector.show()
        self.dialog_wait(selector.dialog)
        
        if selector.selected_port:
            self.current_port = selector.selected_port
            self.current_baudrate = selector.baudrate
            save_serial_config(self.current_port, self.current_baudrate)
            self.reconnect_serial()
    
    def dialog_wait(self, dialog):
        """等待对话框关闭"""
        dialog.wait_window()
        
    def disconnect_serial(self):
        """断开串口连接"""
        self.serial_connected = False
        if hasattr(self, 'serial_ser') and self.serial_ser and self.serial_ser.is_open:
            try:
                self.serial_ser.close()
            except:
                pass
        self.status_label.config(text="● 已断开", fg="#FF4D4F")
        self.show_system_message("串口已断开连接")
        
    def reconnect_serial(self):
        """重新连接串口（手动重连）"""
        if not hasattr(self, 'current_port') or not self.current_port:
            self.show_serial_selector()
            return
        
        # 重置重连状态
        self.reconnect_in_progress = False
        self.reconnect_attempts = 0
        
        self.running = False
        import time
        time.sleep(0.2)
        
        # 重新启动串口监听
        self.running = True
        self.show_system_message(f"正在连接到 {self.current_port} @ {self.current_baudrate}...")
        
        # 停止旧线程
        if hasattr(self, 'serial_thread') and self.serial_thread.is_alive():
            self.serial_thread.join(timeout=0.5)
        
        # 启动新线程
        self.serial_thread = threading.Thread(target=self.serial_worker, daemon=True)
        self.serial_thread.start()
    
    def manual_reconnect(self):
        """手动触发重新检测和连接（强制重新检测所有串口）"""
        self.reconnect_in_progress = False
        self.reconnect_attempts = 0
        
        self.show_system_message("正在重新检测串口设备...")
        
        # 重新检测所有可用串口
        ports = self.get_all_ports()
        if not ports:
            self.show_system_message("未检测到任何串口设备，请检查连接")
            self.status_label.config(text="● 未检测到设备", fg="#FF4D4F")
            return
        
        # 尝试连接第一个可用串口
        port_name, port_desc = ports[0]
        self.current_port = port_name
        self.show_system_message(f"找到设备: {port_name} ({port_desc})，正在连接...")
        
        # 重新启动连接
        self.reconnect_serial()
    
    def toggle_auto_reconnect(self):
        """切换自动重连开关"""
        self.auto_reconnect = self.auto_reconnect_var.get()
        if self.auto_reconnect:
            self.show_system_message("✅ 自动重连已开启")
        else:
            self.show_system_message("❌ 自动重连已关闭")
        
    def handle_msg(self, role, text):
        """处理消息"""
        self.after(0, self.add_message, role, text)
        
    def find_esp_port(self):
        """查找ESP32串口"""
        ports = serial.tools.list_ports.comports()
        for port in ports:
            desc = port.description.upper() if port.description else ""
            # 扩展关键词匹配，包括中文描述
            keywords = ["CH340", "CP210", "JTAG", "UART", "SERIAL", "USB", "ESP32", "SILICON", "FTDI"]
            if any(kw in desc for kw in keywords):
                return port.device
        if ports:
            return ports[0].device
        return None
        
    def get_all_ports(self):
        """获取所有可用串口"""
        ports = serial.tools.list_ports.comports()
        return [(p.device, p.description) for p in ports]
        
    def serial_worker(self):
        """串口监听工作线程"""
        # 如果有用户选择的串口，优先使用
        if hasattr(self, 'current_port') and self.current_port:
            port_name = self.current_port
            baudrate = getattr(self, 'current_baudrate', 115200)
        else:
            port_name = self.find_esp_port()
            baudrate = 115200
            
        if not port_name:
            self.after(0, self.show_system_message, "未找到串口设备，请检查连接或手动选择串口")
            self.after(0, lambda: self.status_label.config(text="● 离线", fg="#FF4D4F"))
            self.serial_connected = False
            # 自动重连
            if self.auto_reconnect:
                self.after(0, self.schedule_reconnect)
            return
        
        # 保存当前端口为上次连接的端口
        self.last_known_port = port_name
        self.serial_connected = True
        self.after(0, self.show_system_message, f"已连接到串口: {port_name} ({baudrate}波特率)")
        self.after(0, lambda: self.status_label.config(text="● 在线", fg="#52C41A"))
        
        user_pattern = re.compile(r">>\s*(.+)")
        ai_pattern = re.compile(r"<<\s*(.+)")
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        
        try:
            self.serial_ser = serial.Serial(port_name, baudrate, timeout=1)
            # 成功连接后保存配置
            self.current_port = port_name
            self.current_baudrate = baudrate
            save_serial_config(port_name, baudrate)
            while self.running and self.serial_connected:
                if not self.serial_ser or not self.serial_ser.is_open:
                    break
                line = self.serial_ser.readline()
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
                
                # 更新已知端口
                self.last_known_port = port_name
                
            if self.serial_ser and self.serial_ser.is_open:
                try:
                    self.serial_ser.close()
                except:
                    pass
                
            # 连接正常退出（非用户主动断开）
            if self.running and self.serial_connected:
                self.serial_connected = False
                self.after(0, self.show_system_message, "⚠️ 串口连接意外断开，正在尝试重连...")
                self.after(0, lambda: self.status_label.config(text="● 连接中断", fg="#FFA500"))
                if self.auto_reconnect:
                    self.after(0, self.schedule_reconnect)
            elif not self.serial_connected and self.running:
                # 可能是被断开了，尝试重连
                self.after(0, self.show_system_message, "⚠️ 串口连接丢失，正在尝试重连...")
                if self.auto_reconnect:
                    self.after(0, self.schedule_reconnect)
                
        except serial.SerialException as e:
            self.serial_connected = False
            error_msg = str(e)
            self.after(0, self.show_system_message, f"⚠️ 串口连接断开: {error_msg}")
            self.after(0, lambda: self.status_label.config(text="● 连接中断", fg="#FFA500"))
            # 自动重连
            if self.auto_reconnect:
                self.after(0, self.schedule_reconnect)
            
    def on_closing(self):
        """关闭窗口"""
        if messagebox.askokcancel("退出", "确定要退出程序吗？"):
            # 停止所有线程
            self.running = False
            self.serial_connected = False
            self.auto_reconnect = False
            self.port_monitor_running = False
            
            # 关闭串口
            if hasattr(self, 'serial_ser') and self.serial_ser and self.serial_ser.is_open:
                try:
                    self.serial_ser.close()
                except:
                    pass
            
            # 等待线程结束（最多2秒）
            if hasattr(self, 'serial_thread') and self.serial_thread.is_alive():
                self.serial_thread.join(timeout=2)
            if hasattr(self, 'port_monitor_thread') and self.port_monitor_thread.is_alive():
                self.port_monitor_thread.join(timeout=2)

            # 保存当前串口配置
            port_to_save = getattr(self, 'last_known_port', None) or getattr(self, 'current_port', None)
            if port_to_save:
                save_serial_config(port_to_save, getattr(self, 'current_baudrate', 115200))

            self.recorder.close()
            self.destroy()

if __name__ == '__main__':
    # 检查PIL库
    try:
        from PIL import Image, ImageTk, ImageDraw, ImageFont
    except ImportError:
        print("请先安装 Pillow 库: pip install Pillow")
        sys.exit(1)
        
    app = App()
    app.mainloop()