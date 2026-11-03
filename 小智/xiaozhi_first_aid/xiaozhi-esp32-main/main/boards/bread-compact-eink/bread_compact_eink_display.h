#ifndef __BREAD_COMPACT_EINK_DISPLAY_H__
#define __BREAD_COMPACT_EINK_DISPLAY_H__

#include <driver/gpio.h>
#include <esp_lcd_panel_io.h>
#include <esp_lcd_panel_ops.h>
#include <esp_timer.h>
#include <lvgl.h>
#include "display.h"

/* Eink display pin configuration */
typedef struct {
    gpio_num_t cs;
    gpio_num_t dc;
    gpio_num_t rst;
    gpio_num_t busy;
    gpio_num_t mosi;
    gpio_num_t scl;
    int spi_host;
    int width;
    int height;
    int buffer_len;
} eink_config_t;

class BreadCompactEinkDisplay : public Display {
public:
    explicit BreadCompactEinkDisplay(const eink_config_t& cfg);
    ~BreadCompactEinkDisplay();

    void SetupUI() override;
    void SetStatus(const char* status) override;
    void ShowNotification(const char* notification, int duration_ms = 3000) override;
    void SetEmotion(const char* emotion) override;
    void SetChatMessage(const char* role, const char* content) override;
    void ClearChatMessages() override;
    void UpdateStatusBar(bool update_all = false) override;

    // Eink hardware control
    void EPD_Init();
    void EPD_Clear();
    void EPD_Display();
    void EPD_DrawColorPixel(uint16_t x, uint16_t y, uint8_t color);
    void EPD_DisplayPart();

private:
    void spi_gpio_init();
    void spi_port_init();
    void read_busy();
    void SPI_SendByte(uint8_t data);
    void EPD_SendData(uint8_t data);
    void EPD_SendCommand(uint8_t command);
    void writeBytes(const uint8_t* data, int len);
    void EPD_SetWindows(uint16_t xs, uint16_t xe, uint16_t ys, uint16_t ye);
    void EPD_SetCursor(uint16_t xs, uint16_t ys);
    void EPD_SetLut(const uint8_t* lut);
    void EPD_TurnOnDisplay();
    void EPD_TurnOnDisplayPart();

    static void lvgl_flush_cb(lv_display_t* disp, const lv_area_t* area, uint8_t* color_p);
    static void flash_task(void* arg);

    eink_config_t cfg_;
    spi_device_handle_t spi_ = nullptr;
    uint8_t* buffer_ = nullptr;

    lv_display_t* disp_ = nullptr;
    TaskHandle_t flash_task_handle_ = nullptr;
    bool epd_initialized_ = false;
    bool flash_done_ = false;

    static constexpr int FLASH_INTERVAL_MS = 2000;
};

#endif
