# SmartAgriBrain v1 统一通信与数据标准

本文件是 SmartAgriBrain 采集 ESP32、云端服务和 Web 前端的 MQTT/REST 目标契约，最后同步于 2026-07-23。2026-07-20 起，ESP32-C5 改为语音与显示终端，不再承担本文件中的传感器 MQTT 发布和执行器控制职责；最新设备分工见 [当前架构与目录状态](architecture-update-2026-07-20.md)。除本文件明确保留为部署配置的主机地址、账号和密钥外，字段名、单位、主题、路径、状态、返回结构和错误码必须完全一致。

当前普通 ESP32 已实现正式主题、QoS 1、持久会话、原子命令、水枪复合命令、ACK、遥测、状态和能力发布。MQTT JSON 已按 Topic 可推导信息完成精简，遥测保持 5 秒周期。前端/FastAPI 只使用真实 REST、EMQX MQTT 和设备 ACK 路径。代码一致性不替代实体硬件联调验收。

## 1. 固定架构与责任边界

从本标准生效起，系统只有一个对外后端服务，逻辑名称为 `smartagribrain-api`：

```text
采集 ESP32 <-> EMQX MQTT <-> smartagribrain-api <-> PostgreSQL/SQLite
                    ^                 ^       ^
                    |                 |       |
          C5 状态/助手事件 MQTT    REST/SSE  HTTP/WebSocket 语音
                    |                 |       |
            ESP32-C5 语音显示终端   Vue Dashboard
```

- 采集 ESP32 只通过 MQTT 上报遥测、状态、能力和命令 ACK；不直接调用 HTTP API。
- ESP32-C5 使用 FastAPI HTTP/WebSocket 传输语音音频，并通过 EMQX MQTT 接收 `view_state`、助手回复及发布状态、能力、助手请求和确认决定；它不发布农业传感器遥测，不订阅普通 ESP32 的 `command`，也不直接控制二维云台。
- 浏览器只调用 REST 和 SSE；不保存 MQTT 账号，不直接连接 Broker。
- `smartagribrain-api` 是 MQTT 客户端、数据库写入者、命令发布者和唯一 REST 服务。
- 当前工作区中可核验的集成服务位于 `前端/backend_api/`。`frontend_dashboard/` 只作为历史原型参考；不得同时让两个后端对外宣称是 `smartagribrain-api`。
- 前端 `VITE_API_BASE_URL` 必须只指向 `smartagribrain-api`。

## 2. 通用规则

### 2.1 标识符、字符集和时间

- 编码：全部 JSON、HTTP 与 MQTT 文本均为 UTF-8。
- `device_id`：小写字母、数字、`_`、`-`；正则 `^[a-z][a-z0-9_-]{2,63}$`。现场普通 ESP32 的协议标识固定为 `greenhouse_001_s3`；后缀 `_s3` 只是兼容命名，不代表芯片型号。
- `site_id`：现场设备固定为 `greenhouse_001`；MQTT 上行根据设备注册关系确定站点，不在每条设备消息中重复发送。
- `message_id`：遥测使用 UUID v4 小写字符串完成 QoS 1 去重。`command_id` 接受 UUID v4 或 1 至 20 位十进制字符串；一个逻辑命令只能使用一个 ID，设备按完整字符串幂等。
- 时间：所有 `*_at` 为 Unix Epoch 毫秒，UTC，JSON number，例 `1752220800123`。禁止秒级时间戳和本地化字符串。
- 时间不可信：ESP32 未完成 SNTP 时，`sampled_at` 为 `0`；服务端改用 `received_at` 保存和排序。
- 数值：JSON number；禁止 `NaN`、`Infinity`、字符串数字和隐式单位。
- 裸板联调：当前允许未接传感器时出现驱动默认值 `0`、DS18B20 的 `-127` 或浮空 ADC 值；这些数据仅用于验证链路，不能作为实体传感器验收结果。
- 版本：MQTT 主版本由 Topic 前缀 `smartagribrain/v1` 确定，JSON 不再重复 `schema_version`。不兼容修改必须更换 Topic 主版本。

### 2.2 统一设备能力名

现场普通 ESP32 当前只声明以下通用执行器：

- `grow_light`：GPIO14 补光灯，类型 `percent`，范围 0 至 90。

GPIO26 水泵、GPIO27 水平 SG90 和 GPIO13 俯仰 SG90 是水枪的内部部件，不得作为通用 `set` 命令或 `actuators` 能力单独声明；它们只能由 `target_position` 水枪复合命令驱动。`pump`、`pan`、`tilt`、`fan`、`alarm`、`curtain`、`heater`、`cooler`、`ventilation` 和 `co2_valve` 均不是当前可用的通用执行器。`light`、`heat`、`cool`、`vent`、`co2`、`waterDemand`、`lightDemand`、`panAngle`、`tiltAngle` 和 `smart_control_update` 均不是 v1 正式命令字段。后端只向能力声明为 `supported=true` 的执行器发布命令。

### 2.3 响应包装

所有 REST 成功响应必须使用以下结构：

```json
{
  "request_id": "d30fe9d7-c41f-47c3-b744-7e49426746fa",
  "data": {}
}
```

有分页时增加 `meta`：

```json
{
  "request_id": "d30fe9d7-c41f-47c3-b744-7e49426746fa",
  "data": [],
  "meta": { "next_cursor": "eyJvZmZzZXQiOjUwfQ", "limit": 50 }
}
```

所有 REST 失败响应必须使用以下结构：

```json
{
  "request_id": "d30fe9d7-c41f-47c3-b744-7e49426746fa",
  "error": {
    "code": "DEVICE_OFFLINE",
    "message": "设备当前离线，命令未发布。",
    "details": { "device_id": "greenhouse_001_s3" }
  }
}
```

服务端必须返回 `X-Request-Id`，其值与响应体 `request_id` 相同。客户端可传入 UUID 格式的 `X-Request-Id`；未传入时由服务端生成。

## 3. MQTT v1 契约

### 3.1 连接和安全

- 协议：MQTT 3.1.1，生产环境只允许 `mqtts://`，端口 `8883`。
- 所有环境：统一使用外部 EMQX Broker。优先使用 `mqtts://` 和 `8883`；若 EMQX 明确提供非 TLS 监听器，才可显式配置 `mqtt://`。不得回退到工作站本地 Broker。
- Client ID：设备为 `sab-dev-{device_id}`；后端为 `sab-api-{instance_id}`。
- 认证：每台设备独立用户名和密码，生产环境须使用设备证书或强随机密码。浏览器不得拥有 Broker 凭据。
- ACL：设备只能发布自身 `telemetry`、`status`、`capabilities`、`command_ack`，只能订阅自身 `command`。后端可读写全部设备主题。
- 会话：设备和后端均使用持久会话；客户端异常断开后 Broker 保留 QoS 1 的未确认消息。
- LWT：设备 LWT 必须发布离线 `status`，QoS 1、retain=true。

Broker 地址、用户名、密码、CA 证书是部署配置，不属于协议内容，不得写入仓库。

### 3.2 主题、QoS 和保留策略

固定主题前缀：`smartagribrain/v1/devices/{device_id}`。

- `.../telemetry`：设备发布，后端订阅，QoS 1，retain=false。用于周期传感器与执行器快照。
- `.../status`：设备发布，后端订阅，QoS 1，retain=true。用于在线状态与最后在线时间。
- `.../capabilities`：设备发布，后端订阅，QoS 1，retain=true。用于传感器、执行器和固件能力。
- `.../command`：后端发布，设备订阅，QoS 1，retain=false。用于单个待执行命令。
- `.../command_ack`：设备发布，后端订阅，QoS 1，retain=false。用于单个命令的最终 ACK。

禁止使用 `devices/...`、`telemetry/data` 或其他未列出主题。后端订阅：`smartagribrain/v1/devices/+/telemetry`、`+/status`、`+/capabilities`、`+/command_ack`。

### 3.3 设备能力消息

设备启动、固件升级和能力变化后必须立即发布能力消息；Broker 重连后也必须重新发布一次。

```json
{
  "reported_at": 1752220800123,
  "firmware": { "version": "0.3.0", "target": "esp32" },
  "sensors": {
    "temperature_c": true,
    "illuminance_lux": true,
    "co2_ppm": true,
    "soil_moisture_pct": true
  },
  "actuators": {
    "grow_light": { "supported": true, "type": "percent", "min": 0, "max": 90 }
  },
  "positioning": {
    "target_position_supported": true,
    "water_gun_control_supported": true,
    "water_gun_timed_spray_supported": true,
    "water_gun_max_duration_seconds": 86399,
    "dynamic_max_hz": 5,
    "calibration": "UN_CALIBRATED_PLACEHOLDER"
  }
}
```

`positioning.calibration` 明确表示当前坐标映射未实测，不得当作真实能力精度。设备身份从 capabilities Topic 推导；能力消息为 retained 快照，不需要消息级去重 ID。

### 3.4 遥测消息

设备每 5 秒发布一次；允许范围为 1 至 3600 秒。数据变化不影响周期发送。后端必须以 `(device_id, message_id)` 去重，以 `received_at` 记录接收时间。

```json
{
  "message_id": "4db84c21-6e68-460c-939b-e187f3061e51",
  "sampled_at": 1752220800000,
  "sensors": {
    "temperature_c": 26.5,
    "illuminance_lux": 1260.4,
    "co2_ppm": 612,
    "soil_moisture_pct": 54.2
  },
  "quality": {
    "temperature_c": "ok",
    "illuminance_lux": "ok",
    "co2_ppm": "ok",
    "soil_moisture_pct": "ok"
  },
  "actuators": {
    "grow_light": 60
  },
  "positioning": {
    "pan_deg": 90,
    "tilt_deg": 5,
    "calibration": "UN_CALIBRATED_PLACEHOLDER",
    "water_gun": {
      "active": false,
      "timed": false,
      "dynamic": false,
      "spray_ends_at": null,
      "sequence": 0
    }
  },
  "connectivity": { "rssi_dbm": -56 }
}
```

允许的 `quality` 值只有 `ok`、`stale`、`invalid`、`unsupported`。ESP32 当前对有限数值发布 `ok`，因此裸板默认值只表示链路数据，不能证明传感器存在。`message_id` 用于 QoS 1 去重；设备 ID 从 Topic 推导，站点从后端设备注册关系推导。能收到遥测已经说明发送时 Wi-Fi 和 MQTT 可用，因此连接对象只保留 RSSI。

### 3.5 在线状态消息

在线时发布：

```json
{
  "reported_at": 1752220800123,
  "online": true,
  "reason": "connected"
}
```

LWT 离线时发布相同结构，仅 `online=false`、`reason="unexpected_disconnect"`。正常停止前发布 `reason="shutdown"`。

状态为 retained 快照，设备身份从 Topic 推导，不使用 `message_id`。LWT 在连接建立时预先注册，因此 `reported_at` 可以为 `0`，后端以接收时间记录离线发生时间。

### 3.6 命令和 ACK 消息

补光灯使用单个原子 `set` 命令。水枪是唯一允许的复合命令，使用 `operation=target_position` 同时描述目标、二维舵机、水泵、定时和动态会话；它不得携带 AI 分析正文。

```json
{
  "command_id": "c820003f-b6c4-4f6d-a3e3-2194c7c77989",
  "expires_at": 1752220830123,
  "command": {
    "operation": "set",
    "target": "grow_light",
    "value": 60
  }
}
```

命令 Topic 已确定版本和目标设备。后端数据库继续保存 `site_id`、`source`、`reason` 和创建时间，设备链路只发送执行所需字段。`grow_light` 值域为 0 至 90 整数。`expires_at` 默认是创建时间后 30 秒；设备只接受尚未过期且不超过未来 300 秒的命令。

设备收到命令后必须在 5 秒内发布最终 ACK：

```json
{
  "command_id": "c820003f-b6c4-4f6d-a3e3-2194c7c77989",
  "acknowledged_at": 1752220800550,
  "state": "executed",
  "actual_value": 60,
  "feedback_verified": false,
  "error": null
}
```

设备 ACK 的 `state` 只能为 `executed` 或 `rejected`。`rejected` 时 `actual_value` 必须为 `null`，`error.code` 必须为本文件第 6 节定义的设备错误码。后端已保存原命令，ACK 不再回显命令、位置或水枪参数。设备必须在 RAM 中缓存最近 50 个 `command_id`，并保证每项至少保留 10 分钟；收到重复 ID 时不重复驱动硬件，直接重发首次 ACK。当前固件具备 50 项容量和覆盖淘汰，但尚未实现独立的 10 分钟保留计时。

命令状态机固定如下：

```text
REST accepted -> QUEUED -> PUBLISHED -> EXECUTED
                                  |          |
                                  |          +-> REJECTED
                                  +-> EXPIRED / DELIVERY_FAILED
任何等待 ACK 超过 expires_at -> TIMED_OUT
```

只有 `EXECUTED` 表示设备已写入控制输出且状态机无错误。当前 SG90 和水泵没有位置/流量反馈，因此该状态不表示物理动作经过传感器验证；`feedback_verified=false`。`QUEUED`、`PUBLISHED` 只表示后端接收或 Broker 已接受消息，前端不得显示“已执行”。

### 3.7 水枪复合命令扩展

水枪命令结构、静态/动态模式、定时字段、安全顺序和临时标定以 [ESP32 与后端通信要求](ESP32与后端通信.md) 为准。固定要求如下：

- `operation=target_position`、`target=position`。
- `position` 包含 `ground_range_mm` 和 `bearing_deg`。
- `bearing_deg` 范围固定为 -90 至 90 度，并线性映射到水平 SG90 的 0 至 180 度命令角。
- `ground_range_mm` 当前接受 300 至 1200 mm，并线性映射到垂直舵机 60 至 5 度；300 mm 对应竖直向上的 60 度，1200 mm 对应平行向前的 5 度。垂直轴所有写入强制限制在实体安全的 5 至 60 度。
- `water_gun` 包含 `mode`、`spray_enabled`、`pump_control_percent`、`session_id`、`sequence`、`spray_schedule`、`spray_duration_seconds`、`spray_ends_at`。
- `pump_control_percent` 由后端按实测两段距离功率模型计算，非零有效范围为 24% 至 100%；ESP32 只执行相同边界的最终限幅。
- 目标变化时先停泵，舵机稳定后才能开泵。
- `timed` 由 ESP32 本地单调时钟和后端停止命令双重保护。
- `dynamic` 使用 `session_id` 和严格递增 `sequence`；序号只能由后端为目标更新和 heartbeat 统一生成，Web 不得自行递增。设备可见保活中断 3 秒时停泵。
- Web 动态目标请求必须串行化并只保留发送期间的最新目标；相同位置的 heartbeat 不得使 ESP32 重复写舵机 PWM。
- 动态模式关闭喷水时 ESP32 仍须保留会话和最后序号，不能让延迟旧目标绕过乱序校验；只有退出动态模式才能清除该状态。
- 坐标到舵机角度及稳定等待仍须标记 `UN_CALIBRATED_PLACEHOLDER`；水泵功率已采用实测分段模型，不再使用该标记。

## 4. REST API v1 契约

### 4.1 访问规则

- Base URL：`https://{api-host}/api/v1`。
- `GET /health` 不需要认证；其他接口必须带 `Authorization: Bearer <access-token>`。
- 所有写操作必须带 `Idempotency-Key: <UUID>`；同一用户、同一路径、同一 Key 在 24 小时内只执行一次。
- `Content-Type: application/json; charset=utf-8`；病害图片上传接口除外。
- 对应命令的 `202 Accepted` 仅表示已进入后端命令状态机，不表示设备执行成功。

### 4.2 领域对象

#### `Telemetry`

REST 的 `Telemetry` 与 MQTT 遥测消息使用完全相同的字段。服务端额外加入：

```json
{
  "received_at": 1752220800210,
  "record_id": "01JZK6WQVN13ZRY9DWE5YZQW5D"
}
```

`record_id` 为 ULID 字符串。REST 返回的 `sensors`、`quality`、`actuators` 和 `connectivity` 不得扁平化。

#### `DeviceStatus`

```json
{
  "device_id": "greenhouse_001_s3",
  "online": true,
  "last_seen_at": 1752220800210,
  "last_telemetry_at": 1752220800000,
  "connectivity": { "wifi": "connected", "mqtt": "connected", "rssi_dbm": -56 },
  "actuators": {
    "pump": { "desired": 0, "actual": 0 },
    "grow_light": { "desired": 60, "actual": 60 }
  },
  "positioning": {
    "pan_deg": 90,
    "tilt_deg": 5,
    "water_gun": { "active": false, "timed": false, "dynamic": false }
  }
}
```

#### `CommandResource`

```json
{
  "command_id": "c820003f-b6c4-4f6d-a3e3-2194c7c77989",
  "device_id": "greenhouse_001_s3",
  "state": "PUBLISHED",
  "source": "web_manual",
  "reason": "用户手动设置补光灯亮度",
  "command": { "operation": "set", "target": "grow_light", "value": 60 },
  "created_at": 1752220800123,
  "published_at": 1752220800150,
  "completed_at": null,
  "ack": null
}
```

`state` 只能为 `QUEUED`、`PUBLISHED`、`EXECUTED`、`REJECTED`、`EXPIRED`、`DELIVERY_FAILED`、`TIMED_OUT`。最终状态必须保留 MQTT ACK 的完整内容到 `ack`。

### 4.3 设备与遥测接口

- `GET /health`：无请求参数；返回 `{ "request_id": "...", "data": { "status": "ok", "version": "1.0" } }`；状态码为 200。
- `GET /devices`：参数为 `?online=true&limit=50&cursor=`；返回 `DeviceStatus[]`；状态码为 200。
- `GET /devices/{device_id}/capabilities`：无请求参数；返回 MQTT capabilities 对象；状态码为 200。
- `GET /devices/{device_id}/latest`：无请求参数；返回 `Telemetry`；状态码为 200。
- `GET /devices/{device_id}/status`：无请求参数；返回 `DeviceStatus`；状态码为 200。
- `GET /devices/{device_id}/telemetry`：参数为 `from`、`to`、`limit`、`cursor`，时间均为毫秒；返回 `Telemetry[]`；状态码为 200。
- `GET /devices/{device_id}/alarms`：参数为 `?state=open&limit=&cursor=`；返回 `Alarm[]`；状态码为 200。
- `GET /devices/{device_id}/commands`：参数为 `?state=&limit=&cursor=`；返回 `CommandResource[]`；状态码为 200。
- `GET /devices/{device_id}/commands/{command_id}`：无请求参数；返回 `CommandResource`；状态码为 200。

`GET /devices/{device_id}/telemetry` 的参数规则：`from`、`to` 可省略；缺省 `to` 为当前时间，缺省 `from` 为 24 小时前；`limit` 默认 100，最大 1000；按 `received_at` 升序返回。多设备展示必须使用 `GET /devices`，禁止继续使用默认 `device_id`。

### 4.4 下发命令接口

```http
POST /api/v1/devices/greenhouse_001_s3/commands
Authorization: Bearer <access-token>
Idempotency-Key: c820003f-b6c4-4f6d-a3e3-2194c7c77989
Content-Type: application/json
```

```json
{
  "source": "web_manual",
  "reason": "用户手动开启水泵",
  "command": { "operation": "set", "target": "pump", "value": 60 },
  "ttl_seconds": 30
}
```

成功时返回 `202` 和 `CommandResource`，初始状态只能是 `QUEUED` 或 `PUBLISHED`。目标设备离线时必须返回 `409 DEVICE_OFFLINE`，不得创建“成功但永远不会执行”的命令。目标不存在或能力不支持时必须返回 `422`。

批量智能托管使用同一路径，但每个执行器独立创建一个命令并分别返回状态：

```json
{
  "source": "web_automation",
  "reason": "自动灌溉与补光",
  "commands": [
    { "operation": "set", "target": "pump", "value": 60 },
    { "operation": "set", "target": "grow_light", "value": 50 }
  ],
  "ttl_seconds": 30
}
```

此批量格式只允许在 `POST /devices/{device_id}/commands/batch` 使用，返回 `202` 和 `CommandResource[]`。任一不支持项必须在发布前逐项标为 `REJECTED`，不影响其他合法命令；响应中不得省略失败项。

### 4.5 实时事件接口

```http
GET /api/v1/devices/{device_id}/events
Accept: text/event-stream
Authorization: Bearer <access-token>
```

服务端事件只允许以下类型：`telemetry`、`status`、`command`、`alarm`。`event.data` 必须为完整 JSON 领域对象；断线后客户端携带 `Last-Event-ID`，服务端从该 ID 后补发最多 1000 条事件。超出范围时发送 `event: resync`，客户端必须重新请求 `/latest`、`/status`、`/commands`。

### 4.6 AI、天气、病害、知识库和状态接口

这些接口同样属于唯一后端服务，并使用第 2.3 节的响应包装。

- `POST /devices/{device_id}/analyses`：请求 `{ "crop": "tomato", "include_weather": true, "include_history_hours": 24 }`；响应 `Analysis`。后端读取本机已保存的遥测，客户端不得提交伪造传感器值。
- `GET /weather/current?city={city}`：响应 `{ "city", "condition", "temperature_c", "humidity_pct", "wind_direction", "wind_level", "updated_at" }`。
- `GET /weather/forecast?city={city}&days=1..7`：响应同一单位的逐日预测数组。
- `POST /vision/disease`：`multipart/form-data`，文件字段固定为 `image`；响应 `DiseaseDetection`。
- `POST /devices/{device_id}/disease-photos`：`multipart/form-data`，文件字段固定为 `image`；响应 `DiseasePhoto`。
- `GET /devices/{device_id}/disease-photos` 与 `GET /devices/{device_id}/disease-photos/{photo_id}`：分别返回图片数组或单张 `DiseasePhoto`。
- `PUT /devices/{device_id}/disease-photos/{photo_id}/analysis` 与 `DELETE /devices/{device_id}/disease-photos/{photo_id}`：保存分析结果或删除图片。
- `POST /assistant/chat`：请求 `{ "question", "device_id", "image_id": null, "current_view" }`；响应 `{ "message", "references", "actions", "created_at" }`。
- `GET /knowledge-bases`：响应知识库数组。
- `POST /knowledge-bases`：请求 `{ "name", "description" }`；响应新知识库。
- `GET /knowledge-bases/{kb_id}/items`：响应知识条目数组。
- `POST /knowledge-bases/{kb_id}/items`：请求 `{ "title", "content" }`；响应新条目。
- `PATCH /knowledge-bases/{kb_id}` 与 `DELETE /knowledge-bases/{kb_id}`：更新或删除知识库。
- `PATCH /knowledge-bases/{kb_id}/items/{item_id}` 与 `DELETE /knowledge-bases/{kb_id}/items/{item_id}`：更新或删除知识条目。
- `GET /ui-state/{key}` 与 `PUT /ui-state/{key}`：仅保存当前已认证用户的前端偏好；请求/响应 `{ "value": {} }`。

`Analysis` 固定为：

```json
{
  "analysis_id": "01JZK6WQVN13ZRY9DWE5YZQW5D",
  "device_id": "greenhouse_001_s3",
  "crop": "tomato",
  "risk_level": "low",
  "risk_score": 18,
  "risk_status": "环境稳定",
  "risk_factors": [
    { "key": "humidity", "label": "湿度", "detail": "62.3% 在目标范围内", "state": "good" }
  ],
  "summary": "当前环境稳定。",
  "suggestions": ["保持当前通风策略。"],
  "proposed_commands": [],
  "basis": ["最近 24 小时遥测", "番茄规则库 v1"],
  "created_at": 1752220800123
}
```

`risk_level` 只能为 `low`、`medium`、`high`；`risk_score` 为 0 至 100 整数。AI 返回的 `proposed_commands` 不得自动下发，必须由用户确认后调用命令接口，或由明确启用的 `web_automation` 规则下发。

`Alarm` 固定为：

```json
{
  "alarm_id": "01JZK6WQVN13ZRY9DWE5YZQW5D",
  "device_id": "greenhouse_001_s3",
  "severity": "warning",
  "source": "sensor",
  "code": "HUMIDITY_HIGH",
  "title": "湿度过高",
  "detail": "当前湿度 88.1% 超过 85% 阈值。",
  "state": "open",
  "opened_at": 1752220800123,
  "acknowledged_at": null,
  "resolved_at": null
}
```

`severity` 只能为 `info`、`warning`、`critical`；`state` 只能为 `open`、`acknowledged`、`resolved`。`DiseaseDetection` 固定包含 `detection_id`、`photo_id`、`diagnosis`、`disease_name_zh`、`confidence`（0 至 1）、`affected_area_ratio`（0 至 1）、`detections`、`summary`、`explanation`、`suggestions`、`processed_at`。每个 `detections` 项固定为 `{ "label", "confidence", "bbox": { "x", "y", "width", "height" } }`，坐标均为原图像素。`DiseasePhoto` 固定包含 `photo_id`、`device_id`、`url`、`original_name`、`mime_type`、`size_bytes`、`created_at`、`analysis`；`analysis` 为 `DiseaseDetection` 或 `null`。

## 5. 统一领域数据和单位

- `temperature_c`：`number` 或 `null`，单位 `degC`，值域 -40 至 125；表示摄氏温度。
- `humidity_pct`：`number` 或 `null`，单位 `%RH`，值域 0 至 100；表示相对湿度。
- `pressure_kpa`：`number` 或 `null`，单位 `kPa`，值域 30 至 120；帕斯卡原始值必须除以 1000。
- `gas_resistance_ohm`：`number` 或 `null`，单位 `ohm`，值域大于等于 0；表示气体阻值。
- `illuminance_lux`：`number` 或 `null`，单位 `lux`，值域大于等于 0；表示光照强度，不是布尔补光状态。
- `co2_ppm`：`number` 或 `null`，单位 `ppm`，值域大于等于 0；表示二氧化碳浓度。
- `soil_moisture_pct`：`number` 或 `null`，单位 `%`，值域 0 至 100；表示标定后的体积含水率或统一百分比。
- `soil_ec_ms_cm`：`number` 或 `null`，单位 `mS/cm`，值域大于等于 0；表示电导率。
- `acceleration_g.*`：`number` 或 `null`，单位 `g`；表示三轴加速度。
- `gyroscope_dps.*`：`number` 或 `null`，单位 `deg/s`；表示三轴角速度。
- `magnetic_field_ut.*`：`number` 或 `null`，单位 `uT`；表示三轴磁场强度。
- `rssi_dbm`：`integer` 或 `null`，单位 `dBm`，值域 -127 至 0；表示 Wi-Fi 接收信号强度。
- binary actuator：`integer` 或 `null`，`0=off`、`1=on`；不使用 `true/false`，便于端侧 GPIO 对应。
- percent actuator：`integer` 或 `null`，值域 0 至 100；仅用于能力类型为 `percent` 的执行器。

禁止在 API 中使用 `temperature`、`humidity`、`pressure`、`light`、`co2`、`soil_ec` 等无单位字段。现有字段迁移固定为：`temperature -> temperature_c`、`humidity -> humidity_pct`、`pressure -> pressure_kpa`、`gas_resistance -> gas_resistance_ohm`、`light -> illuminance_lux`（传感器）或 `grow_light`（执行器）。

## 6. 统一错误码

- `VALIDATION_ERROR`：HTTP 422；字段、类型、时间、单位或值域不符合本标准。
- `INVALID_COMMAND`：HTTP 422；设备收到的命令公共字段、结构、类型、组合关系非法，或同一 `command_id` 被用于不同报文内容。
- `UNAUTHORIZED`：HTTP 401；缺失或无效访问令牌。
- `FORBIDDEN`：HTTP 403；用户无此设备或操作权限。
- `DEVICE_NOT_FOUND`：HTTP 404；`device_id` 不存在。
- `DEVICE_OFFLINE`：HTTP 409；设备当前离线，命令不发布。
- `CAPABILITY_UNSUPPORTED`：HTTP 422；设备未声明支持目标传感器或执行器。
- `ACTUATOR_INTERLOCK`：HTTP 409；安全互锁拒绝命令。
- `COMMAND_EXPIRED`：HTTP 409；MQTT 命令到达时已超过 `expires_at`。
- `COMMAND_TIMED_OUT`：HTTP 504；后端在时限内未收到最终 ACK。
- `COMMAND_QUEUE_FULL`：HTTP 503；设备命令队列已满。
- `DEVICE_TIME_UNSYNCED`：HTTP 409；设备时间未同步，不能启动定时喷水。
- `TIMED_SPRAY_EXPIRED`：HTTP 409；定时喷水截止时间已经到达。
- `STALE_TARGET`：HTTP 409；动态会话序号未递增。
- `TARGET_OUT_OF_RANGE`：HTTP 422；目标超出当前机械或临时标定范围。
- `MQTT_UNAVAILABLE`：HTTP 503；后端无法连接 Broker。
- `SENSOR_INVALID`：HTTP 422；传感器读数无效。
- `INTERNAL_ERROR`：HTTP 500；未分类服务端错误。

设备 ACK 可使用：`INVALID_COMMAND`、`CAPABILITY_UNSUPPORTED`、`ACTUATOR_INTERLOCK`、`COMMAND_EXPIRED`、`COMMAND_QUEUE_FULL`、`DEVICE_TIME_UNSYNCED`、`TIMED_SPRAY_EXPIRED`、`STALE_TARGET`、`TARGET_OUT_OF_RANGE`、`SENSOR_INVALID`、`INTERNAL_ERROR`。后端将它们映射为最终 `CommandResource.state=REJECTED`。

## 7. 数据库与保留标准

- 数据库逻辑实体固定为 `devices`、`device_capabilities`、`telemetry`、`device_status`、`commands`、`command_acks`、`analyses`、`alarms`、`knowledge_bases`、`knowledge_items`、`disease_photos`。
- `telemetry` 必须保存完整 JSON 快照和可检索的规范字段列；不得仅保存温湿度后丢弃其他字段。
- `commands` 与 `command_acks` 通过 `command_id` 一对一关联；`commands` 必须保存发布前、发布后和最终状态时间。
- `(device_id, message_id)` 和 `command_id` 必须有唯一索引或幂等约束。
- 生产数据库使用 PostgreSQL；本机演示可用 SQLite。SQLite 路径必须由 `DATABASE_URL` 明确指定到应用目录，禁止使用依赖当前工作目录的相对路径。
- 禁止提交 `.db`、真实 `.env`、Wi-Fi 密码、MQTT 密码、AI Key、天气 Key、客户端证书私钥和上传图片到 Git。

## 8. 配置名称标准

后端环境变量固定使用：

```dotenv
API_HOST=0.0.0.0
API_PORT=8000
DATABASE_URL=sqlite:///./data/smartagribrain.db
MQTT_URI=mqtts://broker.example.com:8883
MQTT_USERNAME=sab_api
MQTT_PASSWORD=change-me
MQTT_CA_CERT_PATH=./certs/ca.pem
MQTT_TOPIC_PREFIX=smartagribrain/v1
COMMAND_ACK_TIMEOUT_SECONDS=30
CORS_ORIGINS=https://dashboard.example.com,http://localhost:5173
```

前端环境变量固定使用：

```dotenv
VITE_API_BASE_URL=https://api.example.com
```

当前 Arduino/PlatformIO ESP32 的 Wi-Fi、MQTT 主机、用户和密码由被 Git 忽略的本机 `include/config.h` 提供，CA 由同样被忽略的 `include/emqx_ca_cert.h` 提供；设备 ID、主题和控制常量位于 `include/iot_contract.h`。仓库不再维护可能与真实配置漂移的 example 头文件，新环境统一通过 `scripts/setup/configure-emqx.ps1` 生成这两个本机文件。正式部署应迁移到 NVS 或受保护的构建注入方式。每个实际设备都必须发布第 3.3 节能力消息。

## 9. 联调验收样例

以下四项全部通过才算 v1 接通：

1. ESP32 发布第 3.4 节遥测后，`GET /api/v1/devices/greenhouse_001_s3/latest` 返回同一 `message_id`、相同 `sensors` 嵌套结构和服务端 `received_at`。
2. 前端用 `POST /commands` 创建 `pump=60` 命令后先收到 `202/PUBLISHED`；设备在 5 秒内发布匹配 `command_id` 的 `executed` ACK；`GET /commands/{command_id}` 最终为 `EXECUTED`，且 `actual_value` 是设备实际应用值。
3. 对未声明支持的 `fan` 发送命令时，服务端返回 `422 CAPABILITY_UNSUPPORTED`，不向 MQTT 主题发布消息。
4. 设备断网时，status retained 消息为 `online=false`；REST 命令接口返回 `409 DEVICE_OFFLINE`；前端不得更新执行器实际状态。
