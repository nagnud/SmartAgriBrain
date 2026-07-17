# ESP32-C5 智慧农业 Web 前端

这是由 Web、FastAPI、本机 Mosquitto、ESP32-C5 和 ESP32-S3 组成的智慧农业系统。S3 负责传感器与执行器，C5 负责屏幕、精简 AI 对话和后续语音；两块板不直接通信，所有数据均由后端中继。

固定链路为：`Web ⇄ FastAPI ⇄ Mosquitto ⇄ C5/S3`。Web 控制使用 REST，实时状态、命令回执和共享现场会话使用 SSE；板端使用 QoS 1 MQTT。

## 功能

- 首页总览：设备 ID、Wi-Fi / MQTT 状态、天气、温度、湿度、光照、CO2、土壤湿度、土壤 EC、空气质量、风险等级。
- 实时监测：农业核心环境指标、目标区间状态、指标详情抽屉和单变量趋势曲线。
- 历史曲线：温度、湿度、光照、CO2、土壤湿度、土壤 EC、空气质量趋势图。
- 病害识别：图片上传、检测框、置信度、解释和建议；可按识别出的作物与疑似病害查询已启用的官方农业来源并展示引用。
- AI 农事建议：风险等级、分析依据、建议列表和建议命令。
- 专家问答：文字输入、图片附件、浏览器语音识别转文字和聊天流程。
- 设备控制：风机、水泵、补光灯、卷帘、报警器远程控制。
- 知识库管理：知识库列表、知识条目列表、新建、编辑、删除、RAG 引用片段展示。
- 在线农业知识源：按需查询 FAO AGROVOC、EPPO 和全国农技推广网，展示联网状态与官方引用，不保存外部全文。
- 报警记录：通信、环境、病害和 AI 风险相关报警。

## 运行

建议使用已验证的 Node.js 22 LTS。

如果本机 Node 版本过低，可以直接双击：

```text
scripts/web/start-web.bat
```

它会优先使用 Codex 内置的 Node 启动。

也可以手动运行：

```bash
npm install
npm run dev
```

浏览器访问 Vite 输出的本地地址，通常是：

```text
http://localhost:5173
```

## 构建

```bash
npm run build
```

如果系统 Node 版本过低，请使用 `scripts/web/start-web.bat` 运行，或安装 Node.js 22 LTS。

完整环境可执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/check-environment.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start-full-stack.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/build-all.ps1
```

## 接口切换

默认连接本地后端并显示已持久化的真实遥测数据。复制 `.env.example` 为 `.env` 后，设置后端地址：

```text
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK=false
VITE_USE_MOCK_ASSISTANT=false
VITE_USE_MOCK_KNOWLEDGE=false
```

如需演示模式，可显式把 `VITE_USE_MOCK` 设为 `true`。此模式会生成模拟遥测，不应用于验证真实历史数据：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK=true
VITE_USE_MOCK_ASSISTANT=false
VITE_USE_MOCK_AI_ADVICE=false
VITE_USE_MOCK_KNOWLEDGE=false
```

如果只想让专家问答接入后端、AI 农事建议仍使用前端 Mock，把 `VITE_USE_MOCK_AI_ADVICE` 改回 `true` 即可。

后端 AI 农事建议和专家问答使用 `backend_api/.env` 中的 DeepSeek 配置。`.env` 是本地密钥文件，不要提交；别人拿到代码后可以复制 `backend_api/.env.example` 并填入自己的 Key：

```env
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=your-deepseek-api-key
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=90
```

在线农业检索由后端代为执行，DeepSeek 只会请求 `search_agriculture` 工具，不会持有网站账号或直接访问任意网址。默认启用 AGROVOC 和全国农技推广网；EPPO 需要部署者申请 API Key 后再启用：

```env
AGRI_ONLINE_ENABLED=true
AGRI_SOURCE_TIMEOUT_SECONDS=6
AGRI_TOTAL_TIMEOUT_SECONDS=12
AGRI_CACHE_SECONDS=1800
AGRI_MAX_RESULTS=5
EPPO_API_KEY=your-eppo-api-key
```

外部资料只进入最多 200 个查询的进程内缓存，默认 30 分钟过期，不写入 SQLite。AI 生成的设备动作仍然只是待确认建议，只有用户在 Web 中确认后才进入原有命令队列。

知识库默认使用后端本地 SQLite 数据库，启动后会自动创建表并写入初始知识库：

```env
DATABASE_URL=sqlite:///./smartagribrain.db
```

生成的数据库文件位于 `backend_api/smartagribrain.db`，不会作为主要数据提交。未来需要多人线上部署时，可以把 `DATABASE_URL` 改成 PostgreSQL，例如：

```env
DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname
```

前端的 AI 农事建议接口为 `POST /api/ai/analyze`；后端也兼容 `POST /api/v1/farm/ai/analyze`。

前端预留接口集中在 `src/services/api.ts`：

- `GET /api/v1/sites/{site_id}/state`
- `GET /api/v1/sites/{site_id}/events`
- `POST /api/v1/sites/{site_id}/commands`
- `POST /api/v1/sites/{site_id}/assistant/messages`
- `GET /api/v1/sites/{site_id}/assistant/conversation`
- `POST /api/v1/sites/{site_id}/assistant/actions/{action_id}/decision`

- `POST /api/device/telemetry`
- `GET /api/device/latest`
- `GET /api/device/history`
- `GET /api/device/status`
- `GET /api/device/health`
- `GET /api/device/alarms`
- `POST /api/device/alarms/{alarm_id}/ack`
- `GET /api/device/alarm-settings`
- `PUT /api/device/alarm-settings`
- `GET /api/weather/current`
- `POST /api/ai/analyze`
- `POST /api/v1/assistant/chat`
- `GET /api/v1/agri/sources`
- `PATCH /api/v1/agri/sources/{source_id}`
- `POST /api/v1/agri/sources/{source_id}/test`
- `POST /api/device/command`
- `POST /api/vision/disease`
- `GET /api/v1/kb/list`
- `GET /api/v1/kb/items?kbId=`
- `POST /api/v1/kb/create`
- `POST /api/v1/kb/update`
- `POST /api/v1/kb/delete`
- `POST /api/v1/kb/add_text`
- `POST /api/v1/kb/item/update`
- `POST /api/v1/kb/item/delete`
- `POST /api/v1/kb/analyze`

## 数据格式

端侧上传数据建议统一为：

```json
{
  "device_id": "sensairshuttle_001",
  "message_id": "reading-001",
  "sequence": 1,
  "timestamp": 1710000000,
  "sensors": {
    "temperature": 26.5,
    "humidity": 62.3,
    "pressure": 101.2,
    "gas_resistance": 15800,
    "light": 18000,
    "co2": 650,
    "soil_moisture": 58.5,
    "soil_ec": 1.8
  },
  "status": {
    "wifi": "connected",
    "mqtt": "connected",
    "fan": 0,
    "pump": 0,
    "light": 0,
    "alarm": 0,
    "curtain": 1
  }
}
```

`message_id` 和 `sequence` 为可选字段。设备提供 `message_id` 时，后端会自动忽略重复上报，避免历史曲线和报警重复记录。

报警阈值使用 Web 页面中设置的目标范围。指标连续 3 次低于下限或高于上限后生成报警，连续 3 次回到范围内后自动恢复。

控制命令格式：

```json
{
  "device_id": "sensairshuttle_001",
  "command": "curtain_open",
  "value": 1,
  "reason": "打开卷帘，提高自然光照"
}
```

后端会把控制命令放入待执行队列，不会在设备回执前伪造执行成功。设备端或设备网关使用：

- `GET /api/device/commands/next?device_id=sensairshuttle_001` 拉取下一条指令。
- `POST /api/device/commands/{command_id}/ack` 回传 `success`、`message` 和可选的最新 `status`。

当前支持 `fan`、`pump`、`light`、`alarm` 的开关命令，以及 `curtain_open`、`curtain_close`。设备最新状态仍以随后上报的遥测数据为准。

## 可选 MQTT 通信

HTTP 仍是默认设备通信方式。需要 MQTT 时，在 `backend_api/.env` 中配置服务器并显式启用：

```env
MQTT_ENABLED=true
DEVICE_COMMAND_TRANSPORT=mqtt
MQTT_HOST=your-mqtt-host
MQTT_PORT=1883
MQTT_TOPIC_PREFIX=smartagribrain/v1
```

MQTT 未启用或连接失败时不会影响 Web 后端启动。不要把真实账号和密码写入 `.env.example` 或提交到仓库。

病害识别真实接口建议使用 `multipart/form-data` 上传图片字段 `image`，返回 `detections`、`summary`、`explanation`、`suggestions` 和 `processed_at`。
