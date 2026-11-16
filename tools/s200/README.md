# S200 采集、IoTDA 上报与小智播报

在仓库根目录执行以下 PowerShell 命令。采集使用 Windows BLE，并依赖蓝牙适配器支持已验收的 Coded PHY 广播接收方式。

```powershell
py -3.13 -m venv tools/s200/.venv
$python = '.\tools\s200\.venv\Scripts\python.exe'
& $python -m pip install -r tools/s200/requirements.txt
New-Item -ItemType Directory -Force .s200-private | Out-Null
$env:XIAOZHI_CLOUD_BASE_URL = 'https://your-exam-service.example'
```

把示例服务地址替换成自己的体检服务 HTTPS 源地址。默认从仓库根目录的 `.s200-private/` 读取配置，该目录已加入 Git 忽略规则。也可用 `S200_PRIVATE_DIR` 指向仓库外的现有私有配置。文件格式如下，示例里的值须替换成本次联调的配置。

| 文件 | 内容 |
| --- | --- |
| `secrets.yaml` | 两行，分别为 `s200_mac: "AA:BB:CC:DD:EE:FF"` 和 `s200_bindkey: "替换成真实蓝牙解密密钥的十六进制文本"`。保留双引号。 |
| `iotda-measured-device.private.json` | `{"device_id":"DEVICE_ID","device_secret":"DEVICE_SECRET","host":"IOTDA_DEVICE_HOST","port":8883}`。用 IoTDA 设备接入域名和你自己的测量设备身份。 |
| `iotda-measured-binding.json` | `{"DEVICE_ID":{"instrument_id":"S200-PC-001","source":"measured"}}`。键要与设备配置一致，仪器编号要与体检服务映射一致。 |
| `xiaozhi-iotda.private.env` | 一行 `HEALTH_API_KEY=替换成体检服务密钥`。 |
| `xiaozhi-mcp-endpoint.txt` | 一行小智智能体的 MCP WSS 地址。仅问答播报需要。 |

云端需配置 `PhysicalExam` 物模型、转发规则和同一设备的 `measured` 映射。见[云端转发配置](../../docs/huawei/IoTDA转发部署与验收.md)。待终端提示等待测量后再上秤，示例身高 175 请换成本次身高。

```powershell
& $python tools/s200/send-measured-iotda.py --publish --height-cm 175
```

上报脚本确认云端记录匹配后，会在私有目录保存本次查询目标。问答复验时，在同一个 PowerShell 环境启动桥接，再问小智「查询体检数据」。该桥接查询最后一次已核验的目标记录。

```powershell
& $python tools/s200/start-xiaozhi-iotda-measured.py
```

主动播报需先配置 `XIAOZHI_TTS_PUSH_URL` 为指向目标小智设备的 HTTPS 推送接口，接口接收 `{"text":"播报内容"}`。再给采集命令加 `--announce`，明确适用成人 BMI 参考时加 `--confirmed-adult`。实机主动开口待验收。采集日志、实测数据和推送状态写到私有目录。
