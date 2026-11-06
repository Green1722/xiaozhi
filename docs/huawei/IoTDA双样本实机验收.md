# IoTDA 模拟上报与小智实机播报验收

2026-11-06 在华为云 IoTDA、开发者空间中的体检服务及小智实机上完成以下验收。上报来源为电脑模拟器，存储为 SQLite，MCP 通过 HTTPS 读取业务库中的指定记录。播报结果由现场用户听取确认。

| 样本 | IoTDA 记录编号 | 身高 / 体重 / BMI | 验收 |
|---|---|---|---|
| A | synthetic-20261106T070508247605Z | 175 cm / 70 kg / 22.86 | MQTT 确认、自动入库、MCP 同编号命中、实机播报正确 |
| B | synthetic-20261106T070548880632Z | 168 cm / 62 kg / 21.97 | MQTT 确认、自动入库、MCP 命中新编号、实机播报正确 |
| 不存在的编号 | 本轮生成的未上报模拟编号 | — | 小智提示未找到记录 |
| 入口关闭 | 恢复选择 B | — | HTTPS 返回 404，MCP 捕获 HTTP 错误，小智提示无法查询 |

此前同日另有一条记录 synthetic-20261106T064211130083Z 已验证相同 MQTT 报文重传后仍只有一条入库记录，原值未变。实机语音由现场听取确认，数据库的 speech_status 仍为 unconfirmed。自动设备回执需要另行实现和验收。

## 队友复跑

从仓库根目录运行，使用已装项目依赖的 Python。MCP 联调另需同一环境安装项目桥接用的 `mcp>=1.8.1,<2`、`websockets` 与 `python-dotenv`。在当前 shell 从私有配置加载 `HEALTH_BASE_URL`（可信的 HTTPS 业务入口）、`HEALTH_API_KEY`（查询密钥）和 `MCP_ENDPOINT`（小智智能体接入地址）。设备配置 JSON 使用现有探针格式，含 host、port、device_id、device_secret、service_id。私有配置与接入地址保存在仓库外。

1. 在华为开发者空间恢复体检服务并开启临时托管。核对 `/healthz` 返回 200，未鉴权的 `/api/exams` 返回 401，再开启仅匹配模拟设备的原 IoTDA 规则。启停细节见 [云端联调实测](云端联调实测_2026-11-05.md)。
2. 从仓库根目录用现有 `mcp_pipe.py` 启动一个独立的 stdio 工具。以以下结构新建本机私有 MCP 配置文件，其中 Python 路径和选择文件路径填实际绝对路径。将 `MCP_CONFIG` 指向该文件，然后运行 `python 小智/hight_weight/zhudong_mcp/mcp_pipe.py iotda-demo`。等日志出现 WebSocket 连接成功和 ListToolsRequest。
3. 先发 A，等实机播报后再发 B。每次用同一条记录编号核对发布输出、业务查询和 MCP 命中日志。只有业务库查到编号和数值均匹配的记录，发布命令才会写入选择文件。工具每次调用都会重新读取该文件并查询 HTTPS。
4. 把选择文件改为一个以 `synthetic-` 开头、从未上报过的编号，再查询一次。随后恢复 B 的编号，停 IoTDA 规则、关临时托管，再查询一次并核对失败提示。退出本地 MCP 桥接，保留证据。

MCP 配置示例

```json
{
  "mcpServers": {
    "iotda-demo": {
      "command": "D:/private/venv/Scripts/python.exe",
      "args": ["-m", "cloud.health_exam.iotda_demo", "--selection", "D:/private/selection.txt", "serve"]
    }
  }
}
```

上报命令示例

```powershell
python -m cloud.health_exam.iotda_demo --selection 'D:/private/selection.txt' publish --sample A --device 'D:/private/iotda-device.json'
python -m cloud.health_exam.iotda_demo --selection 'D:/private/selection.txt' publish --sample B --device 'D:/private/iotda-device.json'
```

默认仪器为 DEMO-01。若部署的模拟设备映射使用不同标识，两个命令及 MCP 配置都要在子命令前增加同一个 `--instrument` 参数。

## 参赛演示留证

连续录屏时先显示 A 的发布和入库编号，再收录小智读出 A 的声音。随后发 B，显示新编号和 MCP 命中，再收录 B 的声音。结尾演示找不到记录及关闭托管后的失败提示。画面中仅展示模拟数据和必要日志，隐藏端点 Token、密钥与账户信息。本机结构化验收证据为 `2026-11-06-IoTDA-双样本验收.json`，现场带声音的连续录像待录制。实测仪器采集、精度及设备侧断网恢复等体重秤到位后补验。
