# 串口通信使用说明

本文档说明如何配置和使用串口通信功能，从体检机（通过RS232转USB）读取身高体重数据。

## 1. 硬件连接

- **体检机** → **RS232转USB转换器** → **树莓派USB接口**
- 确保连接正确：
  - TX（体检机）→ RX（转换器）
  - RX（体检机）→ TX（转换器）
  - GND（体检机）→ GND（转换器）

## 2. 检查串口设备

在树莓派上检查串口设备：

```bash
# 查看所有串口设备
ls -la /dev/tty* | grep USB

# 查看系统日志中的串口信息
dmesg | grep -i "tty\|serial\|usb" | tail -20
```

通常RS232转USB设备会显示为 `/dev/ttyUSB0`。

## 3. 权限设置

确保当前用户在 `dialout` 组中（通常已设置）：

```bash
# 检查是否在dialout组
groups | grep dialout

# 如果不在，添加用户到dialout组
sudo usermod -a -G dialout $USER
# 然后重新登录
```

## 4. 测试串口通信

### 方法1：使用测试脚本

```bash
# 基本测试（默认115200波特率，已确认）
python3 test_serial.py /dev/ttyUSB0

# 如果需要测试其他波特率
python3 test_serial.py /dev/ttyUSB0 9600
python3 test_serial.py /dev/ttyUSB0 19200
python3 test_serial.py /dev/ttyUSB0 38400
```

测试脚本会：
- 列出所有可用的串口设备
- 打开指定串口并监听数据
- 显示收到的原始数据和解析结果
- 按 Ctrl+C 停止

### 方法2：使用串口读取模块

```bash
# 直接运行串口读取模块
python3 serial_reader.py
```

## 5. 配置主程序使用串口

### 环境变量配置

在主程序启动前设置以下环境变量：

```bash
# 启用串口功能
export SERIAL_ENABLED=true

# 指定串口设备（默认 /dev/ttyUSB0）
export SERIAL_PORT=/dev/ttyUSB0

# 指定波特率（默认 115200，已确认）
export SERIAL_BAUDRATE=115200
```

### 支持的波特率

**已确认的波特率：115200** ✓

其他常见波特率：9600, 19200, 38400, 57600

如果通信有问题，可以尝试其他波特率。

### 启动主程序

```bash
# 设置环境变量并启动
export SERIAL_ENABLED=true
export SERIAL_PORT=/dev/ttyUSB0
export SERIAL_BAUDRATE=115200  # 已确认的波特率

# 启动服务
python3 physical_exam_control.py
```

或使用启动脚本：

```bash
# 编辑 start.sh，添加环境变量
export SERIAL_ENABLED=true
export SERIAL_PORT=/dev/ttyUSB0
export SERIAL_BAUDRATE=9600

# 然后运行
./start.sh
```

## 6. 数据格式

串口读取模块支持以下数据格式：

### 格式1：JSON格式
```json
{"height": 170, "weight": 65}
{"height_cm": 170, "weight_kg": 65}
```

### 格式2：文本格式（H:170 W:65）
```
H:170 W:65
Height:170 Weight:65
```

### 格式3：逗号分隔
```
170,65
170.5,65.2
```

### 格式4：其他变体
```
身高:170 体重:65
H=170 W=65
```

## 7. 工作流程

1. **串口读取器启动**
   - 打开串口设备
   - 启动后台读取线程
   - 持续监听串口数据

2. **数据解析**
   - 接收原始数据
   - 尝试多种格式解析
   - 提取身高和体重数值

3. **数据处理**
   - 调用回调函数 `on_serial_data(height, weight)`
   - 自动调用 `process_and_speak()` 处理数据
   - 计算BMI、生成建议、触发播报

4. **数据发布**
   - 发布到MQTT主题 `体检中心/仪器/身高体重`
   - 触发小智播报
   - 可选：上传到服务器

## 8. 故障排查

### 问题1：找不到串口设备

```bash
# 检查设备是否存在
ls -la /dev/ttyUSB0

# 检查USB设备
lsusb

# 查看系统日志
dmesg | tail -50
```

**解决方法：**
- 检查USB连接
- 检查转换器驱动（CH341通常已自动加载）
- 尝试重新插拔USB设备

### 问题2：权限不足

```
Permission denied: /dev/ttyUSB0
```

**解决方法：**
```bash
sudo usermod -a -G dialout $USER
# 重新登录后生效
```

### 问题3：收不到数据

**可能原因：**
1. 波特率不匹配
2. 数据线连接错误
3. 体检机未发送数据
4. 数据格式不匹配

**解决方法：**
1. 尝试不同的波特率（9600, 19200, 38400, 115200）
2. 检查TX/RX是否接反
3. 确认体检机已上电并正常工作
4. 查看测试脚本的原始数据输出，确认数据格式

### 问题4：数据解析失败

**解决方法：**
1. 查看日志中的原始数据
2. 根据实际数据格式修改 `serial_reader.py` 中的解析逻辑
3. 如果数据格式特殊，可以添加自定义解析规则

## 9. 日志查看

主程序会输出详细的日志信息：

```bash
# 查看实时日志
python3 physical_exam_control.py

# 如果使用systemd服务
sudo journalctl -u physical-exam-mcp.service -f
```

关键日志信息：
- `串口 /dev/ttyUSB0 打开成功` - 串口打开成功
- `收到数据: ...` - 收到原始数据
- `解析到数据: 身高=170cm, 体重=65kg` - 成功解析数据
- `从串口收到体检数据: ...` - 数据已处理

## 10. 同时支持MQTT和串口

系统可以同时支持两种数据来源：

1. **MQTT**：从 `体检中心/仪器/身高体重` 主题接收数据
2. **串口**：直接从串口读取体检机数据

两种方式可以同时启用，数据会统一处理。

## 11. 环境变量汇总

| 变量 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| SERIAL_ENABLED | 是否启用串口功能 | false | true |
| SERIAL_PORT | 串口设备路径 | /dev/ttyUSB0 | /dev/ttyUSB0 |
| SERIAL_BAUDRATE | 波特率 | 115200 | 115200（已确认），其他：9600, 19200, 38400 |

## 12. 测试示例

### 完整测试流程

```bash
# 1. 检查串口设备
ls -la /dev/ttyUSB0

# 2. 测试串口通信（使用已确认的115200波特率）
python3 test_serial.py /dev/ttyUSB0 115200

# 3. 如果测试成功，配置并启动主程序
export SERIAL_ENABLED=true
export SERIAL_PORT=/dev/ttyUSB0
export SERIAL_BAUDRATE=115200
python3 physical_exam_control.py
```

### 模拟数据测试

如果体检机暂时无法连接，可以使用串口测试工具发送测试数据：

```bash
# 安装minicom（串口工具）
sudo apt-get install minicom

# 打开串口（只发送，不接收）
minicom -D /dev/ttyUSB0 -b 9600

# 在minicom中输入测试数据（按Ctrl+A然后Z查看帮助）
# 例如输入: H:170 W:65
```

## 注意事项

1. **串口独占**：一个串口设备同时只能被一个程序打开
2. **波特率匹配**：必须与体检机的波特率设置一致
3. **数据格式**：如果数据格式特殊，需要修改解析逻辑
4. **错误处理**：程序会自动处理串口断开、数据错误等情况
5. **资源清理**：程序退出时会自动关闭串口

