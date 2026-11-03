#ifndef RGB_LED_H_
#define RGB_LED_H_

#include <driver/gpio.h>
#include <driver/ledc.h>
#include <driver/ledc.h>
#include <esp_log.h>
#include <mutex>

class RgbLed {
public:
    RgbLed(gpio_num_t gpio_r, gpio_num_t gpio_g, gpio_num_t gpio_b);
    ~RgbLed();

    void SetColor(uint8_t r, uint8_t g, uint8_t b);
    void TurnOff();
    void SetBrightness(uint8_t brightness);
    
private:
    std::mutex mutex_;
    ledc_channel_config_t channel_r_, channel_g_, channel_b_;
    bool initialized_ = false;
    uint8_t current_r_, current_g_, current_b_;
    uint8_t brightness_ = 100;

    void UpdateDuty();
};

#endif  // RGB_LED_H_
