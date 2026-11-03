# 小车控制 MCP 服务

## 功能概述

支持两种控制模式：
1. **普通遥控模式** - 字符串指令 / JSON 指令
2. **跟随模式** - 视觉跟随控制

---

## 一、普通遥控模式

### A. 字符串指令（简洁，适合手动测试）

| 类型 | 指令 | 说明 |
|------|------|------|
| 直线移动 | `forward` | 向前 |
| | `back` | 向后 |
| 平移 | `strafe_left` | 向左平移 |
| | `strafe_right` | 向右平移 |
| 旋转 | `rotate_left` | 原地左转（默认90°） |
| | `rotate_right` | 原地右转（默认90°） |
| 停止 | `stop` | 急停 |
| 速度档位 | `speed_slow` | 慢速 (0.15 m/s) |
| | `speed_medium` | 中速 (0.3 m/s) |
| | `speed_fast` | 快速 (0.45 m/s) |
| 持续时间 | `duration_short` | 约 2 秒 |
| | `duration_medium` | 约 5 秒 |
| | `duration_infinite` | 持续运行，需手动 stop |

### B. JSON 指令（灵活，可组合参数）

```json
{
  "linear_x": 0.3,      // 前后速度(m/s)，+前进，-后退
  "linear_y": 0.0,      // 平移速度(m/s)，+左移，-右移
  "angular_z": 0.6,     // 角速度(rad/s)，+左转，-右转
  "duration": 2.0,      // 持续时间(秒)，0=持续运行
  "rotate_deg": 90,     // 旋转角度(度)，自动计算时长
  "stop": false         // true=急停
}
```

**字段说明：**
- `linear_x`: 前后速度，+前进，-后退
- `linear_y`: 平移速度，+左移，-右移
- `angular_z`: 角速度，+左转，-右转
- `duration`: >0 则在该秒数后自动停；=0 则持续运行
- `rotate_deg`: 指定旋转角度，若同时给了 angular_z 且 duration<=0，会自动计算所需持续时间
- `stop`: true 时直接发送零速度

### C. 常用动作示例（字符串）

```
# 前进（当前持续时间档位，当前速度档位）
forward

# 后退 5 秒（先切档，再动作）
duration_medium → back

# 原地左转 90°（自动算时长）
rotate_left

# 平移右侧 2 秒（先档位，再动作）
duration_short → strafe_right

# 速度调快后前进
speed_fast → forward

# 急停
stop
```

### D. 常用动作示例（JSON）

```json
// 精确前进 2 秒
{"linear_x": 0.3, "duration": 2.0}

// 前进并左转（走弧线），持续 3 秒
{"linear_x": 0.25, "angular_z": 0.5, "duration": 3.0}

// 原地左转 90°（给角速度 + 角度，自动算时长）
{"angular_z": 0.6, "rotate_deg": 90}

// 停止
{"stop": true}
```

---

## 二、跟随模式

通过 JSON 指令的 `action` 字段控制：

```json
// 开启跟随
{"action": "follow"}

// 停止跟随
{"action": "stop_follow"}
// 或
{"action": "stop"}
```

跟随模式下的运动由视觉+深度+PID 自动计算速度，无需再发具体移动指令。
要恢复手动遥控，发 `stop_follow` 或 `stop` 即可。

---

## 三、MCP 工具列表

| 工具 | 说明 |
|------|------|
| `control(command)` | 统一控制接口，支持字符串/JSON |
| `move(linear_x, linear_y, angular_z, duration, rotate_deg)` | 精确运动控制 |
| `stop()` | 急停 |
| `follow(enable)` | 跟随模式开关 |
| `set_gear(speed, duration)` | 设置档位 |
| `status()` | 获取状态 |
| `forward(duration)` | 向前移动 |
| `back(duration)` | 向后移动 |
| `strafe_left(duration)` | 向左平移 |
| `strafe_right(duration)` | 向右平移 |
| `rotate_left(degrees)` | 原地左转 |
| `rotate_right(degrees)` | 原地右转 |
| `get_responses(limit)` | 获取响应消息 |

---

## 四、组合使用建议

1. 默认启动后若想先遥控再跟随：
   - 直接用字符串/JSON 遥控
   - 需要跟随时发 `{"action":"follow"}`
   - 停止跟随再发 `{"action":"stop_follow"}`

2. 长时间直行或转弯不被看门狗停掉：
   - 使用 `duration_infinite` 或 JSON 里 `duration: 0`
   - 记得用 `stop` 结束

---

## 启动方式

```bash
# 直接运行
python car_control.py

# 通过 MCP pipe 运行
python mcp_pipe.py
```
