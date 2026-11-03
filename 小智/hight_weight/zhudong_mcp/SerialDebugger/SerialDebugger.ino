/*
 * ESP32-S3 串口调试工具
 * 用于调试身高体重计（波特率115200，606协议）
 * 
 * 连接说明：
 * - 身高体重计的TX -> ESP32-S3的GPIO18 (RX1)
 * - 身高体重计的RX -> ESP32-S3的GPIO17 (TX1)
 * - 身高体重计的GND -> ESP32-S3的GND
 * 
 * 功能：
 * - 将身高体重计的数据转发到USB串口（Serial）用于调试
 * - 支持606协议帧解析和显示
 * - 可以通过USB串口发送命令到身高体重计（支持十六进制格式）
 * 
 * 发送命令格式：
 * - 文本命令：直接输入文本，会自动添加\r\n
 * - 十六进制命令：以"0x"或"hex:"开头，如 "hex:5E 01 47 0D" 或 "0x5E 01 47 0D"
 */

// 硬件串口引脚定义（ESP32-S3）
#define UART1_RX_PIN 18  // 接收身高体重计的数据
#define UART1_TX_PIN 17  // 发送数据到身高体重计

// 串口波特率
#define BAUD_RATE 115200

// 数据缓冲区大小
#define BUFFER_SIZE 512

// 606协议常量
#define FRAME_HEADER_SEND 0x5E  // 发送帧头
#define FRAME_HEADER_RESP 0x5F  // 应答帧头
#define FRAME_TAIL 0x0D         // 帧尾

// 板载LED（用于“完全不依赖串口”的运行状态确认）
#ifndef LED_BUILTIN
#define LED_BUILTIN 2
#endif
bool g_led_state = false;

// ROM 级打印（直接走 UART0，和 boot log 同一路；用于“Serial 没起来/端口选错”时的硬验证）
// 兼容处理：如果头文件不存在，就编译为 no-op
#if __has_include("esp_rom_sys.h")
#include "esp_rom_sys.h"   // esp_rom_printf
static void ROM_println(const char* s) { esp_rom_printf("%s\r\n", s); }
#else
static void ROM_println(const char* s) { (void)s; }
#endif

// 全局数据缓冲区
uint8_t rxBuffer[BUFFER_SIZE];
int rxBufferIndex = 0;

// 统计信息（用于验证“确实在收/在发/在跑”）
volatile uint32_t g_uart1_rx_total = 0;
volatile uint32_t g_uart1_rx_chunks = 0;
volatile uint32_t g_uart1_tx_total = 0;
unsigned long g_last_heartbeat_ms = 0;
unsigned long g_last_led_blink_ms = 0;
unsigned long g_last_rom_alive_ms = 0;

// ---- 调试输出：尽量保证“输出一定到电脑” ----
// 说明：
// - ESP32-S3 的 Arduino 里，Serial 可能是 USB CDC，也可能是 UART0（取决于 IDE 里的 USB CDC On Boot 设置/板子硬件）。
// - 你现在只看到 boot log 而看不到本程序输出，常见原因是：你在看 UART0 的 log，但程序输出走了 USB CDC（或反过来）。
// - 所以这里提供两个输出口：
//   - Serial：始终打印（可能是 USB CDC 或 UART0）
//   - DebugUart0：当 Serial=USB CDC 时，额外往 UART0(GPIO44/43) 打印（通常就是你看到 boot log 的那一路）
// 注意：UART0 的默认脚是 GPIO44(RX0)/GPIO43(TX0)，大多数 ESP32-S3 DevKit 的 USB-UART 桥接就在这两个脚。
#if defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT
HardwareSerial DebugUart0(0);
static const int UART0_RX_PIN = 44;
static const int UART0_TX_PIN = 43;
static bool g_debug_uart0_ready = false;
#endif

inline void DBG_print(const String& s) {
  Serial.print(s);
#if defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT
  if (g_debug_uart0_ready) DebugUart0.print(s);
#endif
}
inline void DBG_println(const String& s = "") {
  Serial.println(s);
#if defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT
  if (g_debug_uart0_ready) DebugUart0.println(s);
#endif
}

// 将字节数组转换为十六进制字符串
String bytesToHex(uint8_t* data, int len) {
  String hexStr = "";
  for (int i = 0; i < len; i++) {
    if (data[i] < 0x10) hexStr += "0";
    hexStr += String(data[i], HEX);
    hexStr += " ";
  }
  hexStr.toUpperCase();
  return hexStr;
}

// 从累计缓冲区中“流式”提取 606 帧（允许分包/粘包），逻辑参考 tests/test_serial.py
// 返回：是否成功提取出至少 1 帧
bool extractAndPrint606FramesFromBuffer() {
  bool anyFrame = false;

  // 防御：缓冲区过大直接清空（避免异常数据导致一直卡着）
  if (rxBufferIndex > (int)BUFFER_SIZE - 8) {
    DBG_println("[WARN] RX缓冲区接近满，清空避免溢出");
    rxBufferIndex = 0;
    return false;
  }

  while (rxBufferIndex >= 2) {
    // 找帧头
    if (rxBuffer[0] != FRAME_HEADER_SEND && rxBuffer[0] != FRAME_HEADER_RESP) {
      // 丢弃一个字节继续
      memmove(rxBuffer, rxBuffer + 1, rxBufferIndex - 1);
      rxBufferIndex -= 1;
      continue;
    }

    uint8_t length = rxBuffer[1];
    int totalLen = 1 + 1 + length + 1;
    if (totalLen < 4 || totalLen > BUFFER_SIZE) {
      DBG_println("[WARN] 606长度字段异常，丢弃帧头继续");
      memmove(rxBuffer, rxBuffer + 1, rxBufferIndex - 1);
      rxBufferIndex -= 1;
      continue;
    }

    if (rxBufferIndex < totalLen) {
      // 数据还不够，等下一批
      return anyFrame;
    }

    // 检查帧尾
    if (rxBuffer[totalLen - 1] != FRAME_TAIL) {
      DBG_println("[WARN] 606帧尾不匹配，丢弃1字节继续找帧");
      memmove(rxBuffer, rxBuffer + 1, rxBufferIndex - 1);
      rxBufferIndex -= 1;
      continue;
    }

    // 拿到完整帧
    uint8_t frame[BUFFER_SIZE];
    memcpy(frame, rxBuffer, totalLen);

    // 从缓冲区移除这帧
    memmove(rxBuffer, rxBuffer + totalLen, rxBufferIndex - totalLen);
    rxBufferIndex -= totalLen;

    // 打印并解析
    DBG_print("[606] ");
    DBG_print(frame[0] == FRAME_HEADER_SEND ? "发送 " : "应答 ");
    DBG_print("len=");
    DBG_print(String(length));
    DBG_print(" raw=");
    DBG_println(bytesToHex(frame, totalLen));

    int frameType;
    uint8_t cmd;
    uint8_t payload[BUFFER_SIZE];
    int payloadLen;
    if (parse606Frame(frame, totalLen, frameType, cmd, payload, payloadLen)) {
      decode606Data(cmd, payload, payloadLen);
    } else {
      DBG_println("    [WARN] parse606Frame失败（理论上不该发生）");
    }
    DBG_println();
    anyFrame = true;
  }

  return anyFrame;
}

// 解析606协议帧
bool parse606Frame(uint8_t* data, int len, int& frameType, uint8_t& cmd, uint8_t* payload, int& payloadLen) {
  if (len < 4) return false;  // 至少需要：帧头+长度+命令+帧尾
  
  // 检查帧头
  if (data[0] == FRAME_HEADER_SEND) {
    frameType = 0;  // 发送帧
  } else if (data[0] == FRAME_HEADER_RESP) {
    frameType = 1;  // 应答帧
  } else {
    return false;  // 不是606协议帧
  }
  
  // 读取长度字段（命令+数据的长度）
  uint8_t length = data[1];
  
  // 计算完整帧长度：帧头(1) + 长度(1) + 数据(length) + 帧尾(1)
  int totalLength = 1 + 1 + length + 1;
  
  // 检查数据是否完整
  if (len < totalLength) return false;
  
  // 检查帧尾
  if (data[totalLength - 1] != FRAME_TAIL) return false;
  
  // 提取命令和数据
  cmd = data[2];
  payloadLen = length - 1;  // 长度字段包含命令，所以数据长度是length-1
  if (payloadLen > 0 && payloadLen < BUFFER_SIZE) {
    memcpy(payload, &data[3], payloadLen);
  } else {
    payloadLen = 0;
  }
  
  return true;
}

// 解码606协议数据
void decode606Data(uint8_t cmd, uint8_t* payload, int payloadLen) {
  Serial.print("    命令: 0x");
  Serial.println(cmd, HEX);
  
  if (payloadLen == 0) {
    Serial.println("    数据: 无");
    return;
  }
  
  Serial.print("    数据: ");
  Serial.println(bytesToHex(payload, payloadLen));
  
  // 根据命令解码数据
  if (cmd == 0x42) {  // 身高开始测量
    if (payloadLen >= 3) {
      uint16_t height = (payload[0] << 8) | payload[1];
      float height_cm = height / 10.0;
      Serial.print("    身高: ");
      Serial.print(height_cm);
      Serial.println(" cm");
      Serial.print("    状态: ");
      if (payload[2] == 0x00) Serial.println("测量中");
      else if (payload[2] == 0x01) Serial.println("测量完成");
      else if (payload[2] == 0x02) Serial.println("测量失败");
      else Serial.print("未知(0x"); Serial.print(payload[2], HEX); Serial.println(")");
    }
  } else if (cmd == 0x43) {  // 体重开始测量
    if (payloadLen >= 3) {
      uint16_t weight = (payload[0] << 8) | payload[1];
      float weight_kg = weight / 10.0;
      Serial.print("    体重: ");
      Serial.print(weight_kg);
      Serial.println(" kg");
      Serial.print("    状态: ");
      if (payload[2] == 0x00) Serial.println("测量中");
      else if (payload[2] == 0x01) Serial.println("测量完成");
      else if (payload[2] == 0x02) Serial.println("测量失败");
      else Serial.print("未知(0x"); Serial.print(payload[2], HEX); Serial.println(")");
    }
  } else if (cmd == 0x47) {  // 身高体重开始测量
    if (payloadLen >= 6) {
      uint16_t height = (payload[0] << 8) | payload[1];
      uint16_t weight = (payload[3] << 8) | payload[4];
      float height_cm = height / 100.0;
      float weight_kg = weight / 100.0;
      Serial.print("    身高: ");
      Serial.print(height_cm);
      Serial.println(" cm");
      Serial.print("    体重: ");
      Serial.print(weight_kg);
      Serial.println(" kg");
      Serial.print("    身高状态: ");
      if (payload[2] == 0x00) Serial.println("测量中");
      else if (payload[2] == 0x01) Serial.println("测量完成");
      else if (payload[2] == 0x02) Serial.println("测量失败");
      else Serial.print("未知(0x"); Serial.print(payload[2], HEX); Serial.println(")");
      Serial.print("    体重状态: ");
      if (payload[5] == 0x00) Serial.println("测量中");
      else if (payload[5] == 0x01) Serial.println("测量完成");
      else if (payload[5] == 0x02) Serial.println("测量失败");
      else Serial.print("未知(0x"); Serial.print(payload[5], HEX); Serial.println(")");
    }
  } else if (cmd == 0x54) {  // 读取版本号
    if (payloadLen >= 2) {
      Serial.print("    版本: V");
      Serial.print(payload[0]);
      Serial.print(".");
      Serial.println(payload[1]);
    }
  } else if (cmd == 0x41) {  // 获取温湿度
    if (payloadLen >= 4) {
      uint16_t temp = (payload[0] << 8) | payload[1];
      uint16_t hum = (payload[2] << 8) | payload[3];
      float temperature = temp / 10.0;
      float humidity = hum / 10.0;
      Serial.print("    温度: ");
      Serial.print(temperature);
      Serial.println(" °C");
      Serial.print("    湿度: ");
      Serial.print(humidity);
      Serial.println(" %");
    }
  }
}

// 处理接收到的数据
void processReceivedData(uint8_t* data, int len) {
  if (len == 0) return;
  
  // 先打印本次“原始分片”（对照 test_serial.py 的 chunk 日志）
  DBG_print("\n[RAW] chunk#");
  DBG_print(String(g_uart1_rx_chunks));
  DBG_print(" bytes=");
  DBG_print(String(len));
  DBG_print(" hex=");
  DBG_println(bytesToHex(data, len));

  // 追加进累计缓冲区（用于解决分包/粘包）
  int canCopy = min(len, (int)BUFFER_SIZE - rxBufferIndex);
  if (canCopy > 0) {
    memcpy(rxBuffer + rxBufferIndex, data, canCopy);
    rxBufferIndex += canCopy;
  } else {
    DBG_println("[WARN] RX累计缓冲区满，丢弃本次数据");
  }

  // 尝试从累计缓冲区提取并打印 606 帧
  bool gotFrame = extractAndPrint606FramesFromBuffer();

  if (!gotFrame) {
    // 仅作提示：不是606帧也没关系，但我们至少要看到 RAW chunk
    DBG_println("[INFO] 本次未解析出完整606帧（可能还在等待后续分片，或设备协议不同）");
  }
}

// 解析十六进制字符串
bool parseHexString(String hexStr, uint8_t* output, int& outputLen) {
  hexStr.trim();
  hexStr.toUpperCase();
  
  // 移除 "0x" 或 "hex:" 前缀
  if (hexStr.startsWith("0X") || hexStr.startsWith("HEX:")) {
    int prefixLen = hexStr.startsWith("0X") ? 2 : 4;
    hexStr = hexStr.substring(prefixLen);
    hexStr.trim();
  }
  
  // 移除所有空格
  hexStr.replace(" ", "");
  
  if (hexStr.length() == 0 || hexStr.length() % 2 != 0) {
    return false;  // 长度必须是偶数
  }
  
  outputLen = hexStr.length() / 2;
  if (outputLen > BUFFER_SIZE) {
    return false;  // 超出缓冲区大小
  }
  
  for (int i = 0; i < outputLen; i++) {
    char c1 = hexStr.charAt(i * 2);
    char c2 = hexStr.charAt(i * 2 + 1);
    
    int val = 0;
    if (c1 >= '0' && c1 <= '9') val += (c1 - '0') * 16;
    else if (c1 >= 'A' && c1 <= 'F') val += (c1 - 'A' + 10) * 16;
    else return false;
    
    if (c2 >= '0' && c2 <= '9') val += (c2 - '0');
    else if (c2 >= 'A' && c2 <= 'F') val += (c2 - 'A' + 10);
    else return false;
    
    output[i] = (uint8_t)val;
  }
  
  return true;
}

void setup() {
  // 1) 先做“完全不依赖串口”的验证：快速闪3下（如果板载LED不是这个脚位，也可能看不到，但不影响后续）
  pinMode(LED_BUILTIN, OUTPUT);
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_BUILTIN, HIGH);
    delay(120);
    digitalWrite(LED_BUILTIN, LOW);
    delay(120);
  }

  // 2) ROM级打印：直接走 UART0（boot log 那一路），用于确认是否进入了 setup()
  ROM_println("[ROM] SerialDebugger setup() entered");

  // 初始化USB串口（用于调试输出）
  Serial.begin(115200);
  delay(1000);

  // 初始化LED心跳（不依赖串口）
  digitalWrite(LED_BUILTIN, LOW);
  
  // 如果 Serial 是 USB CDC，某些环境需要等串口就绪，否则前几行可能丢失
  unsigned long waitStart = millis();
  while (!Serial && (millis() - waitStart) < 2000) {
    delay(10);
  }

#if defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT
  // 当 Serial=USB CDC 时，再额外打开 UART0，让你在“boot log 那个串口”也能看到本程序输出
  DebugUart0.begin(115200, SERIAL_8N1, UART0_RX_PIN, UART0_TX_PIN);
  g_debug_uart0_ready = true;
#endif

  DBG_println("\n\n========================================");
  DBG_println("ESP32-S3 串口调试工具 (606协议)");
  DBG_println("========================================");
  DBG_println("波特率: " + String(BAUD_RATE));
  DBG_println("UART1 RX引脚: GPIO" + String(UART1_RX_PIN));
  DBG_println("UART1 TX引脚: GPIO" + String(UART1_TX_PIN));
#if defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT
  DBG_println("调试输出: Serial(USB CDC) + UART0(GPIO43/44)");
#else
  DBG_println("调试输出: Serial(UART0)");
#endif
  DBG_println("========================================\n");
  
  // 初始化硬件串口1（连接到身高体重计）
  Serial1.begin(BAUD_RATE, SERIAL_8N1, UART1_RX_PIN, UART1_TX_PIN);
  Serial1.setRxBufferSize(2048);
  
  DBG_println("串口初始化完成，等待数据...\n");
  DBG_println("提示：");
  DBG_println("  - 你必须至少看到本行，才说明“程序输出->电脑USB串口”链路是通的");
  DBG_println("  - 接收：会先打印 [RAW] 分片，再尝试解析 [606] 帧");
  DBG_println("  - 发送文本命令：直接输入文本，会自动添加\\r\\n");
  DBG_println("  - 发送十六进制命令：以 \"hex:\" 或 \"0x\" 开头，如 \"hex:5E 01 47 0D\"");
  DBG_println("  - 常用606协议命令：");
  DBG_println("    hex:5E 01 47 0D  - 身高体重开始测量");
  DBG_println("    hex:5E 01 42 0D  - 身高开始测量");
  DBG_println("    hex:5E 01 43 0D  - 体重开始测量");
  DBG_println("    hex:5E 01 54 0D  - 读取版本号");
  DBG_println("    hex:5E 01 41 0D  - 获取温湿度");
  DBG_println();
}

void loop() {
  // LED 快闪：250ms 翻转一次（用于排除“肉眼没看到”的误判）
  if (millis() - g_last_led_blink_ms >= 250) {
    g_last_led_blink_ms = millis();
    g_led_state = !g_led_state;
    digitalWrite(LED_BUILTIN, g_led_state ? HIGH : LOW);
  }

  // 串口心跳：每2秒输出一次
  if (millis() - g_last_heartbeat_ms >= 2000) {
    g_last_heartbeat_ms = millis();
    DBG_print("[HB] alive, UART1_RX_total=");
    DBG_print(String(g_uart1_rx_total));
    DBG_print(", chunks=");
    DBG_print(String(g_uart1_rx_chunks));
    DBG_print(", UART1_TX_total=");
    DBG_println(String(g_uart1_tx_total));
  }

  // ROM 心跳：每5秒往 UART0(boot log 那路)打一行，确认 loop 真的在跑
  if (millis() - g_last_rom_alive_ms >= 5000) {
    g_last_rom_alive_ms = millis();
    ROM_println("[ROM] loop alive");
  }

  // 从身高体重计读取数据并转发到USB串口
  if (Serial1.available()) {
    unsigned long startTime = millis();
    // 注意：这里读到的是“RAW分片”，真正的 606 拼帧在 processReceivedData 里做
    uint8_t chunk[BUFFER_SIZE];
    int chunkLen = 0;
    
    // 读取数据（最多等待200ms以确保完整帧）
    while ((Serial1.available() || (millis() - startTime < 200)) && chunkLen < BUFFER_SIZE) {
      if (Serial1.available()) {
        chunk[chunkLen++] = Serial1.read();
        startTime = millis();  // 重置超时时间
      }
      delay(1);
    }
    
    // 处理接收到的数据
    if (chunkLen > 0) {
      g_uart1_rx_total += chunkLen;
      g_uart1_rx_chunks += 1;
      processReceivedData(chunk, chunkLen);
    }
  }
  
  // 从USB串口读取数据并转发到身高体重计
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();  // 去除首尾空白字符
    
    if (command.length() > 0) {
      uint8_t sendBuffer[BUFFER_SIZE];
      int sendLen = 0;
      
      // 检查是否是十六进制命令
      if (command.startsWith("hex:") || command.startsWith("0x") || command.startsWith("0X")) {
        if (parseHexString(command, sendBuffer, sendLen)) {
          DBG_print("[ESP32 -> 身高体重计] 发送 ");
          DBG_print(String(sendLen));
          DBG_print(" 字节 (十六进制): ");
          DBG_println(bytesToHex(sendBuffer, sendLen));
          
          // 发送十六进制数据
          Serial1.write(sendBuffer, sendLen);
          Serial1.flush();
          g_uart1_tx_total += sendLen;
        } else {
          DBG_println("[错误] 无效的十六进制格式，请使用: hex:5E 01 47 0D 或 0x5E 01 47 0D");
        }
      } else {
        // 文本命令
        DBG_print("[ESP32 -> 身高体重计] 发送文本: ");
        DBG_println(command);
        
        // 发送文本命令
        Serial1.print(command);
        Serial1.print("\r\n");  // 添加回车换行符
        Serial1.flush();
        g_uart1_tx_total += command.length() + 2;
      }
      DBG_println();
    }
  }
  
  // 短暂延迟，避免CPU占用过高
  delay(1);
}

