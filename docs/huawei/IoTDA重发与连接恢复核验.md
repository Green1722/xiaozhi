# IoTDA 重发与连接恢复核验

更新：2026-11-11。本核验使用电脑和既有模拟测试设备身份，不需要体重秤。验证边界是电脑探针恢复连接、云端接收与业务去重；测量板缓存、板端自动重连及断电补传仍需硬件。

## 已完成且已验证

- 新增 `cloud/health_exam/iotda_replay_check.py`，保持现有探针与业务接口不变。
- 脚本发布前检查 HTTPS 健康接口、服务标识、查询鉴权、初始记录数，以及本轮编号尚不存在。
- 固定同一个记录编号、原测量时间和 175 cm / 70 kg 模拟值。首次上报入库后，向本进程连接函数注入一次失败，再恢复真实连接重发。
- 按业务主键精确查询，检查 BMI 为 22.86、来源为 synthetic、记录内容和接收时间不变、仪器记录总数只增加 1。不会仅在最新 50 条里查找。
- 证据 JSON 只保留必要的模拟测量和阶段时间，不包含设备密钥、查询密钥或原始异常 URL；拒绝覆盖已有输出文件。
- 本地执行 `.\.venv\Scripts\python.exe -m pytest cloud/health_exam/tests -q`，退出码 0，46 项通过，1 项既有 Starlette/httpx 弃用提示。新增测试使用模拟 MQTT socket 与真实 FastAPI/SQLite，不代表华为云实测。

## 本次实际云端状态与未验证项

本轮前段通过原码道会话恢复了 3002 服务；码道报告 PID 17364、原数据库有 6 条记录。独立外部请求实际获得 `/healthz` HTTP 200，正文为 `{"status":"ok","service":"xiaozhi-health-exam"}`。这只证明当时服务可访问。

用户要求重新开始后，北京时间 11 月 11 日约 11:18 再次检查：开发者空间与联调入口 HTTPS 连接超时；域名可解析，本机 7892 代理监听存在，但通过代理及直连均未取得华为 HTTPS 响应。Edge 重新打开页面也未成功。不能据此判断云端进程是否仍运行。

**待完成：** <span style="color:red">本轮尚未启动 IoTDA 转发规则、尚未执行新脚本的真实上报和重发，未取得第二次转发到达日志。原 DevBridge 托管在前段已启动；网络中断后未能再次确认或停止，恢复连接后应优先核对并在验收结束时停止。</span>

历史证据保留：11 月 6 日记录 `synthetic-20261106T064211130083Z` 重发获得 PUBACK，查询到一条匹配且未变化的业务记录。后来的 `synthetic-20261106T082307293031Z` 仅有两次发布确认，云端去重结果仍待查询，不能套用前一次结果。仅凭“两次 PUBACK + 一条数据库记录”不能排除第二次转发未到达；本脚本不将此条件单独标记为云端去重验收成功。

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
