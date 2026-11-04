# IoTDA 到体检业务系统：部署与验收

## 已实现与验证边界

已实现 `POST /api/iotda/properties`，接收官方 `device.property / report` 通知，校验平台 Token 签名和设备登记信息后复用原体检入库逻辑。未引入依赖、未改数据库结构、未修改或烧写固件。

本地 **37 项测试通过**，包括独立启动 uvicorn、通过真实 loopback HTTP 入库、重传去重、401/409、进程终止后重新启动仍保留一条记录。结果为 175 cm / 70 kg → BMI 22.86，来源为 synthetic，播报仍为 unconfirmed。

华为云四字段上报另已实测通过：`synthetic-20261104T154357161415Z`，175 cm、70 kg，`measured_at=2026-11-04T15:43:57.161415Z`。这是设备到 IoTDA 的真实路径；本地 HTTP 测试使用软件构造的通知，不是华为云自动转发。**两个测试不能拼接成完整云端闭环已通过。**

## 服务器配置

复用现有 `DATABASE_URL` 和 `HEALTH_API_KEY`；新增两个环境变量：

- `IOTDA_FORWARD_KEY`：独立的 24～32 位字母数字 Token，只供平台签名校验，与业务查询密钥不同；不要使用设备密钥。
- `IOTDA_DEVICES_JSON`：按真实设备 ID 配置 app_id、product_id、instrument_id、source。空配置时接口返回 503，不默认接收所有设备。

当前专用模拟设备的绑定如下（不包含密钥）：

```json
{"6aeb47a9cbb0cf6bb9944648_xiaozhi-simulator-001":{"app_id":"1e3ec2bf7fc144248ffef1bdfe568ebf","product_id":"6aeb47a9cbb0cf6bb9944648","instrument_id":"DEMO-01","source":"synthetic"}}
```

真实设备以后独立登记并设置 source=measured。客户端上报的 instrument_id、source、bmi 不作为可信值。

## 消息约定

产品模型 `PhysicalExam` 已有 `height_cm`、`weight_kg`、`record_id`、`measured_at` 四个只读属性。业务接口约定 record_id 为 1～96 位字母数字或 `_.:-`；尽管物模型字符串容量为128，不能超出业务限制。

measured_at 是设备采集时间，使用带 `Z` 的 UTC ISO 时间。同一次测量重传时，record_id、measured_at 和测量值必须保持不变。缺失采集时间返回422，不能用外层通知时间或服务接收时间冒充。

通知需保留完整 header 和 body；不要在平台 SQL 中仅选取 properties 后丢失 device_id、app_id 或 product_id。数据来源限定为“设备属性”，触发事件为“上报”。

## 平台转发与接收入口

接收地址应为部署完成后的 `https://<业务域名>/api/iotda/properties`。这只是路径格式，**当前没有已验收的业务 HTTPS 域名，不能直接复制示例投入运行。**

IoTDA HTTP 推送启用鉴权，Token 与服务器 IOTDA_FORWARD_KEY 保持一致。接口按官方规则校验 timestamp、nonce、signature 三个请求头；不是自定义 X-Iotda-Key。平台签名不覆盖请求体，部署必须使用 HTTPS 并正确配置证书。按官方控制台流程配置推送 CA/SNI，不能通过关闭证书校验解决连接失败。

现有 compose 只监听本机 127.0.0.1:8000；需要已有云服务器上的反向代理或平台正式提供的 HTTPS 服务入口。开发环境预览地址此前访问依赖华为登录，尚未验收为 IoTDA 服务到服务调用入口。未购买服务器、未开放本机公网端口、未创建未经验证的转发规则。

## 复验命令

在 `D:\ICT大赛\github-upload-xiaozhi` 运行：

```powershell
.\.venv\Scripts\python.exe -m pytest cloud\health_exam\tests -q
# 专用测试设备向真实 IoTDA 上报一次模拟记录：
.\.venv\Scripts\python.exe -m cloud.health_exam.iotda_probe --config 'D:\ICT大赛\私有配置\iotda-test-device.json'
```

37项测试中的 `test_iotda_http.py` 自动运行本地 HTTP 和重启验证，不需要云凭证，不修改现场数据库；测试结束后关闭测试服务。

## 自动转发上线后必须验证

先上报一个新 synthetic 编号，确认同一编号依次出现在 IoTDA 控制台、业务列表和按ID查询结果中；重传不新增，同编号改值返回409。随后重启业务服务并确认记录留存。最后才接入真实板卡和小智播报，保留“已请求”和“实机已播报”不同状态。

## 尚待完成

1. 取得并验收可由 IoTDA 访问的业务 HTTPS 入口，部署本次接口，再配置平台转发规则与签名 Token。
2. 实测 IoTDA 自动转发到业务入库，而非人工构造通知。
3. 取回码道补传代码包并审查合并。本轮资源管理器能找到原包，但下载未返回可用文件，Downloads未找到相应文件。
4. 真实板卡独立身份、采集时间同步、同记录播报与断网补传联调。

官方依据：[属性上报通知结构](https://support.huaweicloud.com/intl/en-us/api-iothub/iot_06_v5_01202.html)、[HTTP 转发与 Token 签名](https://support.huaweicloud.com/usermanual-iothub/iot_01_0001.html)、[规则动作配置](https://support.huaweicloud.com/api-iothub/iot_06_v5_01302.html)。
