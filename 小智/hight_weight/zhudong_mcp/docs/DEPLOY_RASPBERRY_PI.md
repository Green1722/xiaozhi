# 树莓派部署指南

本文档说明如何将体检中心小智 MCP 服务部署到树莓派平台。

## 前置要求

1. **树莓派系统**：Raspberry Pi OS (Debian) 或其他 Linux 发行版
2. **Python 3.7+**：树莓派通常已预装 Python 3
3. **网络连接**：确保树莓派可以访问 MQTT 服务器和 MCP WebSocket 端点

## 部署步骤

### 1. 将项目文件传输到树莓派

可以使用以下方式之一：

#### 方式 A：使用 SCP（从 Windows 传输）

```powershell
# 在 Windows PowerShell 中执行
scp -r C:\Users\sxc\Desktop\zhudong_mcp pi@树莓派IP:/home/pi/
```

#### 方式 B：使用 Git（如果项目在 Git 仓库中）

```bash
# 在树莓派上执行
cd ~
git clone <你的仓库地址>
cd zhudong_mcp
```

#### 方式 C：使用 USB 或网络共享

将项目文件夹复制到树莓派可访问的位置。

### 2. 安装依赖

```bash
# SSH 连接到树莓派
ssh pi@树莓派IP

# 进入项目目录
cd ~/zhudong_mcp  # 或你的实际路径

# 安装 Python 依赖
pip3 install -r requirements.txt

# 如果 pip3 不可用，尝试：
python3 -m pip install -r requirements.txt
```

### 3. 配置环境变量（可选）

如果需要自定义配置，可以创建 `.env` 文件或设置环境变量：

```bash
# 编辑 .env 文件（如果使用 python-dotenv）
nano .env
```

添加以下内容（根据需要修改）：
```
MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=REPLACE_ME
PHYSICAL_EXAM_UPLOAD_URL=https://your-api.com/upload/exam
PHYSICAL_EXAM_UPLOAD_ENABLED=true
XIAOZHI_SPEAK_TOPIC_ALT=device/你的设备ID/tts
```

### 4. 赋予启动脚本执行权限

```bash
chmod +x start.sh
```

### 5. 测试运行

```bash
# 直接运行测试
./start.sh
```

如果一切正常，你应该看到：
- MQTT 连接成功的消息
- MCP 服务启动的日志
- 可用工具列表

### 6. 配置为系统服务（可选，开机自启）

创建 systemd 服务文件：

```bash
sudo nano /etc/systemd/system/physical-exam-mcp.service
```

添加以下内容（修改路径为你的实际路径）：

```ini
[Unit]
Description=Physical Exam MCP Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/zhudong_mcp
Environment="PYTHONIOENCODING=utf-8"
Environment="PYTHONUTF8=1"
Environment="MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=REPLACE_ME"
Environment="MCP_CONFIG=/home/pi/zhudong_mcp/mcp_config.json"
ExecStart=/usr/bin/python3 /home/pi/zhudong_mcp/mcp_pipe.py health-exam-service
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用并启动服务：

```bash
# 重新加载 systemd 配置
sudo systemctl daemon-reload

# 启用服务（开机自启）
sudo systemctl enable physical-exam-mcp.service

# 启动服务
sudo systemctl start physical-exam-mcp.service

# 查看服务状态
sudo systemctl status physical-exam-mcp.service

# 查看日志
sudo journalctl -u physical-exam-mcp.service -f
```

### 7. 服务管理命令

```bash
# 启动服务
sudo systemctl start physical-exam-mcp.service

# 停止服务
sudo systemctl stop physical-exam-mcp.service

# 重启服务
sudo systemctl restart physical-exam-mcp.service

# 查看状态
sudo systemctl status physical-exam-mcp.service

# 查看日志
sudo journalctl -u physical-exam-mcp.service -n 50

# 实时查看日志
sudo journalctl -u physical-exam-mcp.service -f

# 禁用开机自启
sudo systemctl disable physical-exam-mcp.service
```

## 故障排查

### 问题 1：Python 模块未找到

```bash
# 确保使用 pip3 安装依赖
pip3 install -r requirements.txt --user

# 或使用虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 问题 2：MQTT 连接失败

- 检查网络连接：`ping 47.97.8.221`
- 检查防火墙设置
- 确认 MQTT 服务器地址和端口正确

### 问题 3：MCP WebSocket 连接失败

- 检查 token 是否有效
- 检查网络是否可以访问 `api.xiaozhi.me`
- 查看日志中的详细错误信息

### 问题 4：权限问题

```bash
# 确保脚本有执行权限
chmod +x start.sh

# 如果使用 systemd，确保服务文件中的路径正确
```

## 新增功能：推送最后一条体检数据

服务已新增 `get_last_person_height_weight` MCP 工具，用于获取最后一个人的身高体重数据并推送到服务器。

### 使用方式

通过 MCP 调用该工具，它会：
1. 从内存中获取最后一条体检记录
2. 提取身高体重数据
3. 向配置的服务器推送（需设置 `PHYSICAL_EXAM_UPLOAD_URL`）

### 配置数据上传

在 `.env` 文件或环境变量中设置：

```bash
export PHYSICAL_EXAM_UPLOAD_URL="https://your-api.com/upload/exam"
export PHYSICAL_EXAM_UPLOAD_ENABLED=true
```

### 返回数据格式

```json
{
  "success": true,
  "message": "已成功向服务器推送最后一条体检数据",
  "data": {
    "height_cm": 170,
    "weight_kg": 65,
    "bmi": 22.5,
    "record_id": "exam_1234567890",
    "timestamp": "2025-02-04 12:00:00"
  },
  "uploaded": true
}
```

## 注意事项

1. **网络稳定性**：确保树莓派网络连接稳定，MQTT 和 WebSocket 都需要持续连接
2. **资源占用**：服务会持续运行，建议监控 CPU 和内存使用情况
3. **日志管理**：如果使用 systemd，日志会自动管理；手动运行时注意日志文件大小
4. **数据安全**：确保 MCP token 和上传 URL 等敏感信息的安全性

## 更新服务

当需要更新代码时：

```bash
# 停止服务
sudo systemctl stop physical-exam-mcp.service

# 更新代码（根据你的部署方式）
cd ~/zhudong_mcp
git pull  # 如果使用 Git
# 或重新传输文件

# 重新安装依赖（如果有新依赖）
pip3 install -r requirements.txt

# 启动服务
sudo systemctl start physical-exam-mcp.service
```


