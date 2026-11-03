# 🤖 小智 ESP32 AI硬件编程教案：智能温控风扇

## 📖 课程简介
本教案专为教育场景设计，通过在“小智 ESP32”大模型语音助手中加入 **DHT11 温湿度传感器** 与 **风扇电机**，引导学生理解**大语言模型如何通过 MCP (Model Context Protocol) 框架操作现实物理世界的硬件**，同时学习单总线传感器通信时序与基础的 GPIO 拉低拉高控制。

---

## ⭐ 当前项目实现的主要功能

结合本次开发的 DHT11 与风扇外设，当前“小智-教育版”完成了以下几个核心功能：
1. **AI 语音自然交互**：通过网络与云端大模型通话，用人类自然语言对设备发号施令，无需死板的按键操作。
2. **环境温湿度实时监测**：利用 DHT11 传感器，小智拥有了“触觉”，可以随时告诉你当前室内的温度和湿度数据。
3. **大模型自主逻辑决策（MCP）**：系统不需要硬编码写死 `if(temp > 30) { 开风扇 }`。你可以告诉 AI 任何规则（例如：“如果温度超过 30 度并且我没回家，就......”），大模型在云端会自己判断什么时候启动硬件。
4. **智能设备实体控制**：利用代码将 GPIO 拉高拉低，完成了单片机向继电器/三极管发出开、关电风扇指令的能力。

---

## 🛠️ 1. 硬件接线准备
* **DHT11 温湿度传感器**: `VCC` 接 3.3V，`GND` 接 GND，`DATA` 接 **GPIO 4**。
* **风扇电机 (含驱动模块 L298N 或 MX1508 类)**: 
  * 🔌 `VCC`：接 ESP32 开发板的 **5V** 引脚（或外部 5V 电源正极，取决于电机额定电压，不要接 3.3V，带不动电机）。
  * 🔌 `GND`：接 ESP32 开发板的 **GND** 引脚（如果用外接电源，必须与 ESP32 的 GND 共地）。
  * 🔌 `INA`（或 IN1）：接开发板的 **GPIO 5**（这是我们在代码中写的“开/关”信号引脚）。
  * 🔌 `INB`（或 IN2）：接开发板的 **GND**。
  > 💡 **原理提示** : 电机驱动板需要两根信号线产生压差来决定正转或反转。通过把 `INB` 固定接在低电平（GND，0V），当小智发指令让 `INA` 变成高电平（3.3V）时，两端有了压差即可转动；当 `INA` 变成低电平（0V）时，两端没压差，风扇就停了。
  > ⚠️ **注意**：绝对不可将小电机马达的两根线硬绑在开发板引脚上，不仅带不动，还会因为反向电流瞬间烧毁 ESP32 主控芯片！

---

## 💻 2. 核心代码讲解

### 知识点一：传感器协议与底层时序驱动 (C语言)
*文件路径：`main/dht11.c`*

DHT11 是一种单总线传感器，只有一根数据线，0和1的信号区别在于“高电平保持的时间长短”。这段代码非常适合教导学生理解计算机底层通信原理。

```c
// 读取 DHT11 传感器的数据 (节选读取 40 bits 数据的核心循环)
for (int i = 0; i < 40; i++) { // DHT11 每次会回复 5个字节 (5 * 8 = 40 bits)
    
    // 1. 等待低电平结束，准备开始接收 1 个 bit 的数据
    if (wait_for_level(pin, 1, 70) < 0) return -1;
    
    // 2. 记录高电平持续的时间，这是分辨 0 和 1 的关键！
    int high_dur = wait_for_level(pin, 0, 100);
    if (high_dur < 0) return -1;

    // 3. 将对应字节的数据左移一位，给新来的 bit 腾出位置
    int byte_idx = i / 8;
    data[byte_idx] <<= 1;
    
    // 4. 判断时间：如果是 26-28us，代表数字 '0' (不作处理，因为上面左移默认补0)
    //    如果超过了 40us (通常是 70us)，代表数字 '1'
    if (high_dur > 40) { 
        data[byte_idx] |= 1; // 使用位或运算，将当前 bit 设为 1
    }
}
```
**👨‍🏫 教学引导：** 提问学生，只有一根线的时候，两个设备如何区分传过来的是0还是1？（通过约定好时间协议！）

---

### 知识点二：设备初始化与 GPIO 控制 
*文件路径：`main/mcp_server.cc`*

要控制外设，必须明确告诉单片机引脚到底是用来“听”（输入）还是“说”（输出）。

```cpp
// 初始化风扇 GPIO (通用输入输出)
gpio_reset_pin(GPIO_NUM_5);                      // 重置引脚状态
gpio_set_direction(GPIO_NUM_5, GPIO_MODE_OUTPUT);// 设置为【输出模式】，因为我们要发出控制信号
gpio_set_level(GPIO_NUM_5, 0);                   // 初始状态设为低电平 (0)，默认让风扇关闭

// 初始化 DHT11 GPIO
dht11_init(GPIO_NUM_4);                          // 内部将 GPIO 4 设成了开漏输入输出模式
```

---

### 知识点三：赋予 AI 连接物理世界的能力 (MCP 协议)
大语言模型（大脑袋）不知道你插了风扇，我们需要将风扇和温度计包装成一个**工具 (Tool)**，并使用提示词(Prompt)告诉AI这个工具能干嘛。

#### 🔧 工具 1：大模型控制风扇
```cpp
// 注册控制风扇的工具，工具名为: self.device.control_fan
AddTool("self.device.control_fan", 
    // 【关键】对 AI 解释这个工具的作用，AI 会根据这段英文决定何时调用它
    "Turn the electric fan on or off. Use this tool when the user asks to turn on the fan or when the temperature is too high.",
    // 定义该工具需要 AI 传递哪些参数过来
    PropertyList({
        Property("state", kPropertyTypeString, "The state to set the fan to: 'on' or 'off'")
    }),
    // 当 AI 决定调用这个工具时，实际执行的 C++ 代码
    [](const PropertyList& properties) -> ReturnValue {
        // 解析 AI 传过来的 "state" 参数
        auto state = properties["state"].value<std::string>();
        
        if (state == "on") {
            gpio_set_level(GPIO_NUM_5, 1); // 收到 on，给风扇引脚高电平，转动！
            ESP_LOGI(TAG, "AI 把风扇打开了");
            return true;
        } else if (state == "off") {
            gpio_set_level(GPIO_NUM_5, 0); // 收到 off，给风扇引脚低电平，停止！
            ESP_LOGI(TAG, "AI 把风扇关闭了");
            return true;
        }
        return false;
    });
```

#### 🌡️ 工具 2：大模型获取环境温度
```cpp
// 注册获取温度的工具
AddTool("self.device.get_temperature",
    // 告诉 AI 这个工具可以用来获取房间的温度和湿度
    "Get the current room temperature and humidity from the DHT11 sensor.",
    PropertyList(), // 此工具不需要 AI 提供任何参数
    [](const PropertyList& properties) -> ReturnValue {
        float temperature = 0.0f;
        float humidity = 0.0f;
        
        // 尝试读取传感器数据（多次重试防止由于时序打断导致的读取失败）
        bool success = false;
        for (int i = 0; i < 3; i++) {
            if (dht11_read(GPIO_NUM_4, &temperature, &humidity) == 0) {
                success = true;
                break;
            }
            vTaskDelay(pdMS_TO_TICKS(100)); // 如果失败，歇一会儿再读
        }

        // 把读到的结果打包成 JSON 格式（大模型能听懂的通用数据格式），返回给 AI 去思考
        cJSON *json = cJSON_CreateObject();
        if (success) {
            cJSON_AddNumberToObject(json, "temperature", temperature);
            cJSON_AddNumberToObject(json, "humidity", humidity);
            cJSON_AddStringToObject(json, "unit", "Celsius");
            cJSON_AddStringToObject(json, "status", "success");
        } else {
            cJSON_AddStringToObject(json, "status", "failed to read sensor"); // 告诉 AI 我们生病了(读取失败)
        }
        return json;
    });
```

---

### 知识点四：语音助手的“大脑”状态机 (C++类与枚举)
*文件路径：`main/device_state_machine.cc`*

小智是如何知道自己现在应该“听你说话”还是应该“回你话”的呢？在代码中，这叫做**状态机 (State Machine)**。通过状态机，设备能够在各种不同的工作模式下有序切换，永远不会同时去“听”又同时去“说”。

```cpp
// 节选：定义语音助手各种状态的名字（用于日志打印和识别）
static const char* const STATE_STRINGS[] = {
    "unknown",           // 0: 未知状态
    "starting",          // 1: 正在开机启动
    "wifi_configuring",  // 2: 正在配网（等待手机连WiFi）
    "idle",              // 3: 待机发呆（等待被唤醒）
    "connecting",        // 4: 正在连接服务器大模型
    "listening",         // 5: 正在竖起耳朵听你说话
    "speaking",          // 6: 小智正在开口讲话
    "upgrading",         // 7: 固件升级中
    "activating",        // 8: 设备激活中
    "audio_testing",     // 9: 检查麦克风喇叭好不好用
    "fatal_error",       // 10: 遇到严重错误宕机
    "invalid_state"
};

// 状态机核心机制：判断“状态A”能否跳转到“状态B”
bool DeviceStateMachine::IsValidTransition(DeviceState from, DeviceState to) const {
    // ...
    switch (from) {
        case kDeviceStateIdle: // 当小智在待机发呆时(Idle)
            // 它可以开始连接服务器，或者开始倾听，或者直接讲话，但在发呆时不能直接升级
            return to == kDeviceStateConnecting ||
                   to == kDeviceStateListening ||
                   to == kDeviceStateSpeaking ||
                   to == kDeviceStateActivating ||
                   to == kDeviceStateUpgrading ||
                   to == kDeviceStateWifiConfiguring;

        case kDeviceStateListening: // 当小智正在听你说话时(Listening)
            // 听完了，只能变成开口说话(Speaking)，或者没听清变回发呆(Idle)
            // 绝对不能在这个时候突然进入“配网状态”
            return to == kDeviceStateSpeaking ||
                   to == kDeviceStateIdle;
                   
        case kDeviceStateSpeaking: // 当小智讲完话后(Speaking)
            // 讲完后，继续听你说(Listening)，或者结束对话去发呆(Idle)
            return to == kDeviceStateListening ||
                   to == kDeviceStateIdle;
    // ...
}
```
**👨‍🏫 教学引导：** 
如果小智一边说话一边听声音会怎样？（会听见自己播放的声音，也就是产生“回音”或“狼嚎”）。引导学生理解为什么程序需要像交通灯一样，红灯停绿灯行（用状态来约束当前设备的动作）。

---

## 🎯 3. 课堂互动与测试
在完成代码烧录后，引导学生使用语音与小智互动，体会大模型的理解力。

**👨‍🎓 学生语音指令示例：**
> **“小智，你帮我看看现在温度，如果高于30度就帮我把电风扇打开。”**

**🧠 AI 思考与执行逻辑 (MCP 工作流)：**
1. **意图理解**：AI 听懂了指令，发现需要查询温度。
2. **工具调用 1**：AI 决定调用 `self.device.get_temperature`。
3. **硬件执行 1**：ESP32 执行 DHT11 读取逻辑，比如返回温度 `32度` 给 AI。
4. **逻辑推理**：AI 判断 32度 > 30度，认为需要开风扇。
5. **工具调用 2**：AI 决定调用 `self.device.control_fan`，并传入参数 `{ "state": "on" }`。
6. **硬件执行 2**：ESP32 收到 `on` 参数，拉高 GPIO 5，风扇呼呼转起来。
7. **语言反馈**：小智通过喇叭回答：“现在温度是32摄氏度，有点热，我已经帮你把风扇打开了。”
