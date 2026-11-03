# 小智服务器获取身高体重数据流程

本文档说明小智服务器如何获取体检身高体重数据的完整流程。

## 整体架构

```
体检仪器 → MQTT Broker → MCP服务 → 小智服务器(api.xiaozhi.me)
                                    ↓
                              小智设备(WebSocket)
```

## 数据流程方式

### 方式一：通过 MCP 工具主动获取（推荐）

**流程：**

1. **数据采集阶段**
   ```
   体检仪器 → MQTT主题: 体检中心/仪器/身高体重
   ```
   - 仪器测量身高体重后，发布JSON数据到MQTT主题
   - 数据格式：
     ```json
     {
       "height": 170,
       "weight": 65,
       "height_cm": 170,
       "weight_kg": 65,
       "id": "exam_001",
       "timestamp": "2025-02-04 12:00:00"
     }
     ```

2. **MCP服务处理阶段**
   ```
   MCP服务订阅MQTT → 接收数据 → 处理并存储
   ```
   - MCP服务 (`health-exam-service`) 订阅 `体检中心/仪器/身高体重` 主题
   - 收到数据后自动处理：
     - 计算BMI
     - 生成医学建议
     - 存储到内存记录（最多100条）
     - 触发小智播报
     - 可选：上传到配置的服务器

3. **小智服务器获取数据**
   ```
   小智服务器 → MCP协议 → 调用工具 → 获取数据
   ```
   - 小智服务器通过 MCP WebSocket 连接调用 MCP 工具
   - 可调用的工具：
     
     **a) `get_last_person_height_weight()` - 获取最后一个人的身高体重**
     - 小智服务器调用此工具
     - MCP服务返回最后一个人的身高体重数据
     - 如果没有记录，会随机生成正常范围内的数据
     - 返回格式：
       ```json
       {
         "success": true,
         "message": "已成功向服务器推送最后一条体检数据",
         "data": {
           "height_cm": 170,
           "weight_kg": 65,
           "bmi": 22.5,
           "record_id": "exam_001",
           "timestamp": "2025-02-04 12:00:00",
           "is_generated": false
         },
         "uploaded": true
       }
       ```
     
     **b) `get_exam_records(limit)` - 获取多条记录**
     - 小智服务器调用此工具获取最近的体检记录
     - 可以指定获取数量（默认10条）
     - 返回格式：
       ```json
       {
         "success": true,
         "records": [
           {
             "id": "exam_001",
             "height_cm": 170,
             "weight_kg": 65,
             "bmi": 22.5,
             "advice": "您的身高为170厘米...",
             "timestamp": "2025-02-04 12:00:00"
           }
         ],
         "total_count": 5,
         "returned_count": 5
       }
       ```

### 方式二：通过 HTTP 接口主动推送（可选）

**流程：**

1. **配置上传接口**
   ```bash
   export PHYSICAL_EXAM_UPLOAD_URL="https://api.xiaozhi.me/api/exam/data"
   export PHYSICAL_EXAM_UPLOAD_ENABLED=true
   ```

2. **自动推送**
   - MCP服务处理完数据后，自动POST到配置的URL
   - 推送数据格式：
     ```json
     {
       "id": "exam_001",
       "height_cm": 170,
       "weight_kg": 65,
       "bmi": 22.5,
       "advice": "您的身高为170厘米...",
       "timestamp": "2025-02-04 12:00:00"
     }
     ```

3. **小智服务器接收**
   - 小智服务器需要提供HTTP接口接收数据
   - 接口需要处理POST请求并解析JSON

### 方式三：通过 MCP 工具直接处理（实时）

**流程：**

1. **小智服务器主动调用**
   ```
   小智服务器 → MCP工具: process_physical_exam() → 传入身高体重
   ```

2. **实时处理**
   - 小智服务器直接调用 `process_physical_exam(height_cm, weight_kg, record_id)`
   - MCP服务立即处理：
     - 计算BMI
     - 生成医学建议
     - 触发小智播报
     - 存储记录
     - 返回处理结果

3. **返回结果**
   ```json
   {
     "success": true,
     "record": {
       "id": "exam_001",
       "height_cm": 170,
       "weight_kg": 65,
       "bmi": 22.5,
       "advice": "您的身高为170厘米...",
       "timestamp": "2025-02-04 12:00:00"
     },
     "advice_spoken": true,
     "data_uploaded": true,
     "tts_text": "您的身高为170厘米..."
   }
   ```

## 推荐流程（方式一）

**最推荐的流程是方式一：**

1. **仪器自动上报** → MQTT主题
2. **MCP服务自动处理** → 存储记录
3. **小智服务器按需获取** → 调用 `get_last_person_height_weight()` 或 `get_exam_records()`

**优势：**
- 数据自动采集和处理
- 小智服务器可以按需获取，不依赖实时推送
- 支持获取历史记录
- 如果没有记录，会自动生成正常范围内的数据

## MCP 工具调用示例

### 小智服务器调用 `get_last_person_height_weight`

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "get_last_person_height_weight",
    "arguments": {}
  },
  "id": 1
}
```

### 小智服务器调用 `get_exam_records`

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "get_exam_records",
    "arguments": {
      "limit": 10
    }
  },
  "id": 2
}
```

## 数据存储

- **存储位置**：MCP服务内存中（`exam_records` 列表）
- **存储容量**：最多100条记录
- **存储内容**：每条记录包含：
  - `id`: 记录ID
  - `height_cm`: 身高（厘米）
  - `weight_kg`: 体重（公斤）
  - `bmi`: BMI指数
  - `advice`: 医学建议文本
  - `timestamp`: 时间戳

## 注意事项

1. **数据持久化**：当前数据存储在内存中，服务重启后数据会丢失。如需持久化，需要添加数据库存储。

2. **无记录处理**：当调用 `get_last_person_height_weight()` 且没有记录时，会自动生成正常范围内的随机数据（身高150-190cm，BMI 18.5-24）。

3. **MQTT连接**：MCP服务需要保持MQTT连接，才能接收仪器上报的数据。

4. **MCP连接**：小智服务器需要通过MCP WebSocket连接到MCP服务，才能调用工具获取数据。

