#pragma once

// ============================================================
//  PhysicalExamControl — 配置文件
//  所有需要修改的参数集中在此处，烧录前改好即可，无需动主程序。
// ============================================================

// ── WiFi（支持多组，逐个尝试）────────────────────────────────
// 可增减条目，ESP32 上电后从上往下依次尝试，连上即停止；全部失败则进入 SmartConfig。
// 注意：ESP32 仅支持 2.4 GHz，若热点同时有 5G/6G 频段请填写 2.4G 的 SSID
#define CFG_WIFI_COUNT 2
static const char* CFG_WIFI_SSIDS[]  = {
    //"iot421_6G",    // 第 1 个 WiFi（优先尝试）
    //"备用热点SSID", // 第 2 个 WiFi（第 1 个失败后尝试），不需要可删掉这行
};
static const char* CFG_WIFI_PASSES[] = {
    //"REPLACE_ME",   // 第 1 个 WiFi 密码
    //"REPLACE_ME", // 第 2 个 WiFi 密码
};

// ── 小智 MCP WebSocket 端点（含 Token）────────────────────────
#define CFG_MCP_ENDPOINT     "wss://api.xiaozhi.me/mcp/?token=REPLACE_ME"

// ── 仪器序号（NVS 可远程覆盖，此处为出厂默认值）──────────────
#define CFG_INSTRUMENT_ID    "HW-001"

// ── MQTT ────────────────────────────────────────────────────
#define CFG_MQTT_SERVER      "47.97.8.221"
#define CFG_MQTT_PORT        1883
#define CFG_MQTT_CLIENT_ID   "ESP32_PhysicalExam"

// ── MQTT 主题 ────────────────────────────────────────────────
#define CFG_TOPIC_INSTRUMENT_DATA  "体检中心/仪器/身高体重"
#define CFG_TOPIC_XIAOZHI_SPEAK    "体检中心/小智/播报"
#define CFG_TOPIC_UPLOAD_STATUS    "体检中心/数据/状态"

// ── SmartConfig（ESP-Touch 一键配网）────────────────────────
// WiFi 连接失败时自动进入 SmartConfig 等待配网；手机用 ESP-Touch App 发送凭据
// 超时后放弃（单位：秒）；0 = 永不超时（一直等）
#define CFG_SMARTCONFIG_TIMEOUT_S  120

// ── SoftAP 配网页面（192.168.44.1）──────────────────────────
// 当 STA 模式连接失败时，设备会开启热点并提供网页用于配置 WiFi。
// 密码至少 8 位；若留空则创建开放热点。
#define CFG_SOFTAP_SSID      "esp32-Setup"
#define CFG_SOFTAP_PASS      ""
