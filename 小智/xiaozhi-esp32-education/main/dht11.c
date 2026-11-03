#include "dht11.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"
#include "esp_log.h"

static const char *TAG = "DHT11";

// Wait for a specific level on the pin, with a timeout in microseconds
static int wait_for_level(gpio_num_t pin, int level, int timeout_us) {
    int time_waited = 0;
    while (gpio_get_level(pin) != level) {
        if (time_waited > timeout_us) {
            return -1; // Timeout
        }
        esp_rom_delay_us(1);
        time_waited++;
    }
    return time_waited;
}

void dht11_init(gpio_num_t pin) {
    gpio_reset_pin(pin);
    // Keep it pulled up high normally
    gpio_set_direction(pin, GPIO_MODE_INPUT_OUTPUT_OD); // Open drain
    gpio_set_pull_mode(pin, GPIO_PULLUP_ONLY);          // Pull-up internally
    gpio_set_level(pin, 1);
}

int dht11_read(gpio_num_t pin, float *temperature, float *humidity) {
    uint8_t data[5] = {0, 0, 0, 0, 0};

    // 1. Host sends Start signal: Pull low for at least 18ms
    gpio_set_level(pin, 0);
    vTaskDelay(pdMS_TO_TICKS(20)); // We need to yield otherwise watchdog might reset

    // 2. Host pulls high and waits for 20-40us
    gpio_set_level(pin, 1);
    esp_rom_delay_us(30);

    // 3. DHT11 should now pull low for 80us, then pull high for 80us.
    gpio_set_direction(pin, GPIO_MODE_INPUT);

    // [关键修复]：因为 ESP32 多任务(网络、音频)频繁打断 CPU，导致原本微秒级的时序判定被拉长，
    // 从而出现校验和失败 (Checksum failed) 或者超时 (timeout)。
    // 这里使用临界区关闭任务调度，保证读取过程的一气呵成。
    portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
    portENTER_CRITICAL(&mux);

    // Wait for the pin to go low, then high, then low (start of data)
    // Relaxed timings for less precise hardware
    if (wait_for_level(pin, 0, 150) < 0) {
        portEXIT_CRITICAL(&mux);
        ESP_LOGE(TAG, "Response timeout (low)");
        dht11_init(pin);
        return -1; 
    }
    if (wait_for_level(pin, 1, 150) < 0) {
        portEXIT_CRITICAL(&mux);
        ESP_LOGE(TAG, "Response timeout (high)");
        dht11_init(pin);
        return -1; 
    }
    if (wait_for_level(pin, 0, 150) < 0) {
        portEXIT_CRITICAL(&mux);
        ESP_LOGE(TAG, "Response timeout (start transmission)");
        dht11_init(pin);
        return -1; 
    }

    // 4. Read 40 bits of data (5 bytes)
    for (int i = 0; i < 40; i++) { // 5 bytes * 8 bits
        // It should stay low for 50us
        if (wait_for_level(pin, 1, 100) < 0) {
            portEXIT_CRITICAL(&mux);
            ESP_LOGE(TAG, "Response timeout 50us (low)");
            return -1;
        }
        
        // It stays high for 26-28us for '0', and 70us for '1'
        int high_dur = wait_for_level(pin, 0, 200);
        if (high_dur < 0) {
            portEXIT_CRITICAL(&mux);
            ESP_LOGE(TAG, "Response timeout 26-70us (high)");
            return -1;
        }

        int byte_idx = i / 8;
        data[byte_idx] <<= 1;
        if (high_dur > 40) { // If it took longer than 40us, it's a '1'
            data[byte_idx] |= 1;
        }
    }

    portEXIT_CRITICAL(&mux);

    // Done reading, restore standard output high state
    dht11_init(pin);

    // 5. Verify checksum
    uint8_t checksum = data[0] + data[1] + data[2] + data[3];
    if (checksum != data[4]) {
        ESP_LOGE(TAG, "Checksum failed: %d vs expected %d", checksum, data[4]);
        return -2;
    }

    // For DHT11, data[0] is integral RH, data[1] is decimal RH
    // data[2] is integral T, data[3] is decimal T
    *humidity = data[0] + (data[1] * 0.1f);
    *temperature = data[2] + (data[3] * 0.1f);

    return 0;
}
