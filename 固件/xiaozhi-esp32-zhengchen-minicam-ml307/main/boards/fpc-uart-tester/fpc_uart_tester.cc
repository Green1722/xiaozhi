#include "esp_log.h"
#include "esp_err.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "driver/gpio.h"
#include "driver/ledc.h"

#include "config.h"

#include <string.h>

static const char* TAG = "fpc-uart-tester";

// 全局变量
static QueueHandle_t uart_queue;
static TaskHandle_t rx_task_handle = NULL;
static TaskHandle_t tx_task_handle = NULL;

// LED控制
static void led_on(void) {
    gpio_set_level(TEST_LED_GPIO, 1);
}

static void led_off(void) {
    gpio_set_level(TEST_LED_GPIO, 0);
}

static void led_blink(int times, int delay_ms) {
    for (int i = 0; i < times; i++) {
        led_on();
        vTaskDelay(pdMS_TO_TICKS(delay_ms));
        led_off();
        vTaskDelay(pdMS_TO_TICKS(delay_ms));
    }
}

// UART初始化
static void uart_init(void) {
    ESP_LOGI(TAG, "Initializing UART...");
    ESP_LOGI(TAG, "  TX Pin: GPIO%d", TEST_UART_TX_PIN & 0xFF);
    ESP_LOGI(TAG, "  RX Pin: GPIO%d", TEST_UART_RX_PIN & 0xFF);
    ESP_LOGI(TAG, "  Baud Rate: %d", TEST_UART_BAUD_RATE);

    uart_config_t uart_config = {
        .baud_rate = TEST_UART_BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    int intr_alloc_flags = 0;
    ESP_ERROR_CHECK(uart_driver_install(TEST_UART_PORT_NUM, TEST_UART_BUF_SIZE * 2, 0, 20, &uart_queue, intr_alloc_flags));
    ESP_ERROR_CHECK(uart_param_config(TEST_UART_PORT_NUM, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(TEST_UART_PORT_NUM, TEST_UART_TX_PIN, TEST_UART_RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

    ESP_LOGI(TAG, "UART initialized successfully");
}

// UART接收任务
static void uart_rx_task(void* arg) {
    uint8_t rx_buffer[TEST_UART_BUF_SIZE];
    ESP_LOGI(TAG, "UART RX task started");

    while (1) {
        int len = uart_read_bytes(TEST_UART_PORT_NUM, rx_buffer, TEST_UART_BUF_SIZE - 1, pdMS_TO_TICKS(100));
        if (len > 0) {
            rx_buffer[len] = '\0';
            ESP_LOGI(TAG, "UART RX [%d bytes]: %s", len, rx_buffer);
            led_blink(2, 100);  // 收到数据，LED闪烁2次
        }
    }
}

// UART发送任务 - 定期发送测试数据
static void uart_tx_task(void* arg) {
    uint8_t test_count = 0;
    ESP_LOGI(TAG, "UART TX task started");

    // 等待系统稳定
    vTaskDelay(pdMS_TO_TICKS(1000));

    while (1) {
        char tx_buffer[64];
        test_count++;
        snprintf(tx_buffer, sizeof(tx_buffer), "TEST:Hello_%d\r\n", test_count);
        
        int len = strlen(tx_buffer);
        int written = uart_write_bytes(TEST_UART_PORT_NUM, tx_buffer, len);
        
        if (written == len) {
            ESP_LOGI(TAG, "UART TX [%d bytes]: %s", written, tx_buffer);
            led_blink(1, 200);  // 发送成功，LED闪烁1次
        } else {
            ESP_LOGE(TAG, "UART TX failed, expected %d, wrote %d", len, written);
        }

        // 等待下一次发送
        vTaskDelay(pdMS_TO_TICKS(TEST_INTERVAL_MS));
    }
}

// 手动发送测试命令
static void send_test_command(const char* cmd) {
    int len = strlen(cmd);
    int written = uart_write_bytes(TEST_UART_PORT_NUM, cmd, len);
    if (written == len) {
        ESP_LOGI(TAG, "Sent command: %s", cmd);
        led_blink(1, 100);
    } else {
        ESP_LOGE(TAG, "Failed to send command: %s", cmd);
    }
}

// GPIO初始化
static void gpio_init(void) {
    ESP_LOGI(TAG, "Initializing GPIO...");

    // LED GPIO
    gpio_reset_pin(TEST_LED_GPIO);
    gpio_set_direction(TEST_LED_GPIO, GPIO_MODE_OUTPUT);
    led_off();

    // BOOT按钮 GPIO (输入上拉)
    gpio_reset_pin(TEST_BOOT_BUTTON_GPIO);
    gpio_set_direction(TEST_BOOT_BUTTON_GPIO, GPIO_MODE_INPUT);
    gpio_set_pull_mode(TEST_BOOT_BUTTON_GPIO, GPIO_PULLUP_ONLY);

    ESP_LOGI(TAG, "GPIO initialized successfully");
}

// 按钮检测任务
static void button_task(void* arg) {
    ESP_LOGI(TAG, "Button task started");
    int last_button_state = 1;  // 默认高电平（未按下）

    while (1) {
        int button_state = gpio_get_level(TEST_BOOT_BUTTON_GPIO);
        
        // 检测按钮按下（低电平）
        if (button_state == 0 && last_button_state == 1) {
            ESP_LOGI(TAG, "Button pressed!");
            led_blink(3, 100);
            
            // 发送测试命令
            send_test_command("TEST:Button\r\n");
        }
        
        last_button_state = button_state;
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

// 应用入口
extern "C" void app_main(void) {
    ESP_LOGI(TAG, "===========================================");
    ESP_LOGI(TAG, "  FPC UART Tester");
    ESP_LOGI(TAG, "  Version: 1.0.0");
    ESP_LOGI(TAG, "===========================================");
    ESP_LOGI(TAG, "  TX: GPIO%d -> 主设备 GPIO8 (RX)", TEST_UART_TX_PIN & 0xFF);
    ESP_LOGI(TAG, "  RX: GPIO%d <- 主设备 GPIO7 (TX)", TEST_UART_RX_PIN & 0xFF);
    ESP_LOGI(TAG, "  Baud: %d", TEST_UART_BAUD_RATE);
    ESP_LOGI(TAG, "===========================================");

    // 初始化GPIO
    gpio_init();

    // 初始化UART
    uart_init();

    // 创建任务
    xTaskCreate(uart_rx_task, "uart_rx", 4096, NULL, 5, &rx_task_handle);
    xTaskCreate(uart_tx_task, "uart_tx", 4096, NULL, 4, &tx_task_handle);
    xTaskCreate(button_task, "button", 2048, NULL, 3, NULL);

    ESP_LOGI(TAG, "All tasks started");
    ESP_LOGI(TAG, "LED will blink on TX/RX activity");
    ESP_LOGI(TAG, "Press BOOT button to send test command");
}
