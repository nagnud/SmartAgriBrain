# ESP32-C5 智慧农业 Web 前端

这是智慧农业电脑端 Web 管理平台，面向大棚环境监测、作物健康识别、知识库管理、AI 专家问答和远程设备控制等日常使用场景。

## 功能

- 首页总览：设备 ID、Wi-Fi / MQTT 状态、天气、温度、湿度、光照、CO2、土壤湿度、土壤 EC、空气质量、风险等级。
- 实时监测：农业核心环境指标、目标区间状态、指标详情抽屉和单变量趋势曲线。
- 历史曲线：温度、湿度、光照、CO2、土壤湿度、土壤 EC、空气质量趋势图。
- 病害识别：图片上传、检测框、YOLO 风格类别、置信度、解释和建议。
- AI 农事建议：风险等级、分析依据、建议列表和建议命令。
- 专家问答：文字输入、图片附件、浏览器语音识别转文字和聊天流程。
- 设备控制：风机、水泵、补光灯、卷帘、报警器远程控制。
- 知识库管理：知识库列表、知识条目列表、新建、编辑、删除、RAG 引用片段展示。
- 报警记录：通信、环境、病害和 AI 风险相关报警。

## 运行

建议使用 Node.js 20.19 或更高版本。

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

如果系统 Node 版本过低，请使用 `scripts/web/start-web.bat` 运行，或安装 Node.js 20.19+。

## 接口切换

默认使用本地示例数据。后端完成后复制 `.env.example` 为 `.env`，把 `VITE_USE_MOCK` 改为 `false`，并设置后端地址：

```text
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK=false
VITE_USE_MOCK_ASSISTANT=false
```

如果只想让 AI 助手和 AI 农事建议真实接入、其他遥测/设备/视觉功能继续使用 Mock，可以保持：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK=true
VITE_USE_MOCK_ASSISTANT=false
VITE_USE_MOCK_AI_ADVICE=false
```

如果只想让专家问答接入后端、AI 农事建议仍使用前端 Mock，把 `VITE_USE_MOCK_AI_ADVICE` 改回 `true` 即可。

后端 AI 农事建议和专家问答使用 `backend_api/.env` 中的 DeepSeek 配置。这个文件会随项目一起推送，别人拿到代码后运行后端脚本即可使用同一套配置：

```env
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=90
```

前端的 AI 农事建议接口为 `POST /api/ai/analyze`；后端也兼容 `POST /api/v1/farm/ai/analyze`。

前端预留接口集中在 `src/services/api.ts`：

- `GET /api/device/latest`
- `GET /api/device/history`
- `GET /api/device/status`
- `GET /api/device/alarms`
- `GET /api/weather/current`
- `POST /api/ai/analyze`
- `POST /api/v1/assistant/chat`
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

控制命令格式：

```json
{
  "device_id": "sensairshuttle_001",
  "command": "curtain_open",
  "value": 1,
  "reason": "打开卷帘，提高自然光照"
}
```

病害识别真实接口建议使用 `multipart/form-data` 上传图片字段 `image`，返回 `detections`、`summary`、`explanation`、`suggestions` 和 `processed_at`。
