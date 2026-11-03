#include "wifi_board.h"
#include "audio_codec.h"
#include "display/oled_display.h"
#include "system_reset.h"
#include "application.h"
#include "button.h"
#include "config.h"
#include "mcp_server.h"
#include "lamp_controller.h"
#include "led/single_led.h"
#include "assets/lang_config.h"

#include <esp_log.h>
#include <driver/i2c_master.h>
#include <driver/i2s_std.h>
#include <esp_lcd_panel_ops.h>
#include <esp_lcd_panel_vendor.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <cmath>
#include <cstring>
#include <vector>
#include <mutex>

#ifdef SH1106
#include <esp_lcd_panel_sh1106.h>
#endif

#define TAG "CompactWifiBoard"

// ── 外部 I2S Slave Codec ──────────────────────────────────────────
// I2S_NUM_0：扬声器（Master）
// I2S_NUM_1：接收测量板 I2S 输出（Slave，G13/G14/G21）
// 检测到有效音频时自动通知触发任务调用 StartListening()
//─────────────────────────────────────────────────────────────────

// 触发任务句柄（在 codec Read() 中向其发通知）
static TaskHandle_t s_ext_trigger_task = nullptr;

class ExternalTriggerCodec : public AudioCodec {
public:
    ExternalTriggerCodec() {
        input_sample_rate_  = AUDIO_INPUT_SAMPLE_RATE;
        output_sample_rate_ = AUDIO_OUTPUT_SAMPLE_RATE;
        SetupSpeaker();
        SetupExternalSlave();
    }

    virtual ~ExternalTriggerCodec() {
        if (rx_handle_) { i2s_channel_disable(rx_handle_); i2s_del_channel(rx_handle_); }
        if (tx_handle_) { i2s_channel_disable(tx_handle_); i2s_del_channel(tx_handle_); }
    }

    virtual void EnableInput(bool enable) override {
        if (enable == input_enabled_) return;
        if (enable) i2s_channel_enable(rx_handle_);
        else        i2s_channel_disable(rx_handle_);
        AudioCodec::EnableInput(enable);
    }

    virtual void EnableOutput(bool enable) override {
        if (enable == output_enabled_) return;
        if (enable) i2s_channel_enable(tx_handle_);
        else        i2s_channel_disable(tx_handle_);
        AudioCodec::EnableOutput(enable);
    }

protected:
    bool     audio_active_   = false;
    std::mutex read_mutex_;

    void SetupSpeaker() {
        // I2S_NUM_0 Master — 扬声器
        i2s_chan_config_t chan_cfg = {
            .id                 = (i2s_port_t)0,
            .role               = I2S_ROLE_MASTER,
            .dma_desc_num       = AUDIO_CODEC_DMA_DESC_NUM,
            .dma_frame_num      = AUDIO_CODEC_DMA_FRAME_NUM,
            .auto_clear_after_cb  = true,
            .auto_clear_before_cb = false,
            .intr_priority      = 0,
        };
        ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, &tx_handle_, nullptr));

        i2s_std_config_t std_cfg = {
            .clk_cfg = {
                .sample_rate_hz = (uint32_t)output_sample_rate_,
                .clk_src        = I2S_CLK_SRC_DEFAULT,
                .mclk_multiple  = I2S_MCLK_MULTIPLE_256,
#ifdef I2S_HW_VERSION_2
                .ext_clk_freq_hz = 0,
#endif
            },
            .slot_cfg = {
                .data_bit_width = I2S_DATA_BIT_WIDTH_32BIT,
                .slot_bit_width = I2S_SLOT_BIT_WIDTH_AUTO,
                .slot_mode      = I2S_SLOT_MODE_MONO,
                .slot_mask      = I2S_STD_SLOT_LEFT,
                .ws_width       = I2S_DATA_BIT_WIDTH_32BIT,
                .ws_pol         = false,
                .bit_shift      = true,
#ifdef I2S_HW_VERSION_2
                .left_align = true, .big_endian = false, .bit_order_lsb = false,
#endif
            },
            .gpio_cfg = {
                .mclk  = I2S_GPIO_UNUSED,
                .bclk  = AUDIO_I2S_SPK_GPIO_BCLK,
                .ws    = AUDIO_I2S_SPK_GPIO_LRCK,
                .dout  = AUDIO_I2S_SPK_GPIO_DOUT,
                .din   = I2S_GPIO_UNUSED,
                .invert_flags = { false, false, false },
            },
        };
        ESP_ERROR_CHECK(i2s_channel_init_std_mode(tx_handle_, &std_cfg));
        ESP_LOGI(TAG, "ExternalTriggerCodec: speaker I2S_NUM_0 ready");
    }

    void SetupExternalSlave() {
        // I2S_NUM_1 Slave — 接收测量板 G13/G14/G21 的 I2S 音频
        i2s_chan_config_t chan_cfg = {
            .id                 = (i2s_port_t)1,
            .role               = I2S_ROLE_SLAVE,   // ← Slave 由测量板提供时钟
            .dma_desc_num       = AUDIO_CODEC_DMA_DESC_NUM,
            .dma_frame_num      = AUDIO_CODEC_DMA_FRAME_NUM,
            .auto_clear_after_cb  = false,
            .auto_clear_before_cb = false,
            .intr_priority      = 0,
        };
        ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, nullptr, &rx_handle_));

        i2s_std_config_t std_cfg = {
            .clk_cfg = {
                // Slave 模式下 sample_rate_hz 仅供驱动参考，实际时钟由 Master 提供
                .sample_rate_hz = (uint32_t)input_sample_rate_,
                .clk_src        = I2S_CLK_SRC_DEFAULT,
                .mclk_multiple  = I2S_MCLK_MULTIPLE_256,
#ifdef I2S_HW_VERSION_2
                .ext_clk_freq_hz = 0,
#endif
            },
            .slot_cfg = {
                .data_bit_width = I2S_DATA_BIT_WIDTH_32BIT,
                .slot_bit_width = I2S_SLOT_BIT_WIDTH_AUTO,
                .slot_mode      = I2S_SLOT_MODE_MONO,
                .slot_mask      = I2S_STD_SLOT_LEFT,
                .ws_width       = I2S_DATA_BIT_WIDTH_32BIT,
                .ws_pol         = false,
                .bit_shift      = true,
#ifdef I2S_HW_VERSION_2
                .left_align = true, .big_endian = false, .bit_order_lsb = false,
#endif
            },
            .gpio_cfg = {
                .mclk  = I2S_GPIO_UNUSED,
                .bclk  = EXT_I2S_BCLK_PIN,   // G13 ← 测量板 GPIO13 BCLK
                .ws    = EXT_I2S_WS_PIN,      // G14 ← 测量板 GPIO14 WS
                .dout  = I2S_GPIO_UNUSED,
                .din   = EXT_I2S_DIN_PIN,     // G21 ← 测量板 GPIO21 DOUT
                .invert_flags = { false, false, false },
            },
        };
        ESP_ERROR_CHECK(i2s_channel_init_std_mode(rx_handle_, &std_cfg));
        ESP_LOGI(TAG, "ExternalTriggerCodec: external I2S_NUM_1 Slave ready (G13/G14/G21)");
    }

    virtual int Write(const int16_t* data, int samples) override {
        std::vector<int32_t> buffer(samples);
        int32_t vol = (int32_t)(pow((double)output_volume_ / 100.0, 2) * 65536);
        for (int i = 0; i < samples; i++) {
            int64_t t = (int64_t)data[i] * vol;
            buffer[i] = t > INT32_MAX ? INT32_MAX : t < INT32_MIN ? INT32_MIN : (int32_t)t;
        }
        size_t bytes_written;
        ESP_ERROR_CHECK(i2s_channel_write(tx_handle_, buffer.data(),
                                          samples * sizeof(int32_t), &bytes_written, portMAX_DELAY));
        return (int)(bytes_written / sizeof(int32_t));
    }

    virtual int Read(int16_t* dest, int samples) override {
        std::lock_guard<std::mutex> lock(read_mutex_);
        size_t bytes_read = 0;
        std::vector<int32_t> buf32(samples);

        // Slave 模式：Master 不发送时会超时，返回静音；Master 发送时读到真实数据
        esp_err_t ret = i2s_channel_read(rx_handle_, buf32.data(),
                                          samples * sizeof(int32_t),
                                          &bytes_read, pdMS_TO_TICKS(120));

        if (ret == ESP_ERR_TIMEOUT || bytes_read == 0) {
            // 测量板没有在发送 → 返回静音
            memset(dest, 0, samples * sizeof(int16_t));
            audio_active_ = false;
            return samples;
        }

        int n = (int)(bytes_read / sizeof(int32_t));
        bool has_signal = false;
        for (int i = 0; i < n; i++) {
            int32_t v = buf32[i] >> 12;
            dest[i] = v > INT16_MAX ? INT16_MAX : v < -INT16_MAX ? -INT16_MAX : (int16_t)v;
            if (abs(dest[i]) > 200) has_signal = true;
        }

        // 首次检测到有效音频 → 通知触发任务
        if (has_signal && !audio_active_) {
            audio_active_ = true;
            if (s_ext_trigger_task) {
                xTaskNotify(s_ext_trigger_task, 1, eSetValueWithOverwrite);
            }
        }
        if (!has_signal) {
            audio_active_ = false;   // 音频结束，重置，允许下次触发
        }
        return n;
    }
};

class CompactWifiBoard : public WifiBoard {
private:
    i2c_master_bus_handle_t display_i2c_bus_;
    esp_lcd_panel_io_handle_t panel_io_ = nullptr;
    esp_lcd_panel_handle_t panel_ = nullptr;
    Display* display_ = nullptr;
    Button boot_button_;
    Button touch_button_;
    Button volume_up_button_;
    Button volume_down_button_;

    void InitializeDisplayI2c() {
        i2c_master_bus_config_t bus_config = {
            .i2c_port = (i2c_port_t)0,
            .sda_io_num = DISPLAY_SDA_PIN,
            .scl_io_num = DISPLAY_SCL_PIN,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .intr_priority = 0,
            .trans_queue_depth = 0,
            .flags = {
                .enable_internal_pullup = 1,
            },
        };
        ESP_ERROR_CHECK(i2c_new_master_bus(&bus_config, &display_i2c_bus_));
    }

    void InitializeSsd1306Display() {
        // SSD1306 config
        esp_lcd_panel_io_i2c_config_t io_config = {
            .dev_addr = 0x3C,
            .on_color_trans_done = nullptr,
            .user_ctx = nullptr,
            .control_phase_bytes = 1,
            .dc_bit_offset = 6,
            .lcd_cmd_bits = 8,
            .lcd_param_bits = 8,
            .flags = {
                .dc_low_on_data = 0,
                .disable_control_phase = 0,
            },
            .scl_speed_hz = 400 * 1000,
        };

        ESP_ERROR_CHECK(esp_lcd_new_panel_io_i2c_v2(display_i2c_bus_, &io_config, &panel_io_));

        ESP_LOGI(TAG, "Install SSD1306 driver");
        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = -1;
        panel_config.bits_per_pixel = 1;

        esp_lcd_panel_ssd1306_config_t ssd1306_config = {
            .height = static_cast<uint8_t>(DISPLAY_HEIGHT),
        };
        panel_config.vendor_config = &ssd1306_config;

#ifdef SH1106
        ESP_ERROR_CHECK(esp_lcd_new_panel_sh1106(panel_io_, &panel_config, &panel_));
#else
        ESP_ERROR_CHECK(esp_lcd_new_panel_ssd1306(panel_io_, &panel_config, &panel_));
#endif
        ESP_LOGI(TAG, "SSD1306 driver installed");

        // Reset the display
        ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_));
        if (esp_lcd_panel_init(panel_) != ESP_OK) {
            ESP_LOGE(TAG, "Failed to initialize display");
            display_ = new NoDisplay();
            return;
        }
        ESP_ERROR_CHECK(esp_lcd_panel_invert_color(panel_, false));

        // Set the display to on
        ESP_LOGI(TAG, "Turning display on");
        ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel_, true));

        display_ = new OledDisplay(panel_io_, panel_, DISPLAY_WIDTH, DISPLAY_HEIGHT, DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y);
    }

    void InitializeButtons() {
        boot_button_.OnClick([this]() {
            auto& app = Application::GetInstance();
            if (app.GetDeviceState() == kDeviceStateStarting) {
                EnterWifiConfigMode();
                return;
            }
            app.ToggleChatState();
        });
        touch_button_.OnPressDown([this]() {
            Application::GetInstance().StartListening();
        });
        touch_button_.OnPressUp([this]() {
            Application::GetInstance().StopListening();
        });

        volume_up_button_.OnClick([this]() {
            auto codec = GetAudioCodec();
            auto volume = codec->output_volume() + 10;
            if (volume > 100) {
                volume = 100;
            }
            codec->SetOutputVolume(volume);
            GetDisplay()->ShowNotification(Lang::Strings::VOLUME + std::to_string(volume));
        });

        volume_up_button_.OnLongPress([this]() {
            GetAudioCodec()->SetOutputVolume(100);
            GetDisplay()->ShowNotification(Lang::Strings::MAX_VOLUME);
        });

        volume_down_button_.OnClick([this]() {
            auto codec = GetAudioCodec();
            auto volume = codec->output_volume() - 10;
            if (volume < 0) {
                volume = 0;
            }
            codec->SetOutputVolume(volume);
            GetDisplay()->ShowNotification(Lang::Strings::VOLUME + std::to_string(volume));
        });

        volume_down_button_.OnLongPress([this]() {
            GetAudioCodec()->SetOutputVolume(0);
            GetDisplay()->ShowNotification(Lang::Strings::MUTED);
        });
    }

    // 物联网初始化，逐步迁移到 MCP 协议
    void InitializeTools() {
        static LampController lamp(LAMP_GPIO);
    }

    // 启动外部触发任务：等待 codec 通知 → 调用 StartListening()
    void InitializeExternalTriggerTask() {
        xTaskCreate([](void*) {
            while (true) {
                uint32_t val = 0;
                // 阻塞等待 codec 的 xTaskNotify 通知
                xTaskNotifyWait(0x00, 0xFFFFFFFF, &val, portMAX_DELAY);
                if (val == 1) {
                    auto& app = Application::GetInstance();
                    // 仅在空闲或连接状态下触发，避免打断正在进行的对话
                    DeviceState state = app.GetDeviceState();
                    if (state == kDeviceStateIdle || state == kDeviceStateConnecting) {
                        ESP_LOGI(TAG, "[ExtTrigger] 检测到外部 I2S 音频，触发 StartListening()");
                        app.StartListening();
                    }
                }
            }
        }, "ext_trigger", 4096, nullptr, 5, &s_ext_trigger_task);
        ESP_LOGI(TAG, "外部 I2S 触发任务已启动");
    }

public:
    CompactWifiBoard() :
        boot_button_(BOOT_BUTTON_GPIO),
        touch_button_(TOUCH_BUTTON_GPIO),
        volume_up_button_(VOLUME_UP_BUTTON_GPIO),
        volume_down_button_(VOLUME_DOWN_BUTTON_GPIO) {
        InitializeDisplayI2c();
        InitializeSsd1306Display();
        InitializeButtons();
        InitializeTools();
        InitializeExternalTriggerTask();
    }

    virtual Led* GetLed() override {
        static SingleLed led(BUILTIN_LED_GPIO);
        return &led;
    }

    virtual AudioCodec* GetAudioCodec() override {
        // I2S_NUM_0 = 扬声器 Master (GPIO15/16/7)
        // I2S_NUM_1 = 外部 I2S Slave  (GPIO13/14/21 ← 测量板)
        static ExternalTriggerCodec audio_codec;
        return &audio_codec;
    }

    virtual Display* GetDisplay() override {
        return display_;
    }
};

DECLARE_BOARD(CompactWifiBoard);
