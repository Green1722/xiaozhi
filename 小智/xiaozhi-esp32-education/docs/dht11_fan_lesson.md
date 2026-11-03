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

## 🛠️ 1. 硬件接线准备与常见排雷（极简无工具版）
* **DHT11 温湿度传感器**: `VCC` 接 **3.3V**，`GND` 接 开发板 **GND** 之一，`DATA` 接 **GPIO 17**。
* **风扇电机 (含驱动模块如 MX1508、L298N 类)**: 
  * 🔌 `VCC`：接 ESP32 上的 **3.3V** 引脚（*注: 既然开发板确认无 5V 输出，而小体积电机和 MX1508 驱动板通常对电压宽容，我们可以降级使用 3.3V 供电，只是风扇转速会变慢，但能验证程序逻辑*）。
  * 🔌 `GND`：接 ESP32 开发板的 另一个 **GND**引脚。
  * 🔌 `INA`（正转信号）：接开发板的 **GPIO 18**。
  * 🔌 `INB`（反转信号）：接开发板的 **GPIO 19**（*神基操作：利用代码将其变成“软件地线”*）。

> 🏫 **教学痛点与解决（ESP32-S3 极端缺引脚情况）**：
> 1. **确认绝对没有 5V 输出引脚怎么办？**
>    如果板子连 `VBUS`/`VIN` 都没有，又弄不到电池。既然是教育演示验证逻辑，我们把电机驱动板的 VCC **插在另一个 3.3V 引脚上**（一般 ESP32-S3 都有不止一个 3.3V 引脚）。现在的迷你电机（如N20马达）在 3V 下依然能转起来，只是风力较小。
> 2. **板子上 GND 只有两根，完全没法合线或用面包板怎么办？**
>    现在我们的 DHT11 用掉了一个 GND，风扇驱动器的供电 GND 用掉了第二个，没有多余的 GND 给风扇的 `INB` （反转信号地线）使用了！
>    * **✨ 代码魔法：“软件地线 (Software GND)”**：
>      我们可以**征用一根普通的信号引脚（比如 GPIO 19）**，并在初始化代码里写死：把 GPIO 19 设为输出模式，并且永远输出低电平（也就是零电压 0V）。如此一来，**GPIO 19 就物理等效于一根 GND 地线了！** 把 `INB` 插到这根信号线上，完美免去剪线拧线的麻烦！

> 💡 **风扇驱动原理提示** : 驱动板需要两根信号线产生压差来决定正转或反转。通过把 `INB` 固定接在低电平（GND，0V），当小智发指令让 `INA` 变成高电平（3.3V）时，两端出现电压差即会启动；当 `INA` 变低电平（0V）时，两端毫无压差，风扇停止。
> ⚠️ **注意**：绝对不可将小电机马达的两根电源线硬绑在开发板信号引脚上！发热反向电流会瞬间烧毁 ESP32 芯片！
> ⚠️ **避坑指南**：**绝不能占用 GPIO 4、5、6** 等核心默认引脚，否则会导致麦克风和喇叭失效，使小智无法听到声音或发生崩溃。本教程已变更为安全空闲引脚 17, 18, 19。

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

### 🌟 mcp_server.cc 核心修改总结

为了实现咱们的“AI 智能温控风扇”教育项目，我们在 `mcp_server.cc` 文件中一共加了 3 个大类的核心内容。这些全部都是让小智（大模型）能够与物理世界（传感器、电机）交互的桥梁：

#### 1. 引入了必要的硬件驱动头文件
在代码最顶部的 `#include` 区域，我们新增了两个底层驱动库头文件：
```c
#include "driver/gpio.h" // 乐鑫 ESP32 官方的 GPIO 引脚控制库（用来拉高、拉低引脚电平操作风扇）
#include "dht11.h"       // 我们自己为教育项目手写的 DHT11 温湿度传感器驱动库
```

#### 2. 硬件引脚的初始化（以及“软件地线”魔法）
在 `AddCommonTools()` 函数的中间部分，我们指派并初始化了 3 个安全的空闲引脚：
* **风扇控制引脚 (✨新加)**：将 `GPIO_NUM_18` 设置为输出模式，默认输出低电平（0），让风扇开机时保持关闭。
* **软件地线引脚 (✨新加魔法)**：将 `GPIO_NUM_19` 设置为输出模式，并永久输出低电平（0V）。这是专门为了解决开发板上 GND（地线）接口不够用的教学痛点，将普通引脚强制变成了一个地线接口。
* **温度计引脚 (✨新加)**：调用 `dht11_init(GPIO_NUM_17)` 将 `GPIO_NUM_17` 初始化为专供单总线数据读写的模式。

#### 3. 给 AI 大脑注入三个“物理工具 (MCP Tools)”
这是最核心的部分。大模型本来只是个没手没脚的聊天软件，我们通过 `AddTool()` 给它硬塞了三个可以被它调用的“工具”，从而让它获得了“感知”和“动作”：
* **`self.device.control_fan`（风扇开关控制工具）**：
  * **作用**：大模型决定开风扇时，会发指令调用这个代码，把 GPIO 18 设为 1（高电平）；决定关风扇时，把 GPIO 18 设为 0。
* **`self.device.get_fan_status`（风扇状态复核工具）**：
  * **作用**：大模型可以通过主动读取 GPIO 18 的当前物理电平（1或0），来知道风扇当前真实是不是在转着，避免 AI 自己“瞎猜”。
* **`self.device.get_temperature`（真实温度读取工具）**：
  * **作用**：AI 想要知道温度时，会触发这段代码调用 `dht11_read()`。如果读取失败，代码里还会给它最多尝试 5 次、每次间隔 1.5 秒的重试逻辑。读到真实数据后，再打包成 JSON 格式（带上 Celsius 单位）发送给远端服务器。

---

### 知识点二：设备初始化与 GPIO 控制 
*文件路径：`main/mcp_server.cc`*

要控制外设，必须明确告诉单片机引脚到底是用来“听”（输入）还是“说”（输出）。

```cpp
// 初始化风扇 GPIO (通用输入输出)
gpio_reset_pin(GPIO_NUM_18);                      // 重置引脚状态
gpio_set_direction(GPIO_NUM_18, GPIO_MODE_OUTPUT);// 设置为【输出模式】，因为我们要发出控制信号
gpio_set_level(GPIO_NUM_18, 0);                   // 初始状态设为低电平 (0)，默认让风扇关闭

// 初始化 DHT11 GPIO
dht11_init(GPIO_NUM_17);                          // 内部将 GPIO 17 设成了开漏输入输出模式
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
            gpio_set_level(GPIO_NUM_18, 1); // 收到 on，给风扇引脚高电平，转动！
            ESP_LOGI(TAG, "AI 把风扇打开了");
            return true;
        } else if (state == "off") {
            gpio_set_level(GPIO_NUM_18, 0); // 收到 off，给风扇引脚低电平，停止！
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
            if (dht11_read(GPIO_NUM_17, &temperature, &humidity) == 0) {
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
