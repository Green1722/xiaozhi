#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

#include <driver/gpio.h>
#include <driver/uart.h>

// FPC UART Tester Configuration
// 用于测试 zhengchen-minicam-ml307 的 FPC UART 功能
//
// 接线说明：
//   zhengchen-minicam-ml307  <--->  测试设备ESP32S3
//   GPIO7  (TX/UART1)        <--->  GPIO17 (RX)
//   GPIO8  (RX/UART1)        <--->  GPIO16 (TX)
//   GND                       <--->  GND
//
// 注意事项：
// - 主设备的 GPIO7/GPIO8 是原 CAMERA 引脚（摄像头已移除）
// - 不要用 GPIO15/GPIO17 作为主设备 TX/RX，因为板载 Octal PSRAM 占用

// 测试UART配置 (UART2)
#define TEST_UART_TX_PIN GPIO_NUM_16  // 测试器 TX -> 主设备 GPIO8 (RX)
#define TEST_UART_RX_PIN GPIO_NUM_17  // 测试器 RX <- 主设备 GPIO7 (TX)
#define TEST_UART_PORT_NUM UART_NUM_2
#define TEST_UART_BAUD_RATE 115200
#define TEST_UART_BUF_SIZE 256

// 测试间隔 (ms)
#define TEST_INTERVAL_MS 3000

// 内置LED (用于指示通信状态)
#define TEST_LED_GPIO GPIO_NUM_2

// BOOT按钮 (按下触发测试)
#define TEST_BOOT_BUTTON_GPIO GPIO_NUM_0

#endif // _BOARD_CONFIG_H_
