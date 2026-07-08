# ESP32-C5 智慧农业 Web 前端

这是物联网设计竞赛乐鑫赛道的电脑端 Web 展示平台，重点展示 ESP32-C5 / ESP-SensairShuttle 的采集、联网、AI 建议和远程控制闭环。

## 功能

- 首页总览：设备 ID、Wi-Fi / MQTT 状态、核心环境指标、执行设备状态。
- 实时监测：BME690、BMI270、BMM350 的环境和三轴数据。
- 历史曲线：温度、湿度、气压、气体阻值趋势图。
- AI 农事建议：风险等级、建议列表、建议命令。
- 设备控制：风机、水泵、补光灯、报警器远程控制。
- 报警记录：通信、环境和空气质量相关报警。

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

## GitHub 推送

推送脚本已经放在 `pro` 文件夹内部：

```text
scripts/git/push-frontend.bat
```

网络稳定、GitHub 登录正常时，双击这个脚本即可把当前 `pro` 工程导入到仓库的 `frontend_dashboard/` 目录并推送到 `feature/frontend` 分支。

## 接口切换

默认使用 Mock 数据。后端完成后复制 `.env.example` 为 `.env`，把 `VITE_USE_MOCK` 改为 `false`，并设置后端地址：

```text
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK=false
```

前端预留接口集中在 `src/services/api.ts`：

- `GET /api/device/latest`
- `GET /api/device/history`
- `GET /api/device/status`
- `POST /api/ai/analyze`
- `POST /api/device/command`

## 数据格式

端侧上传数据以新比赛负责文件为准：

```json
{
  "device_id": "sensairshuttle_001",
  "timestamp": 1710000000,
  "sensors": {
    "temperature": 26.5,
    "humidity": 62.3,
    "pressure": 101.2,
    "gas_resistance": 15800,
    "acc_x": 0.01,
    "acc_y": -0.02,
    "acc_z": 0.98,
    "gyro_x": 0.1,
    "gyro_y": 0.0,
    "gyro_z": -0.1,
    "mag_x": 12.3,
    "mag_y": 8.6,
    "mag_z": -35.1
  },
  "status": {
    "wifi": "connected",
    "mqtt": "connected",
    "fan": 0,
    "pump": 0,
    "light": 0
  }
}
```

控制命令格式：

```json
{
  "device_id": "sensairshuttle_001",
  "command": "fan_on",
  "value": 1,
  "reason": "棚内温度偏高，建议开启通风"
}
```
