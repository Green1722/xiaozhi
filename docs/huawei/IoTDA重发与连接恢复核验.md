# IoTDA 重发与连接恢复核验

更新：2026-11-11。本核验使用电脑和既有模拟测试设备身份，不需要体重秤。验证边界是电脑探针恢复连接、云端接收与业务去重；测量板缓存、板端自动重连及断电补传仍需硬件。

## 已完成且已验证

- 新增 `cloud/health_exam/iotda_replay_check.py`，保持现有探针与业务接口不变。
- 脚本发布前检查 HTTPS 健康接口、服务标识、查询鉴权、初始记录数，以及本轮编号尚不存在。
- 固定同一个记录编号、原测量时间和 175 cm / 70 kg 模拟值。首次上报入库后，向本进程连接函数注入一次失败，再恢复真实连接重发。
- 按业务主键精确查询，检查 BMI 为 22.86、来源为 synthetic、记录内容和接收时间不变、仪器记录总数只增加 1。不会仅在最新 50 条里查找。
- 证据 JSON 只保留必要的模拟测量和阶段时间，不包含设备密钥、查询密钥或原始异常 URL；拒绝覆盖已有输出文件。
- 本地执行 `.\.venv\Scripts\python.exe -m pytest cloud/health_exam/tests -q`，退出码 0，46 项通过，1 项既有 Starlette/httpx 弃用提示。新增测试使用模拟 MQTT socket 与真实 FastAPI/SQLite，不代表华为云实测。

## 2026-11-11 华为云实测

北京时间 21:31，恢复开发者空间内的 3002 体检服务和原 DevBridge 托管，外部 `/healthz` 返回 HTTP 200。临时启用测试转发规则后，运行本机重发核验脚本，退出码为 0。

| 检查 | 实测结果 |
|---|---|
| 首次上报 | 测试设备通过 TLS 和 MQTT 认证，收到 PUBACK |
| 首次入库 | `synthetic-20261111T133129936573Z`，175 cm、70 kg、BMI 22.86，来源为 synthetic |
| 连接恢复 | 在电脑进程注入一次连接失败，随后实际重连、认证并重发原报文，再次收到 PUBACK |
| 云端入库 | 记录数为 6 → 7 → 7，按业务主键查询到同一条记录，内容与接收时间保持一致 |
| 转发到达 | 该次启动后业务访问日志共有两条 `POST /api/iotda/properties`，第 11、14 行均为 HTTP 200。第 12 行是对本次业务主键的查询，返回 HTTP 200 |
| 清理 | IoTDA 规则显示未启动，DevBridge 显示暂无运行中的托管进程。外部入口再次返回 HTTP 404 `tunnel not found` |

两次 MQTT 确认发生于 UTC 13:31:30.359694 和 13:31:31.840623。Uvicorn 默认访问日志没有时间戳和 POST 请求体，按同一启动周期内仅有的两次回调、两次回调之间的本次主键查询及探针执行顺序关联。业务主键为 `9ad831e925db2b677df25aaeb43a99d97e5ee07d726fdc8a1669f4dacf420072`。本轮已通过模拟设备连接恢复、重复上报与云端去重验证。

本机原始脚本证据为 `D:/ICT大赛/output/iotda-replay-20261111T133128Z.json`。脚本生成时云端日志尚未人工核对，因此 JSON 内的转发确认字段保留原值。本次人工核对结果记录在上表。测量板实物的断网缓存、自动重连、断电补传和实际测量精度待实机验收。

## 网络恢复后的运行顺序

1. 在原开发者空间检查 3002 的 `/healthz`，按原启动方法恢复服务并保留数据库。恢复原 DevBridge 托管；外部 `/healthz` 应返回 200，未携带查询密钥的 `/api/exams` 应返回 401。
2. 确认原 `xiaozhi-health-exam-forward` 规则只匹配模拟设备，再启用。记录云端 `/tmp/health_exam_uvicorn.log` 中 POST `/api/iotda/properties` 的已有成功次数，或记录可按本轮编号关联的转发日志。
3. 在仓库根目录运行以下命令。设备配置与查询密钥放在仓库外；`HEALTH_BASE_URL` 必须是可信 HTTPS 源站，`HEALTH_API_KEY` 从本机私有配置加载，不能写入命令或提交。

```powershell
.\.venv\Scripts\python.exe -m cloud.health_exam.iotda_replay_check `
  --config 'D:\ICT大赛\私有配置\iotda-test-device.json' `
  --output 'D:\ICT大赛\output\iotda-replay-evidence-本轮唯一名称.json' `
  --instrument DEMO-01 --wait-seconds 30 --settle-seconds 10
```

本机已提供仓库外加载器，可自动读取现有私有配置，不显示密钥：

```powershell
.\.venv\Scripts\python.exe 'D:\ICT大赛\私有配置\run-iotda-replay-check.py' `
  --output 'D:\ICT大赛\output\iotda-replay-evidence-本轮唯一名称.json' `
  --wait-seconds 30 --settle-seconds 10
```

4. 脚本观察完成的状态为 `observations_complete_forwarding_log_confirmation_required`；退出码 0 仅表示脚本检查通过，`forwarding_duplicate_observed` 仍为 null。按 JSON 中 UTC 时间与编号，核对两次真实上报都到达业务服务且处理成功。没有其他上报的隔离窗口内，可结合新增两次 HTTP 回调成功与该记录仍只有一条；若有并发上报，需按编号关联日志，不能只比较请求次数。
5. 将补充日志与脚本证据一起归档，再判断云端去重是否通过。结束后先停转发规则，再停临时托管，核对页面状态。

## 验收口径

| 项目 | 本次可验证方式 | 通过后允许的结论 |
|---|---|---|
| 平台接收 | TLS、CONNACK、PUBACK | IoTDA 接受了模拟设备发布 |
| 首次入库 | 按同编号精确查询到原值与服务端 BMI | 首次自动转发与入库成功 |
| 重发去重 | 第二次到达日志 + 同一业务记录不变 + 总数只增加 1 | 此次真实云端重复上报未重复入库 |
| 连接恢复 | 注入一次失败，移除注入后再次真实认证与 PUBACK | 电脑探针能够重新连接并重发 |
| 硬件断网恢复 | 板端缓存、实际断网/恢复、重启与补传证据 | 本脚本不能替代，待硬件验收 |
