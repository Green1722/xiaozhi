# 征辰科技 MiniCam (ML307 版)

主控：ESP32-S3，4G 联网（ML307 Cat.1 模组），自带 LCD。

## 1. 准备 ESP-IDF 环境

- **ESP-IDF 版本**：v5.4 或更高
- 克隆本仓库后，进入项目根目录初始化子模块：

```bash
git submodule update --init --recursive
```

## 2. 设置编译目标

```bash
idf.py set-target esp32s3
```

## 3. 选择板子

```bash
idf.py menuconfig
```

依次进入：

```
Xiaozhi Assistant  --->
    Board Type  --->
        征辰科技MiniCam(ML307)      <*>
```

保存退出。

## 4. 配置 Flash 与 PSRAM（如果 menuconfig 没自动选）

```
Serial flasher config  --->
    Flash size  --->  8 MB (或按实际模组选择)
```

## 5. 编译

```bash
idf.py build
```

## 6. 烧录

```bash
idf.py -p COMx flash monitor
```

把 `COMx` 换成 Windows 上实际识别到的串口号（例如 `COM5`）。

按主板的 BOOT/RST 按钮，让 ESP32-S3 进入下载模式（如必要）。

## 7. 查看日志

烧录完成后会自动进入 monitor 模式：

```
I (...) zhengchen_minicam_ml307: Initializing FPC UART...
I (...) zhengchen_minicam_ml307:   TX Pin: FPC Pin 14 -> GPIO10
I (...) zhengchen_minicam_ml307:   RX Pin: FPC Pin 13 -> GPIO17
I (...) zhengchen_minicam_ml307:   Baud Rate: 115200
I (...) zhengchen_minicam_ml307: FPC UART task started
I (...) zhengchen_minicam_ml307: FPC UART initialized successfully
```

看到这四行说明 FPC UART 已就绪。

## 8. 生成量产固件（可选）

```bash
idf.py merge-bin
```

会在 `build/` 下生成 `xiaozhi.bin`，可用 `esptool.py` 直接烧录合并后的固件。

## 9. 与测试板（FPC_UART_Tester）连接

| 测试板 ESP32S3 | 方向 | 主板 (zhengchen-minicam-ml307) |
|---------------|------|-------------------------------|
| GPIO16 (TX)   | →    | GPIO17 (RX, FPC Pin 13)      |
| GPIO17 (RX)   | ←    | GPIO10 (TX, FPC Pin 14)      |
| GND           | ↔    | GND                          |

波特率 115200，8N1。
