# reminder_service.py - 小智定时提醒MCP服务
# 支持：添加/查看/删除提醒，定时触发，WebSocket通信

from mcp.server.fastmcp import FastMCP
import sys
import logging
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Tuple, Dict, Any
import uuid
import re

# ==================== 日志配置 ====================
logger = logging.getLogger('ReminderService')

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
mcp = FastMCP("ReminderService")


# ==================== 数据模型 ====================

class ReminderStatus(Enum):
    """提醒状态枚举"""
    PENDING = "pending"      # 等待触发
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 发送失败
    CANCELLED = "cancelled"  # 已取消


@dataclass
class Reminder:
    """提醒数据类"""
    content: str
    trigger_time: datetime
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: ReminderStatus = ReminderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'id': self.id,
            'content': self.content,
            'trigger_time': self.trigger_time.strftime('%Y-%m-%d %H:%M:%S'),
            'status': self.status.value,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'error_message': self.error_message
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Reminder':
        """从字典反序列化"""
        return cls(
            id=data['id'],
            content=data['content'],
            trigger_time=datetime.strptime(data['trigger_time'], '%Y-%m-%d %H:%M:%S'),
            status=ReminderStatus(data['status']),
            created_at=datetime.strptime(data['created_at'], '%Y-%m-%d %H:%M:%S'),
            error_message=data.get('error_message')
        )


# ==================== 时间解析 ====================

def parse_trigger_time(time_str: str) -> datetime:
    """解析触发时间字符串
    
    支持两种格式：
    1. 绝对时间: "YYYY-MM-DD HH:MM:SS"
    2. 相对时间: "+5m" (5分钟后), "+1h" (1小时后), "+30s" (30秒后)
    
    Args:
        time_str: 时间字符串
        
    Returns:
        datetime对象
        
    Raises:
        ValueError: 时间格式无效
    """
    time_str = time_str.strip()
    
    if time_str.startswith('+'):
        # 相对时间格式: +5m, +1h, +30s
        match = re.match(r'^\+(\d+)([smh])$', time_str)
        if not match:
            raise ValueError(f"Invalid relative time format: {time_str}. Expected format: +<number><s|m|h>")
        
        value = int(match.group(1))
        unit = match.group(2)
        
        delta_map = {
            's': timedelta(seconds=value),
            'm': timedelta(minutes=value),
            'h': timedelta(hours=value)
        }
        
        return datetime.now() + delta_map[unit]
    else:
        # 绝对时间格式: YYYY-MM-DD HH:MM:SS
        try:
            return datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            raise ValueError(f"Invalid absolute time format: {time_str}. Expected format: YYYY-MM-DD HH:MM:SS")


# ==================== 存储层 ====================

import threading

class ReminderStore:
    """内存存储，管理提醒事项
    
    使用字典存储，线程安全
    """
    
    def __init__(self):
        self._reminders: Dict[str, Reminder] = {}
        self._lock = threading.RLock()
    
    def add(self, reminder: Reminder) -> str:
        """添加提醒，返回ID
        
        Args:
            reminder: 提醒对象
            
        Returns:
            提醒ID
        """
        with self._lock:
            self._reminders[reminder.id] = reminder
            return reminder.id
    
    def get(self, reminder_id: str) -> Optional[Reminder]:
        """根据ID获取提醒
        
        Args:
            reminder_id: 提醒ID
            
        Returns:
            提醒对象，不存在则返回None
        """
        with self._lock:
            return self._reminders.get(reminder_id)
    
    def remove(self, reminder_id: str) -> bool:
        """删除提醒，返回是否成功
        
        Args:
            reminder_id: 提醒ID
            
        Returns:
            是否删除成功
        """
        with self._lock:
            if reminder_id in self._reminders:
                del self._reminders[reminder_id]
                return True
            return False
    
    def list_pending(self) -> List[Reminder]:
        """获取所有待触发的提醒，按时间排序
        
        Returns:
            按trigger_time升序排列的待触发提醒列表
        """
        with self._lock:
            pending = [
                r for r in self._reminders.values() 
                if r.status == ReminderStatus.PENDING
            ]
            return sorted(pending, key=lambda r: r.trigger_time)
    
    def update_status(self, reminder_id: str, status: ReminderStatus, error: str = None) -> bool:
        """更新提醒状态
        
        Args:
            reminder_id: 提醒ID
            status: 新状态
            error: 错误信息（可选）
            
        Returns:
            是否更新成功
        """
        with self._lock:
            reminder = self._reminders.get(reminder_id)
            if reminder:
                reminder.status = status
                if error:
                    reminder.error_message = error
                return True
            return False
    
    def size(self) -> int:
        """获取存储的提醒数量
        
        Returns:
            提醒数量
        """
        with self._lock:
            return len(self._reminders)
    
    def clear(self) -> None:
        """清空所有提醒"""
        with self._lock:
            self._reminders.clear()


# ==================== 消息格式化 ====================

def format_wake_message() -> str:
    """格式化唤醒消息
    
    Returns:
        JSON格式的唤醒消息字符串
    """
    message = {
        "action": "wake",
        "timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    }
    return json.dumps(message, ensure_ascii=False)


def format_reminder_message(content: str) -> str:
    """格式化提醒消息
    
    Args:
        content: 提醒内容
        
    Returns:
        JSON格式的提醒消息字符串
    """
    message = {
        "action": "reminder",
        "content": content,
        "timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    }
    return json.dumps(message, ensure_ascii=False)


# ==================== 通信层 ====================

import asyncio
import os

try:
    import websockets
    from websockets.exceptions import ConnectionClosed, WebSocketException
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    logger.warning("websockets库未安装，WebSocket功能不可用")


# ==================== 调度层 ====================

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.jobstores.base import JobLookupError
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("apscheduler库未安装，定时调度功能不可用")


class ReminderScheduler:
    """定时调度器，使用APScheduler
    
    负责在指定时间触发提醒回调
    """
    
    def __init__(self):
        """初始化调度器"""
        self._scheduler = None
        self._running = False
        
        if APSCHEDULER_AVAILABLE:
            self._scheduler = AsyncIOScheduler()
        else:
            logger.warning("APScheduler不可用，调度功能将被禁用")
    
    @property
    def is_running(self) -> bool:
        """检查调度器是否正在运行"""
        return self._running and self._scheduler is not None
    
    def start(self) -> bool:
        """启动调度器
        
        Returns:
            是否启动成功
        """
        if not APSCHEDULER_AVAILABLE or self._scheduler is None:
            logger.error("APScheduler不可用，无法启动调度器")
            return False
        
        if self._running:
            logger.warning("调度器已在运行中")
            return True
        
        try:
            self._scheduler.start()
            self._running = True
            logger.info("调度器已启动")
            return True
        except Exception as e:
            logger.error(f"启动调度器失败: {e}")
            return False
    
    def stop(self) -> bool:
        """停止调度器
        
        Returns:
            是否停止成功
        """
        if not self._running or self._scheduler is None:
            logger.warning("调度器未在运行")
            return True
        
        try:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("调度器已停止")
            return True
        except Exception as e:
            logger.error(f"停止调度器失败: {e}")
            return False
    
    def schedule(self, reminder: Reminder, callback) -> bool:
        """注册定时任务
        
        Args:
            reminder: 提醒对象
            callback: 触发时调用的回调函数，接收reminder_id参数
            
        Returns:
            是否注册成功
        """
        if not APSCHEDULER_AVAILABLE or self._scheduler is None:
            logger.error("APScheduler不可用，无法注册定时任务")
            return False
        
        if not self._running:
            logger.error("调度器未启动，无法注册定时任务")
            return False
        
        try:
            # 使用DateTrigger在指定时间触发一次
            trigger = DateTrigger(run_date=reminder.trigger_time)
            
            self._scheduler.add_job(
                callback,
                trigger=trigger,
                id=reminder.id,
                args=[reminder.id],
                name=f"reminder_{reminder.id}",
                replace_existing=True
            )
            
            logger.info(f"已注册定时任务: {reminder.id} -> {reminder.trigger_time}")
            return True
        except Exception as e:
            logger.error(f"注册定时任务失败: {e}")
            return False
    
    def cancel(self, reminder_id: str) -> bool:
        """取消定时任务
        
        Args:
            reminder_id: 提醒ID
            
        Returns:
            是否取消成功
        """
        if not APSCHEDULER_AVAILABLE or self._scheduler is None:
            logger.error("APScheduler不可用，无法取消定时任务")
            return False
        
        try:
            self._scheduler.remove_job(reminder_id)
            logger.info(f"已取消定时任务: {reminder_id}")
            return True
        except JobLookupError:
            logger.warning(f"定时任务不存在: {reminder_id}")
            return False
        except Exception as e:
            logger.error(f"取消定时任务失败: {e}")
            return False
    
    def get_pending_jobs_count(self) -> int:
        """获取待执行的任务数量
        
        Returns:
            待执行任务数量
        """
        if not self._scheduler or not self._running:
            return 0
        
        try:
            jobs = self._scheduler.get_jobs()
            return len(jobs)
        except Exception:
            return 0


# ==================== 通信层 ====================

class XiaozhiClient:
    """WebSocket客户端，与小智服务器通信
    
    支持连接管理、消息发送、自动重连
    """
    
    # 默认WebSocket端点
    DEFAULT_ENDPOINT = "ws://localhost:8080"
    
    # 重连配置
    MAX_RECONNECT_ATTEMPTS = 5
    INITIAL_RECONNECT_DELAY = 1.0  # 秒
    MAX_RECONNECT_DELAY = 30.0  # 秒
    
    def __init__(self, endpoint: str = None):
        """初始化客户端
        
        Args:
            endpoint: WebSocket端点URL，默认从环境变量XIAOZHI_WS_ENDPOINT获取
        """
        self._endpoint = endpoint or os.environ.get('XIAOZHI_WS_ENDPOINT', self.DEFAULT_ENDPOINT)
        self._websocket = None
        self._connected = False
        self._lock = asyncio.Lock()
        self._reconnect_attempts = 0
        
    @property
    def endpoint(self) -> str:
        """获取WebSocket端点"""
        return self._endpoint
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected and self._websocket is not None
    
    async def connect(self) -> bool:
        """建立WebSocket连接
        
        Returns:
            是否连接成功
        """
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets库未安装")
            return False
            
        async with self._lock:
            if self._connected and self._websocket:
                return True
                
            try:
                logger.info(f"正在连接小智服务器: {self._endpoint}")
                self._websocket = await websockets.connect(
                    self._endpoint,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                )
                self._connected = True
                self._reconnect_attempts = 0
                logger.info("小智服务器连接成功")
                return True
            except Exception as e:
                logger.error(f"连接小智服务器失败: {e}")
                self._connected = False
                self._websocket = None
                return False
    
    async def disconnect(self):
        """断开连接"""
        async with self._lock:
            if self._websocket:
                try:
                    await self._websocket.close()
                    logger.info("已断开小智服务器连接")
                except Exception as e:
                    logger.warning(f"断开连接时出错: {e}")
                finally:
                    self._websocket = None
                    self._connected = False
    
    async def _reconnect_with_backoff(self) -> bool:
        """使用指数退避策略重连
        
        Returns:
            是否重连成功
        """
        if self._reconnect_attempts >= self.MAX_RECONNECT_ATTEMPTS:
            logger.error(f"已达到最大重连次数 ({self.MAX_RECONNECT_ATTEMPTS})")
            return False
        
        # 计算退避延迟
        delay = min(
            self.INITIAL_RECONNECT_DELAY * (2 ** self._reconnect_attempts),
            self.MAX_RECONNECT_DELAY
        )
        self._reconnect_attempts += 1
        
        logger.info(f"将在 {delay:.1f} 秒后尝试重连 (第 {self._reconnect_attempts} 次)")
        await asyncio.sleep(delay)
        
        # 重置连接状态
        self._websocket = None
        self._connected = False
        
        return await self.connect()
    
    async def _send_message(self, message: str) -> bool:
        """发送消息（内部方法）
        
        Args:
            message: 要发送的消息
            
        Returns:
            是否发送成功
        """
        if not self._connected or not self._websocket:
            # 尝试连接
            if not await self.connect():
                return False
        
        try:
            await self._websocket.send(message)
            logger.info(f"消息已发送: {message}")
            return True
        except ConnectionClosed as e:
            logger.warning(f"连接已关闭: {e}")
            self._connected = False
            # 尝试重连并重发
            if await self._reconnect_with_backoff():
                try:
                    await self._websocket.send(message)
                    logger.info(f"重连后消息已发送: {message}")
                    return True
                except Exception as e2:
                    logger.error(f"重连后发送失败: {e2}")
                    return False
            return False
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False
    
    async def send_wake(self) -> bool:
        """发送唤醒指令
        
        Returns:
            是否发送成功
        """
        message = format_wake_message()
        success = await self._send_message(message)
        if success:
            logger.info("唤醒指令已发送")
        return success
    
    async def send_reminder(self, content: str) -> bool:
        """发送提醒内容
        
        Args:
            content: 提醒内容
            
        Returns:
            是否发送成功
        """
        message = format_reminder_message(content)
        success = await self._send_message(message)
        if success:
            logger.info(f"提醒内容已发送: {content}")
        return success
    
    async def send_wake_and_reminder(self, content: str) -> Tuple[bool, str]:
        """发送唤醒+提醒，返回(成功, 消息)
        
        先发送唤醒指令，再发送提醒内容
        
        Args:
            content: 提醒内容
            
        Returns:
            (是否成功, 结果消息)
        """
        # 发送唤醒指令
        wake_success = await self.send_wake()
        if not wake_success:
            return (False, "发送唤醒指令失败")
        
        # 短暂延迟，确保设备有时间响应唤醒
        await asyncio.sleep(0.5)
        
        # 发送提醒内容
        reminder_success = await self.send_reminder(content)
        if not reminder_success:
            return (False, "发送提醒内容失败（唤醒指令已发送）")
        
        return (True, f"提醒已发送: {content}")


# ==================== 业务管理层 ====================

class ReminderManager:
    """核心业务逻辑，协调各组件
    
    协调 ReminderStore, ReminderScheduler, XiaozhiClient
    实现提醒的添加、删除、列表、触发和立即发送功能
    """
    
    def __init__(self, store: ReminderStore = None, scheduler: ReminderScheduler = None, client: XiaozhiClient = None):
        """初始化管理器
        
        Args:
            store: 提醒存储，默认创建新实例
            scheduler: 调度器，默认创建新实例
            client: 小智客户端，默认创建新实例
        """
        self._store = store or ReminderStore()
        self._scheduler = scheduler or ReminderScheduler()
        self._client = client or XiaozhiClient()
        self._initialized = False
    
    @property
    def store(self) -> ReminderStore:
        """获取存储实例"""
        return self._store
    
    @property
    def scheduler(self) -> ReminderScheduler:
        """获取调度器实例"""
        return self._scheduler
    
    @property
    def client(self) -> XiaozhiClient:
        """获取客户端实例"""
        return self._client
    
    def initialize(self) -> bool:
        """初始化管理器，启动调度器
        
        Returns:
            是否初始化成功
        """
        if self._initialized:
            return True
        
        if self._scheduler.start():
            self._initialized = True
            logger.info("ReminderManager 已初始化")
            return True
        else:
            logger.warning("调度器启动失败，服务降级为仅支持立即发送")
            self._initialized = True  # 仍然标记为已初始化，支持降级模式
            return False
    
    def shutdown(self):
        """关闭管理器，停止调度器和客户端连接"""
        if self._scheduler:
            self._scheduler.stop()
        # 注意：客户端断开连接是异步的，需要在异步上下文中调用
        self._initialized = False
        logger.info("ReminderManager 已关闭")
    
    def add_reminder(self, content: str, trigger_time_str: str) -> Tuple[bool, str, Optional[Reminder]]:
        """添加提醒
        
        Args:
            content: 提醒内容
            trigger_time_str: 触发时间字符串，支持绝对时间和相对时间
            
        Returns:
            (成功, 消息, 提醒对象)
            - 成功时返回 (True, 成功消息, Reminder对象)
            - 失败时返回 (False, 错误消息, None)
        """
        # 验证内容不为空
        if not content or not content.strip():
            return (False, "Reminder content cannot be empty", None)
        
        # 解析触发时间
        try:
            trigger_time = parse_trigger_time(trigger_time_str)
        except ValueError as e:
            return (False, f"Invalid time format: {e}", None)
        
        # 验证时间不是过去
        if trigger_time <= datetime.now():
            return (False, "Trigger time must be in the future", None)
        
        # 创建提醒对象
        reminder = Reminder(
            content=content.strip(),
            trigger_time=trigger_time
        )
        
        # 存储提醒
        reminder_id = self._store.add(reminder)
        
        # 注册定时任务
        if self._scheduler.is_running:
            if not self._scheduler.schedule(reminder, self._on_reminder_trigger):
                # 调度失败，回滚存储
                self._store.remove(reminder_id)
                return (False, "Failed to schedule reminder", None)
        else:
            logger.warning(f"调度器未运行，提醒 {reminder_id} 已存储但不会自动触发")
        
        logger.info(f"提醒已添加: {reminder_id} -> {trigger_time}")
        return (True, f"Reminder added successfully. ID: {reminder_id}, Scheduled: {trigger_time.strftime('%Y-%m-%d %H:%M:%S')}", reminder)
    
    def delete_reminder(self, reminder_id: str) -> Tuple[bool, str]:
        """删除提醒
        
        Args:
            reminder_id: 提醒ID
            
        Returns:
            (成功, 消息)
        """
        # 检查提醒是否存在
        reminder = self._store.get(reminder_id)
        if not reminder:
            return (False, f"Reminder not found: {reminder_id}")
        
        # 取消定时任务
        if self._scheduler.is_running:
            self._scheduler.cancel(reminder_id)
        
        # 从存储中删除
        if self._store.remove(reminder_id):
            logger.info(f"提醒已删除: {reminder_id}")
            return (True, f"Reminder deleted successfully: {reminder_id}")
        else:
            return (False, f"Failed to delete reminder: {reminder_id}")
    
    def list_reminders(self) -> List[Reminder]:
        """获取所有待触发提醒
        
        Returns:
            按触发时间排序的待触发提醒列表
        """
        return self._store.list_pending()
    
    def _on_reminder_trigger(self, reminder_id: str):
        """定时任务触发回调（由调度器调用）
        
        这是一个同步包装器，用于在异步事件循环中执行触发逻辑
        
        Args:
            reminder_id: 提醒ID
        """
        try:
            # 获取或创建事件循环
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # 在事件循环中执行异步触发
            if loop.is_running():
                asyncio.create_task(self.trigger_reminder(reminder_id))
            else:
                loop.run_until_complete(self.trigger_reminder(reminder_id))
        except Exception as e:
            logger.error(f"触发提醒时出错: {e}")
            self._store.update_status(reminder_id, ReminderStatus.FAILED, str(e))
    
    async def trigger_reminder(self, reminder_id: str) -> Tuple[bool, str]:
        """触发提醒（由调度器调用）
        
        发送唤醒指令和提醒内容到小智服务器
        
        Args:
            reminder_id: 提醒ID
            
        Returns:
            (成功, 消息)
        """
        # 获取提醒
        reminder = self._store.get(reminder_id)
        if not reminder:
            logger.warning(f"触发时提醒不存在: {reminder_id}")
            return (False, f"Reminder not found: {reminder_id}")
        
        if reminder.status != ReminderStatus.PENDING:
            logger.warning(f"提醒状态不是PENDING: {reminder_id} -> {reminder.status}")
            return (False, f"Reminder is not pending: {reminder_id}")
        
        logger.info(f"正在触发提醒: {reminder_id} -> {reminder.content}")
        
        # 发送唤醒和提醒
        success, message = await self._client.send_wake_and_reminder(reminder.content)
        
        if success:
            # 标记为已完成
            self._store.update_status(reminder_id, ReminderStatus.COMPLETED)
            logger.info(f"提醒已触发成功: {reminder_id}")
            return (True, message)
        else:
            # 标记为失败
            self._store.update_status(reminder_id, ReminderStatus.FAILED, message)
            logger.error(f"提醒触发失败: {reminder_id} -> {message}")
            return (False, message)
    
    async def send_immediate(self, content: str) -> Tuple[bool, str]:
        """立即发送提醒（测试用）
        
        不经过调度，直接发送唤醒和提醒内容
        
        Args:
            content: 提醒内容
            
        Returns:
            (成功, 消息)
        """
        # 验证内容不为空
        if not content or not content.strip():
            return (False, "Reminder content cannot be empty")
        
        content = content.strip()
        logger.info(f"立即发送提醒: {content}")
        
        # 发送唤醒和提醒
        success, message = await self._client.send_wake_and_reminder(content)
        
        if success:
            logger.info(f"立即发送成功: {content}")
            return (True, f"Immediate reminder sent successfully: {content}")
        else:
            logger.error(f"立即发送失败: {message}")
            return (False, f"Failed to send immediate reminder: {message}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态
        
        Returns:
            包含服务状态信息的字典
        """
        return {
            "initialized": self._initialized,
            "scheduler_running": self._scheduler.is_running if self._scheduler else False,
            "client_connected": self._client.is_connected if self._client else False,
            "pending_reminders": self._store.size() if self._store else 0,
            "scheduled_jobs": self._scheduler.get_pending_jobs_count() if self._scheduler else 0,
            "websocket_endpoint": self._client.endpoint if self._client else None
        }


# ==================== 全局管理器实例 ====================

# 创建全局管理器实例
_manager: Optional[ReminderManager] = None


def get_manager() -> ReminderManager:
    """获取或创建全局管理器实例"""
    global _manager
    if _manager is None:
        _manager = ReminderManager()
        _manager.initialize()
    return _manager


# ==================== MCP Tools ====================

@mcp.tool()
def add_reminder(content: str, trigger_time: str) -> dict:
    """添加定时提醒
    
    Args:
        content: 提醒内容
        trigger_time: 触发时间，格式 "YYYY-MM-DD HH:MM:SS" 或相对时间 "+5m", "+1h", "+30s"
        
    Returns:
        包含操作结果的字典
    """
    manager = get_manager()
    success, message, reminder = manager.add_reminder(content, trigger_time)
    
    if success and reminder:
        return {
            "success": True,
            "message": message,
            "reminder": {
                "id": reminder.id,
                "content": reminder.content,
                "trigger_time": reminder.trigger_time.strftime('%Y-%m-%d %H:%M:%S'),
                "status": reminder.status.value
            }
        }
    else:
        return {
            "success": False,
            "error": message
        }


@mcp.tool()
def list_reminders() -> dict:
    """查看所有待触发的提醒
    
    Returns:
        包含提醒列表的字典
    """
    manager = get_manager()
    reminders = manager.list_reminders()
    
    return {
        "success": True,
        "count": len(reminders),
        "reminders": [
            {
                "id": r.id,
                "content": r.content,
                "trigger_time": r.trigger_time.strftime('%Y-%m-%d %H:%M:%S'),
                "status": r.status.value
            }
            for r in reminders
        ]
    }


@mcp.tool()
def delete_reminder(reminder_id: str) -> dict:
    """删除指定提醒
    
    Args:
        reminder_id: 要删除的提醒ID
        
    Returns:
        包含操作结果的字典
    """
    manager = get_manager()
    success, message = manager.delete_reminder(reminder_id)
    
    if success:
        return {
            "success": True,
            "message": message
        }
    else:
        return {
            "success": False,
            "error": message
        }


@mcp.tool()
async def send_now(content: str) -> dict:
    """立即发送提醒（测试用）
    
    不经过调度，直接发送唤醒指令和提醒内容到小智设备
    
    Args:
        content: 提醒内容
        
    Returns:
        包含操作结果的字典
    """
    manager = get_manager()
    success, message = await manager.send_immediate(content)
    
    if success:
        return {
            "success": True,
            "message": message
        }
    else:
        return {
            "success": False,
            "error": message
        }


@mcp.tool()
def reminder_status() -> dict:
    """获取提醒服务状态
    
    Returns:
        包含服务状态信息的字典
    """
    manager = get_manager()
    status = manager.get_status()
    
    return {
        "success": True,
        "status": {
            "service_initialized": status["initialized"],
            "scheduler_running": status["scheduler_running"],
            "websocket_connected": status["client_connected"],
            "websocket_endpoint": status["websocket_endpoint"],
            "pending_reminders": status["pending_reminders"],
            "scheduled_jobs": status["scheduled_jobs"]
        }
    }


# ==================== 启动入口 ====================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("=" * 50)
    logger.info("小智定时提醒MCP服务已启动")
    logger.info("=" * 50)
    logger.info("服务就绪，等待指令...")
    
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("服务被中断")
