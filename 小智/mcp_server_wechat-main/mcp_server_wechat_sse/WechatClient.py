"""
微信客户端 - 基于 wxauto 库
支持新版微信
"""
import json
import re
import os
import datetime
import logging
import time
from typing import Optional, List, Union

from wxauto import WeChat


class WeChatClient:
    """
    微信客户端
    负责微信聊天记录获取和消息发送功能
    """

    def __init__(self, default_folder_path: Optional[str] = None):
        """
        初始化微信客户端

        参数:
        - default_folder_path: 默认保存聊天记录的文件夹路径
        """
        self.default_folder_path = default_folder_path
        self.logger = logging.getLogger(__name__)
        self._wx = None
        
        if self.default_folder_path:
            try:
                os.makedirs(self.default_folder_path, exist_ok=True)
            except Exception as e:
                self.logger.error(f"创建默认文件夹失败: {self.default_folder_path}, 错误: {e}")

    @property
    def wx(self) -> WeChat:
        """延迟初始化微信实例"""
        if self._wx is None:
            self._wx = WeChat()
        return self._wx

    def _parse_date(self, date_str: str) -> Optional[datetime.datetime]:
        """解析微信日期格式为datetime对象"""
        try:
            today = datetime.datetime.now().date()

            # YY/M/D 格式
            match = re.match(r'(\d{2})/(\d{1,2})/(\d{1,2})', date_str)
            if match:
                year, month, day = map(int, match.groups())
                return datetime.datetime(2000 + year, month, day)

            # YYYY-MM-DD 格式
            match = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', date_str)
            if match:
                year, month, day = map(int, match.groups())
                return datetime.datetime(year, month, day)

            # YYYY年MM月DD日 格式
            match = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_str)
            if match:
                year, month, day = map(int, match.groups())
                return datetime.datetime(year, month, day)

            if "昨天" in date_str:
                yesterday = today - datetime.timedelta(days=1)
                return datetime.datetime.combine(yesterday, datetime.time())

            if "星期" in date_str:
                weekday_map = {
                    "星期一": 0, "星期二": 1, "星期三": 2, "星期四": 3,
                    "星期五": 4, "星期六": 5, "星期日": 6, "星期天": 6
                }
                for weekday_str, weekday_num in weekday_map.items():
                    if weekday_str in date_str:
                        current_weekday = today.weekday()
                        days_diff = weekday_num - current_weekday
                        if days_diff > 0:
                            days_diff -= 7
                        target_date = today + datetime.timedelta(days=days_diff)
                        return datetime.datetime.combine(target_date, datetime.time())

            # 纯时间格式（今天）
            if re.match(r'^\d{1,2}:\d{2}', date_str):
                return datetime.datetime.combine(today, datetime.time())

            return None
        except Exception as e:
            self.logger.error(f"日期解析错误: {date_str}, {e}")
            return None

    def get_chat_history_by_date(self, friend: str, target_date: str, folder_path: str = None,
                                 search_pages: int = 5, wechat_path: str = None, is_maximize: bool = False,
                                 close_wechat: bool = True, scroll_delay: float = 0.01):
        """
        获取特定日期的微信聊天记录

        参数:
        - friend: 好友或群聊备注或昵称
        - target_date: 目标日期，格式为"YY/M/D"，如"25/3/22"
        - folder_path: 保存聊天记录的文件夹路径
        - search_pages: 搜索好友时翻页次数
        - scroll_delay: 翻页延迟时间(秒)

        返回:
        - 聊天记录的JSON字符串
        """
        if folder_path is None:
            folder_path = self.default_folder_path

        if folder_path:
            os.makedirs(folder_path, exist_ok=True)

        # 解析目标日期
        try:
            match = re.match(r'(\d{2})/(\d{1,2})/(\d{1,2})', target_date)
            if match:
                year, month, day = map(int, match.groups())
                target_datetime = datetime.datetime(2000 + year, month, day)
            else:
                raise ValueError(f'日期格式不正确: {target_date}, 应为"YY/M/D"格式，如"25/3/22"')
        except Exception as e:
            raise ValueError(f'日期解析错误: {e}')

        self.logger.info(f"开始获取与 {friend} 在 {target_date} 的聊天记录")

        # 切换到目标聊天
        try:
            self.wx.ChatWith(friend)
        except Exception as e:
            raise Exception(f"无法打开与 {friend} 的聊天窗口: {e}")

        time.sleep(0.5)

        # 获取聊天记录
        target_messages = []
        max_scroll = search_pages * 10 if search_pages > 0 else 50
        scroll_count = 0

        while scroll_count < max_scroll:
            try:
                messages = self.wx.GetAllMessage()
                if not messages:
                    break

                for msg in messages:
                    if hasattr(msg, 'time') and hasattr(msg, 'sender') and hasattr(msg, 'content'):
                        msg_time = msg.time
                        msg_sender = msg.sender
                        msg_content = msg.content
                    elif isinstance(msg, (list, tuple)) and len(msg) >= 3:
                        msg_sender, msg_content, msg_time = msg[0], msg[1], msg[2]
                    elif isinstance(msg, dict):
                        msg_sender = msg.get('sender', '')
                        msg_content = msg.get('content', '')
                        msg_time = msg.get('time', '')
                    else:
                        continue

                    msg_date = self._parse_date(str(msg_time))
                    if msg_date:
                        msg_date_obj = msg_date.date()
                        target_date_obj = target_datetime.date()

                        if msg_date_obj == target_date_obj:
                            target_messages.append({
                                "发送者": str(msg_sender),
                                "时间": str(msg_time),
                                "消息": str(msg_content)
                            })
                        elif msg_date_obj < target_date_obj:
                            break

                self.wx.LoadMoreMessage()
                time.sleep(scroll_delay)
                scroll_count += 1

                if scroll_count % 10 == 0:
                    self.logger.info(f"已翻页 {scroll_count} 次，收集到 {len(target_messages)} 条消息")

            except Exception as e:
                self.logger.warning(f"获取消息时出错: {e}")
                break

        # 去重
        seen = set()
        unique_messages = []
        for msg in target_messages:
            key = (msg['发送者'], msg['时间'], msg['消息'])
            if key not in seen:
                seen.add(key)
                unique_messages.append(msg)

        formatted_messages = []
        for index, msg in enumerate(unique_messages):
            formatted_messages.append({"index": index, **msg})

        chat_history_json = json.dumps(formatted_messages, ensure_ascii=False, indent=4)

        if folder_path:
            safe_date = target_date.replace('/', '-')
            json_path = os.path.join(folder_path, f'与{friend}的{safe_date}聊天记录.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                f.write(chat_history_json)
            self.logger.info(f"已保存到: {json_path}")

        self.logger.info(f"共获取到 {len(formatted_messages)} 条聊天记录")
        return chat_history_json

    def send_message_to_friend(self, friend: str, message: str, delay: float = 1,
                               search_pages: int = 0):
        """向单个好友发送单条消息"""
        try:
            self.wx.ChatWith(friend)
            time.sleep(0.3)
            self.wx.SendMsg(message)
            time.sleep(delay)
            return {"status": "success", "message": f"消息已发送给 {friend}"}
        except Exception as e:
            return {"status": "error", "message": f"发送消息失败: {str(e)}"}

    def send_messages_to_friend(self, friend: str, messages: List[str], delay: float = 1,
                                search_pages: int = 0):
        """向单个好友发送多条消息"""
        try:
            self.wx.ChatWith(friend)
            time.sleep(0.3)
            for msg in messages:
                self.wx.SendMsg(msg)
                time.sleep(delay)
            return {"status": "success", "message": f"已向 {friend} 发送 {len(messages)} 条消息"}
        except Exception as e:
            return {"status": "error", "message": f"发送消息失败: {str(e)}"}

    def send_message_to_friends(self, friends: List[str], message: Union[str, List[str]], delay: float = 1):
        """向多个好友发送消息"""
        try:
            results = []
            messages = message if isinstance(message, list) else [message] * len(friends)
            
            for i, friend in enumerate(friends):
                msg = messages[i] if i < len(messages) else messages[-1]
                try:
                    self.wx.ChatWith(friend)
                    time.sleep(0.3)
                    self.wx.SendMsg(msg)
                    time.sleep(delay)
                    results.append({"friend": friend, "status": "success"})
                except Exception as e:
                    results.append({"friend": friend, "status": "error", "error": str(e)})
            
            success_count = sum(1 for r in results if r["status"] == "success")
            return {
                "status": "success" if success_count == len(friends) else "partial",
                "message": f"已向 {success_count}/{len(friends)} 位好友发送消息",
                "details": results
            }
        except Exception as e:
            return {"status": "error", "message": f"发送消息失败: {str(e)}"}
