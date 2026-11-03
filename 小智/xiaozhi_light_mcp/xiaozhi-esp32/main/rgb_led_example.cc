/**
 * @file rgb_led_example.cc
 * @brief 示例：如何在 xiaozhi-esp32 中添加 RGB LED 控制功能
 * 
 * 本文件展示了如何:
 * 1. 初始化 RGB LED 驱动 (GPIO 10, 11, 12)
 * 2. 通过 MCP 协议暴露 RGB 控制工具给大模型
 * 
 * 使用方法:
 * 1. 将 rgb_led.h 和 rgb_led.cc 复制到 main 目录
 * 2. 将本文件中的 InitializeTools() 函数内容复制到你使用的 board 的对应文件中
 * 3. 修改 GPIO 引脚号为你实际使用的引脚
 */

// ============================================================================
// 第一步: 在 board 文件中包含头文件
// ============================================================================
// 在你的 board .cc 文件顶部添加:
// #include "rgb_led.h"

// ============================================================================
// 第二步: 定义 RGB LED 使用的 GPIO 引脚
// ============================================================================
// 在 config.h 中添加:
// #define RGB_LED_GPIO_R    GPIO_NUM_10
// #define RGB_LED_GPIO_G    GPIO_NUM_11
// #define RGB_LED_GPIO_B    GPIO_NUM_12

// ============================================================================
// 第三步: 在 board 类中添加 RGB LED 成员变量
// ============================================================================
// 在你的 board 类中添加:
// private:
//     RgbLed* rgb_led_;

// ============================================================================
// 第四步: 在构造函数中初始化 RGB LED
// ============================================================================
// 在你的 board 构造函数中添加:
// rgb_led_ = new RgbLed(RGB_LED_GPIO_R, RGB_LED_GPIO_G, RGB_LED_GPIO_B);

// ============================================================================
// 第五步: 在 InitializeTools() 中注册 MCP 工具
// ============================================================================
/*
void InitializeTools() {
    auto& mcp_server = McpServer::GetInstance();
    
    // 注册 RGB LED 控制工具
    mcp_server.AddTool(
        "self.device.set_rgb_color",
        "Control the RGB LED to display a specific color. "
        "Parameters: r, g, b values range from 0 to 255. "
        "Examples: (255,0,0)=red, (0,255,0)=green, (0,0,255)=blue, (255,255,255)=white, (0,0,0)=off.",
        PropertyList({
            Property("r", kPropertyTypeInteger, 0, 255),
            Property("g", kPropertyTypeInteger, 0, 255),
            Property("b", kPropertyTypeInteger, 0, 255)
        }),
        [this](const PropertyList& properties) -> ReturnValue {
            int r = properties["r"].value<int>();
            int g = properties["g"].value<int>();
            int b = properties["b"].value<int>();
            rgb_led_->SetColor(r, g, b);
            return true;
        }
    );

    // 注册关闭 RGB LED 工具
    mcp_server.AddTool(
        "self.device.turn_off_rgb",
        "Turn off the RGB LED (set all channels to 0).",
        PropertyList(),
        [this](const PropertyList& properties) -> ReturnValue {
            rgb_led_->TurnOff();
            return true;
        }
    );

    // 注册设置 RGB LED 亮度工具
    mcp_server.AddTool(
        "self.device.set_rgb_brightness",
        "Set the brightness of the RGB LED (0-100%).",
        PropertyList({
            Property("brightness", kPropertyTypeInteger, 0, 100)
        }),
        [this](const PropertyList& properties) -> ReturnValue {
            int brightness = properties["brightness"].value<int>();
            rgb_led_->SetBrightness(brightness);
            return true;
        }
    );
    
    // 注册预设颜色快捷工具
    mcp_server.AddTool(
        "self.device.set_rgb_preset",
        "Set RGB LED to a preset color: red, green, blue, yellow, cyan, magenta, white, orange, purple.",
        PropertyList({
            Property("color", kPropertyTypeString)
        }),
        [this](const PropertyList& properties) -> ReturnValue {
            auto color = properties["color"].value<std::string>();
            
            // 预设颜色定义
            std::map<std::string, std::tuple<uint8_t, uint8_t, uint8_t>> presets = {
                {"red",     {255, 0, 0}},
                {"green",   {0, 255, 0}},
                {"blue",    {0, 0, 255}},
                {"yellow",  {255, 255, 0}},
                {"cyan",    {0, 255, 255}},
                {"magenta", {255, 0, 255}},
                {"white",   {255, 255, 255}},
                {"orange",  {255, 165, 0}},
                {"purple",  {128, 0, 128}}
            };
            
            auto it = presets.find(color);
            if (it != presets.end()) {
                auto [r, g, b] = it->second;
                rgb_led_->SetColor(r, g, b);
                return true;
            }
            throw std::runtime_error("Unknown color: " + color + ". Available: red, green, blue, yellow, cyan, magenta, white, orange, purple");
        }
    );
}
*/

// ============================================================================
// 完整示例: 假设你使用的是 zhengchen-1.54tft-wifi 板子
// ============================================================================
// 在 zhengchen-1.54tft-wifi/config.h 中添加引脚定义:
// #define RGB_LED_GPIO_R    GPIO_NUM_10
// #define RGB_LED_GPIO_G    GPIO_NUM_11
// #define RGB_LED_GPIO_B    GPIO_NUM_12
//
// 在 zhengchen-1.54tft-wifi/zhengchen-1.54tft-wifi.cc 中:
//
// 1. 添加头文件:
// #include "rgb_led.h"
//
// 2. 添加成员变量 (在 private 部分):
// RgbLed* rgb_led_;
//
// 3. 修改构造函数:
// ZHENGCHEN_1_54TFT_WIFI() : ... {
//     ...
//     rgb_led_ = new RgbLed(RGB_LED_GPIO_R, RGB_LED_GPIO_G, RGB_LED_GPIO_B);
//     InitializeTools();
//     ...
// }
//
// 4. 修改 InitializeTools():
// void InitializeTools() {
//     auto& mcp_server = McpServer::GetInstance();
//     
//     // RGB LED 控制工具
//     mcp_server.AddTool(
//         "self.device.set_rgb_color",
//         "Control the RGB LED to display a specific color...",
//         PropertyList({
//             Property("r", kPropertyTypeInteger, 0, 255),
//             Property("g", kPropertyTypeInteger, 0, 255),
//             Property("b", kPropertyTypeInteger, 0, 255)
//         }),
//         [this](const PropertyList& properties) -> ReturnValue {
//             rgb_led_->SetColor(
//                 properties["r"].value<int>(),
//                 properties["g"].value<int>(),
//                 properties["b"].value<int>()
//             );
//             return true;
//         }
//     );
//     
//     mcp_server.AddTool(
//         "self.device.turn_off_rgb",
//         "Turn off the RGB LED.",
//         PropertyList(),
//         [this](const PropertyList& properties) -> ReturnValue {
//             rgb_led_->TurnOff();
//             return true;
//         }
//     );
//     
//     mcp_server.AddTool(
//         "self.device.set_rgb_brightness",
//         "Set the brightness of the RGB LED (0-100%).",
//         PropertyList({
//             Property("brightness", kPropertyTypeInteger, 0, 100)
//         }),
//         [this](const PropertyList& properties) -> ReturnValue {
//             rgb_led_->SetBrightness(properties["brightness"].value<int>());
//             return true;
//         }
//     );
// }
