#include "rgb_led.h"

#define TAG "RgbLed"

#define RGB_LEDC_TIMER        LEDC_TIMER_2
#define RGB_LEDC_MODE         LEDC_LOW_SPEED_MODE
#define RGB_LEDC_DUTY_RES    LEDC_TIMER_13_BIT  // 13位分辨率 (0-8191)
#define RGB_LEDC_FREQ_HZ     1000               // 1kHz刷新率
#define RGB_LED_MAX_DUTY     8191               // 13位最大值

RgbLed::RgbLed(gpio_num_t gpio_r, gpio_num_t gpio_g, gpio_num_t gpio_b) {
    // 配置定时器
    ledc_timer_config_t timer = {};
    timer.speed_mode = RGB_LEDC_MODE;
    timer.timer_num = RGB_LEDC_TIMER;
    timer.duty_resolution = RGB_LEDC_DUTY_RES;
    timer.freq_hz = RGB_LEDC_FREQ_HZ;
    timer.clk_cfg = LEDC_AUTO_CLK;
    ESP_ERROR_CHECK(ledc_timer_config(&timer));

    // 配置红色通道
    channel_r_.channel = LEDC_CHANNEL_0;
    channel_r_.duty = 0;
    channel_r_.gpio_num = gpio_r;
    channel_r_.speed_mode = RGB_LEDC_MODE;
    channel_r_.hpoint = 0;
    channel_r_.timer_sel = RGB_LEDC_TIMER;
    channel_r_.flags.output_invert = 0;
    ESP_ERROR_CHECK(ledc_channel_config(&channel_r_));

    // 配置绿色通道
    channel_g_.channel = LEDC_CHANNEL_1;
    channel_g_.duty = 0;
    channel_g_.gpio_num = gpio_g;
    channel_g_.speed_mode = RGB_LEDC_MODE;
    channel_g_.hpoint = 0;
    channel_g_.timer_sel = RGB_LEDC_TIMER;
    channel_g_.flags.output_invert = 0;
    ESP_ERROR_CHECK(ledc_channel_config(&channel_g_));

    // 配置蓝色通道
    channel_b_.channel = LEDC_CHANNEL_2;
    channel_b_.duty = 0;
    channel_b_.gpio_num = gpio_b;
    channel_b_.speed_mode = RGB_LEDC_MODE;
    channel_b_.hpoint = 0;
    channel_b_.timer_sel = RGB_LEDC_TIMER;
    channel_b_.flags.output_invert = 0;
    ESP_ERROR_CHECK(ledc_channel_config(&channel_b_));

    // 初始化颜色为关闭状态
    current_r_ = 0;
    current_g_ = 0;
    current_b_ = 0;
    brightness_ = 100;
    
    initialized_ = true;
    ESP_LOGI(TAG, "RGB LED initialized on GPIO R=%d, G=%d, B=%d", gpio_r, gpio_g, gpio_b);
}

RgbLed::~RgbLed() {
    if (initialized_) {
        ledc_set_duty(channel_r_.speed_mode, channel_r_.channel, 0);
        ledc_set_duty(channel_g_.speed_mode, channel_g_.channel, 0);
        ledc_set_duty(channel_b_.speed_mode, channel_b_.channel, 0);
        ledc_update_duty(channel_r_.speed_mode, channel_r_.channel);
        ledc_update_duty(channel_g_.speed_mode, channel_g_.channel);
        ledc_update_duty(channel_b_.speed_mode, channel_b_.channel);
    }
}

void RgbLed::SetColor(uint8_t r, uint8_t g, uint8_t b) {
    if (!initialized_) {
        return;
    }

    std::lock_guard<std::mutex> lock(mutex_);
    current_r_ = r;
    current_g_ = g;
    current_b_ = b;
    UpdateDuty();
    
    ESP_LOGI(TAG, "Set RGB color: R=%d, G=%d, B=%d", r, g, b);
}

void RgbLed::TurnOff() {
    if (!initialized_) {
        return;
    }

    std::lock_guard<std::mutex> lock(mutex_);
    current_r_ = 0;
    current_g_ = 0;
    current_b_ = 0;
    
    ledc_set_duty(channel_r_.speed_mode, channel_r_.channel, 0);
    ledc_set_duty(channel_g_.speed_mode, channel_g_.channel, 0);
    ledc_set_duty(channel_b_.speed_mode, channel_b_.channel, 0);
    ledc_update_duty(channel_r_.speed_mode, channel_r_.channel);
    ledc_update_duty(channel_g_.speed_mode, channel_g_.channel);
    ledc_update_duty(channel_b_.speed_mode, channel_b_.channel);
    
    ESP_LOGI(TAG, "RGB LED turned off");
}

void RgbLed::SetBrightness(uint8_t brightness) {
    if (!initialized_) {
        return;
    }
    
    brightness_ = brightness > 100 ? 100 : brightness;
    std::lock_guard<std::mutex> lock(mutex_);
    UpdateDuty();
    
    ESP_LOGI(TAG, "Set brightness: %d%%", brightness_);
}

void RgbLed::UpdateDuty() {
    // 计算亮度系数 (0-100 -> 0-1)
    float brightness_factor = brightness_ / 100.0f;
    
    // 将 0-255 的颜色值转换为 0-8191 的 duty 值
    // 共阳极 RGB LED: GPIO 拉低时点亮，所以 duty = 最大值 - 颜色值对应的高电平比例
    uint32_t duty_r = (uint32_t)((255 - current_r_) * 32.0f * brightness_factor);
    uint32_t duty_g = (uint32_t)((255 - current_g_) * 32.0f * brightness_factor);
    uint32_t duty_b = (uint32_t)((255 - current_b_) * 32.0f * brightness_factor);
    
    // 限制最大值
    duty_r = duty_r > RGB_LED_MAX_DUTY ? RGB_LED_MAX_DUTY : duty_r;
    duty_g = duty_g > RGB_LED_MAX_DUTY ? RGB_LED_MAX_DUTY : duty_g;
    duty_b = duty_b > RGB_LED_MAX_DUTY ? RGB_LED_MAX_DUTY : duty_b;
    
    ledc_set_duty(channel_r_.speed_mode, channel_r_.channel, duty_r);
    ledc_set_duty(channel_g_.speed_mode, channel_g_.channel, duty_g);
    ledc_set_duty(channel_b_.speed_mode, channel_b_.channel, duty_b);
    ledc_update_duty(channel_r_.speed_mode, channel_r_.channel);
    ledc_update_duty(channel_g_.speed_mode, channel_g_.channel);
    ledc_update_duty(channel_b_.speed_mode, channel_b_.channel);
}
