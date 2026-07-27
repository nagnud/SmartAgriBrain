# SmartAgriBrain

最后同步日期：2026-07-23。

SmartAgriBrain 是一个由现场采集执行节点、云端服务、Web 管理端和语音显示终端组成的智慧农业项目。当前仓库分支重点维护统一契约、协同文档和普通 ESP32 固件。

## 当前目录

- `docs/`：架构、MQTT/REST 契约、ESP32 与后端通信要求、跨团队问题和 Word 设计说明书。
- `esp32/`：普通 ESP32 的 PlatformIO/Arduino 工程，负责传感器采集、MQTT 上报以及水泵、补光灯和二维水枪云台控制。
- `前端/`：完整的 Web 管理端、FastAPI 集成服务、MQTT 脚本和联调说明，也是后续前端开发的唯一源码目录；其开发约束以目录内 `AGENTS.md` 为准。
- `frontend_dashboard/`：历史推送映射或本地依赖残留，不是当前开发源，不得反向覆盖 `前端/`。
- `esp32c5_voice_display/`：约定的 ESP32-C5 语音与屏幕工程目录；当前工作区尚未包含该目录。

## 设备职责

- 普通 ESP32：采集土壤湿度、光照、温度和 CO2；通过 MQTT QoS 1 上报；执行 GPIO26 水泵、GPIO14 补光灯、GPIO27 水平舵机和 GPIO13 俯仰舵机控制。
- ESP32-C5：负责屏幕、录音、播放和云端大模型语音交互，不直接采集农业传感器，也不直接驱动水泵或云台。
- `smartagribrain-api`：统一接入 MQTT、保存遥测与命令状态、向 Web/C5 提供 REST 与 SSE，并代理云端模型能力。

## 通信与 MQTT

### 1. 实际通信路径

浏览器前端不保存 MQTT 账号，也不直接连接 EMQX。一次真实水枪控制的路径固定如下：

```text
浏览器 Vue Web
  -> HTTP REST
smartagribrain-api（FastAPI）
  -> MQTT QoS 1 / TLS
EMQX 云端 Broker
  -> MQTT QoS 1 / TLS
普通 ESP32
  -> command_ack / telemetry / status / capabilities
EMQX 云端 Broker
  -> MQTT QoS 1 / TLS
smartagribrain-api
  -> REST / SSE
浏览器 Vue Web
```

后端是唯一的 MQTT 命令发布者和设备消息写入者。浏览器只能调用后端 REST/SSE；ESP32-C5 的语音和屏幕业务也通过后端，不接管普通 ESP32 的水泵或云台控制。

### 2. 当前真实运行模式

本机当前运行配置已经启用真实模式：

```text
MQTT_ENABLED=true
DEVICE_COMMAND_TRANSPORT=mqtt
```

这意味着前端确认水枪操作后，后端会将真实命令写入队列并发布到 EMQX；ESP32 收到命令后可能驱动 GPIO26 水泵和 GPIO27/GPIO13 云台。启动服务本身不会自动发送控制命令。

模拟控制开关和 `simulation_only` 字段已彻底移除。升级 ESP32 固件后，不得再使用旧版后端或旧脚本发送带有 `simulation_only=true` 的命令；该字段不再具有阻止硬件输出的语义，任何通过其余校验的有效控制命令都会走真实 GPIO 执行路径。

当前 EMQX 只允许 TLS 地址 `mqtts://<域名>:8883`，后端使用 QoS 1、稳定客户端 ID 和持久会话。项目不启动、不依赖、也不允许回退到本地 Mosquitto。账号、密码、CA 证书和 Wi-Fi 信息只保存在被 Git 忽略的本机配置中。

本次启动已确认 FastAPI 进程持有一个到 EMQX TLS `8883` 的已建立连接。连接建立只证明后端可以到达 EMQX，不代表 ESP32 已收到某一条命令；是否执行必须以 `command_ack` 为准。

### 3. 普通 ESP32 的设备标识和 Topic

普通 ESP32 当前协议设备 ID 为 `greenhouse_001_s3`，站点 ID 为 `greenhouse_001`，固定 Topic 前缀为 `smartagribrain/v1`。设备 ID 中的 `_s3` 是历史协议标识；当前 PlatformIO 构建目标仍为普通 ESP32 `esp32dev`。

当前普通 ESP32 使用以下 5 个业务 Topic，全部使用 QoS 1：

- **控制命令 `command`**

  完整 Topic：`smartagribrain/v1/devices/greenhouse_001_s3/command`。

  方向为后端发布、ESP32 订阅。内容是命令信封、目标执行器、控制值、水枪位置和喷水参数。`retain=false`，避免 ESP32 重连后误执行旧命令。该 Topic 不按固定周期发布；后端命令线程每 50 ms 检查一次队列，但只有出现新的待发送命令时才发布。发布失败的命令只在有效期内重试。

- **命令结果 `command_ack`**

  完整 Topic：`smartagribrain/v1/devices/greenhouse_001_s3/command_ack`。

  方向为 ESP32 发布、后端订阅。内容包括原 `command_id`、`executed` 或 `rejected`、实际应用值和错误码。`retain=false`。该 Topic 不按固定周期发布；每条有效命令执行完成或被拒绝时发布一次。普通灯光命令通常立即返回，水枪命令在云台约 800 ms 稳定等待结束后返回，最终 ACK 应在命令到达后 5 秒内产生。若 QoS 1 导致同一命令重复投递，ESP32 会重发缓存 ACK，但不会重复执行硬件动作。

- **设备遥测 `telemetry`**

  完整 Topic：`smartagribrain/v1/devices/greenhouse_001_s3/telemetry`。

  方向为 ESP32 发布、后端订阅。内容包括土壤湿度、光照、温度、CO2、补光灯 PWM 值、云台角度、水枪状态和 RSSI。`retain=false`。当前由 `SEND_INTERVAL_MS=5000` 控制，每 5 秒尝试上报一次。MQTT 断线时本次上报会跳过，不缓存，也不会在重连后批量补发历史快照。

- **在线状态 `status`**

  完整 Topic：`smartagribrain/v1/devices/greenhouse_001_s3/status`。

  方向为 ESP32 或 EMQX 发布、后端订阅。内容是 `online` 状态及连接或异常断线原因。`retain=true`。它不是周期上报：ESP32 每次 MQTT 首次连接或重连成功时发布一次 `online=true`；设备异常掉线时，由 EMQX 按 LWT 遗嘱立即保留 `online=false`。MQTT 协议每 30 秒进行 keepalive 检测，但 keepalive 不是该 Topic 的业务消息。

- **设备能力 `capabilities`**

  完整 Topic：`smartagribrain/v1/devices/greenhouse_001_s3/capabilities`。

  方向为 ESP32 发布、后端订阅。内容是固件版本、传感器类型、补光灯范围、水枪功能和当前标定状态。`retain=true`。它不是周期上报：ESP32 每次 MQTT 首次连接或重连成功时发布一次。静态能力不会塞进每 5 秒的遥测，从而减少重复流量。

后端订阅通配范围为：

```text
smartagribrain/v1/devices/+/telemetry
smartagribrain/v1/devices/+/status
smartagribrain/v1/devices/+/capabilities
smartagribrain/v1/devices/+/command_ack
```

这些 Topic 没有可以直接删除的重复项。`command` 与 `command_ack` 分别表示“要求执行”和“最终执行结果”；`telemetry` 表示周期状态快照；`status` 负责异常断线时仍可由 Broker 发布的在线状态；`capabilities` 表示设备支持什么功能。`command_ack` 的实际应用值可能与下一条 `telemetry` 中的执行器状态相同，但前者用于确认某个 `command_id`，后者用于恢复设备当前全量状态，两者语义不同。把它们合并会破坏命令确认、LWT、retain 或消息频率，因此当前 5 个 Topic 均保留。

裸 ESP32 只上电、后端没有下发控制命令时，实时消息流中持续出现的只有 `telemetry`，这是当前设计的正常结果。`status` 和 `capabilities` 只在 MQTT 连接或重连时各发布一次，并作为 retained 消息保存在 EMQX；`command` 由后端按需发布；`command_ack` 只有设备处理命令后才发布。检查全部设备 Topic 时应订阅：

```text
smartagribrain/v1/devices/greenhouse_001_s3/#
```

设备每次连接后，串口应至少出现一次 `type=capabilities`、一次 `type=status`，并分别收到 PUBACK。如果从设备复位开始就没有这些日志，则不是频率问题，应继续检查 MQTT 连接事件、发布结果和 EMQX ACL。

### 4. 后端向 ESP32 下发的命令格式

Topic 中的 `/v1/devices/greenhouse_001_s3` 已经确定协议版本和目标设备，因此 JSON 不再重复 `schema_version`、`device_id` 和 `site_id`。来源、原因和创建时间由后端数据库保存，不再发送给 ESP32。精简命令只保留 `command_id`、`expires_at` 和 `command`；默认有效期为 30 秒，ESP32 拒绝已过期或超过未来 300 秒的命令。

以下是一个真实的定时水枪命令结构。尖括号字段由后端在发送瞬间填入，不能直接作为 JSON 原样发布：

```json
{
  "command_id": "42",
  "expires_at": "<当前Unix毫秒加30000毫秒>",
  "command": {
    "operation": "target_position",
    "target": "position",
    "value": 1,
    "position": {
      "ground_range_mm": 850.0,
      "bearing_deg": 0.0
    },
    "water_gun": {
      "mode": "static",
      "spray_enabled": true,
      "pump_control_percent": 50.0,
      "sequence": 1,
      "spray_schedule": "timed",
      "spray_duration_seconds": 10,
      "spray_ends_at": "<当前Unix毫秒加10000毫秒>"
    }
  }
}
```

只有 `grow_light` 使用 `operation="set"` 的原子命令。GPIO26 水泵和 GPIO27/GPIO13 云台是水枪内部部件；水枪必须使用 `operation="target_position"`，同时携带位置和水路参数，避免把云台移动和水泵开关拆成彼此失配的两条命令。

动态水枪使用 `mode="dynamic"`、非空 `session_id` 和严格递增的 `sequence`。该序号由后端为 Web 目标更新和每秒 heartbeat 统一生成，浏览器不自行递增。Web 串行发送动态目标并只保留请求期间的最新位置；ESP32 对相同目标保活只刷新序号和 3 秒安全超时，不重复写舵机 PWM。动态命令只能采用 `spray_schedule="continuous"`，后端保活中断超过 3 秒时 ESP32 会停泵。

### 5. ESP32 命令校验和执行确认

ESP32 仅在下列条件都满足时才执行命令：消息来自本设备精确 `command` Topic、本地 SNTP 时间有效、命令未过期且不超过未来 300 秒、参数在范围内、命令 ID 未重复。

水枪执行前会先停泵，再移动云台，云台稳定后才允许开启水泵。SG90 没有角度反馈，水泵没有流量反馈，因此设备 ACK 的 `executed` 仅代表 GPIO 输出和状态机已应用，不代表实际水流或角度已经被传感器验证。

ESP32 每个命令都应在 5 秒内向下列 Topic 返回最终 ACK：

```text
smartagribrain/v1/devices/greenhouse_001_s3/command_ack
```

ACK 的 `state` 只能是 `executed` 或 `rejected`。前端只有在后端收到并处理 `executed` ACK 后，才能把真实设备操作视为成功；MQTT 发布成功或后端命令进入 `queued` 状态都不等于硬件已执行。

### 6. 如何判断当前是否存在真实下发

后端连接到 EMQX 后即使没有控制命令，也会发送 MQTT 协议 keepalive。这不是业务控制数据。要确认当前有没有真实下发，应同时检查命令队列和 ACK：

- 后端命令记录为 `queued` 或 `dispatched`：表示命令正在等待或已尝试发布。
- EMQX 发布成功：表示 Broker 已接受 QoS 1 发布，仍不能证明 ESP32 已执行。
- 收到 `command_ack` 且 `state=executed`：表示 ESP32 已接受并应用控制输出。
- 收到 `command_ack` 且 `state=rejected`，或命令标记为 `expired`、`failed`：表示不能把该操作视为成功。

本次服务启动时没有待发送的普通 ESP32 命令，因此后端仅保持与 EMQX 的真实 TLS 连接，没有自动向 `.../command` 发布控制 JSON。前端产生并确认新的真实控制请求后，才会出现下发。

### 7. C5 相关 MQTT 输出

普通 ESP32 与 C5 使用不同业务 Topic。后端在收到设备遥测、状态或能力变化后，会向 C5 页面状态 Topic 发布保留消息：

```text
smartagribrain/v1/devices/{C5设备ID}/view_state
```

后端处理 C5 语音请求后，会向以下 Topic 发布非保留响应：

```text
smartagribrain/v1/devices/{C5设备ID}/assistant/response
```

当前工作区尚未包含 C5 源码，因此只能确认后端发布逻辑和 Topic 格式，不能宣称 C5 实体已订阅或显示这些消息。

## ESP32 当前状态

ESP32 源码已经完成以下功能：

- 使用 ESP-IDF MQTT 客户端建立 MQTT 3.1.1 TLS 持久会话。
- `command`、`command_ack`、`telemetry`、`status`、`capabilities` 和 LWT 全部使用 QoS 1。
- 只允许 `grow_light` 原子命令；水泵和两个舵机只能作为水枪复合命令的一部分统一控制。
- 支持 `target_position` 水枪复合命令、静态/动态模式、定时停止和 3 秒动态安全超时。
- 使用 `command_id`、内容指纹和 ACK 缓存处理 QoS 1 重复投递。
- 水枪独占 GPIO26、GPIO27 和 GPIO13，并通过统一安全状态机驱动。
- PlatformIO `esp32dev` 环境已经通过源码构建验证。

源码构建成功不代表真机、Broker、后端和前端已经端到端验收。临时云台映射、水泵 40% 最小启动值和距离功率算法均未实测，必须按 `UN_CALIBRATED_PLACEHOLDER` 处理。

当前本机前端/FastAPI 已启用真实水枪模式，MQTT 仅允许连接外部 EMQX。EMQX 地址、端口、TLS、CA 和分端账号均位于被忽略的本地配置中；真实下发结果仍必须通过设备 `command_ack` 验证。

## 启动项目

本项目当前的可运行入口是 `前端/`：Vue Web 位于 `前端/src/`，FastAPI 位于 `前端/backend_api/`。不要从历史 `frontend_dashboard/` 或 `backend_server/` 启动服务。

### 1. 前置条件

- Windows PowerShell。
- Node.js `20.19` 或更高版本。
- Python `3.10` 或更高版本。建议使用已安装的 Python 3.11；后端脚本会创建独立虚拟环境，不会污染系统 Python。

在仓库根目录执行以下命令确认运行环境：

```powershell
Set-Location E:\vscode\esp32\SmartAgriBrain\前端
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev\check-environment.ps1
```

该检查中 Node、npm 和后端 Python 是必需项。EMQX、普通 ESP32、PlatformIO 和 C5 是设备联调所需的可选项。

### 2. 数据库不需要单独启动

当前开发环境使用 SQLite，不使用 MySQL、PostgreSQL 或独立数据库服务。首次启动 FastAPI 时会自动创建并初始化数据库文件：

```text
前端/backend_api/smartagribrain.db
```

数据库路径由 `backend_api/database.py` 按后端目录固定，不能因为从不同 PowerShell 目录启动而生成第二份默认数据库。需要清空开发数据时先停止后端，再明确删除这个文件；不要删除上传文件、截图或本机 MQTT 配置。

如需改用其他数据库，只能通过本机 `前端/backend_api/.env` 的 `DATABASE_URL` 配置；当前默认 SQLite 已可直接运行。

### 3. 首次安装依赖

在仓库根目录打开 PowerShell 后执行：

```powershell
Set-Location E:\vscode\esp32\SmartAgriBrain\前端
npm install
```

后端依赖无需手动安装。首次运行后端启动脚本时，它会创建 `backend_api/.venv` 并安装 `backend_api/requirements.txt`；后续仅在依赖清单的 SHA-256 发生变化时重装，普通启动不会重复运行整份 `pip install`。需要单独预装时可执行：

```powershell
backend_api\.venv\Scripts\python.exe -m pip install -r backend_api\requirements.txt
```

如果 `backend_api/.venv` 尚未存在，请先运行下一节的后端启动命令，让脚本自动创建。

### 4. 分别启动后端与前端

推荐开发时使用两个 PowerShell 窗口，这样日志最清楚，也可以用 `Ctrl+C` 分别停止。

这两个命令都是前台常驻服务：执行后该 PowerShell 会持续显示 Uvicorn 或 Vite 日志，直到按 `Ctrl+C` 才会返回提示符。这是正常行为，不是终端卡死；需要继续在同一窗口输入命令时，请使用下一节的后台一键启动方式。

第一个窗口启动 FastAPI：

```powershell
Set-Location E:\vscode\esp32\SmartAgriBrain\前端
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\backend\start-backend.ps1
```

后端默认地址是 `http://127.0.0.1:8000`。启动后可打开：

- API 健康检查：`http://127.0.0.1:8000/api/v1/health`
- OpenAPI 文档：`http://127.0.0.1:8000/docs`

第二个窗口启动 Vue Web：

```powershell
Set-Location E:\vscode\esp32\SmartAgriBrain\前端
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\web\start-web.ps1
```

浏览器打开 `http://127.0.0.1:5173`。前端会通过 FastAPI 接口访问数据；浏览器不直接连接 EMQX，也不保存 MQTT 账号或密码。

### 5. 一次启动前后端

已安装依赖后，推荐用受管后台方式同时启动两个服务。命令会等待后端健康检查和 Web 首页成功响应后才返回，因此返回 PowerShell 提示符就表示两个服务已经可用：

```powershell
Set-Location E:\vscode\esp32\SmartAgriBrain\前端
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev\start-full-stack.ps1
```

也可以双击 `前端\一键启动.bat`。该入口最终调用同一个受管启动脚本，不会再创建另一套无法统一关闭的后台进程。

后台启动会关闭 Uvicorn 自动重载，避免重载器替换 PID 后遗留持有摄像头的 Python 进程。启动器 PID 和实际监听 PID 保存在：

```text
%LOCALAPPDATA%\SmartAgriBrain\full-stack.json
```

每次启动会重新建立以下日志，避免历史日志无限增长或与本次运行混淆：

```text
%LOCALAPPDATA%\SmartAgriBrain\logs\backend.out.log
%LOCALAPPDATA%\SmartAgriBrain\logs\backend.err.log
%LOCALAPPDATA%\SmartAgriBrain\logs\frontend.out.log
%LOCALAPPDATA%\SmartAgriBrain\logs\frontend.err.log
```

停止后台服务只能使用配套停止入口：

```powershell
Set-Location E:\vscode\esp32\SmartAgriBrain\前端
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev\stop-full-stack.ps1
```

也可以双击 `前端\一键关闭.bat`，或在 VS Code 任务中执行 `SmartAgri: Stop full stack`。

停止脚本会执行以下操作：

- 校验状态文件中的启动器 PID，结束后端和前端的完整进程树。
- 即使状态文件缺失或损坏，也会按本项目启动脚本、Uvicorn、Vite 命令行和 `8000`、`5173` 监听端口重新发现进程。
- 重复扫描，处理旧版 Uvicorn 重载器在关闭过程中替换子进程的情况。
- 删除状态文件，并确认 `8000`、`5173` 已释放。后端 Python 退出后，它创建的 OpenCV 摄像头对象也随进程释放。
- 如果端口属于无法确认的其他程序，拒绝误杀并输出占用 PID。

不要使用 `Stop-Process -Id <PID>` 代替停止脚本。单独结束监听进程或启动器可能留下它的父进程、子进程或摄像头所有者。

关闭后可执行以下命令复核。两条命令都不应返回结果：

```powershell
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in 8000, 5173 }

Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -match 'start-backend\.ps1|start-web\.ps1|uvicorn\s+main:app|vite(?:\.js)?\s.*(?:--port\s+|--port=)5173'
  }
```

### 6. EMQX 与真实硬件联调

项目只使用外部 EMQX TLS，不提供本地 Mosquitto 启动方式。Web 和 API 的任何设备控制都使用真实后端、真实命令队列和 EMQX 下发路径。

当前本机若已有 `前端/backend_api/.env.mqtt.local`，后端会在启动时自动加载它。新电脑或配置丢失时，使用以下脚本生成被 Git 忽略的 EMQX 配置和 ESP32 CA 文件：

```powershell
Set-Location E:\vscode\esp32\SmartAgriBrain\前端
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup\configure-emqx.ps1 `
  -MqttUri 'mqtts://<EMQX域名>:8883' `
  -BackendUsername '<后端账号>' -BackendPassword '<后端密码>' `
  -Esp32Username '<ESP32账号>' -Esp32Password '<ESP32密码>' `
  -CaCertPath 'C:\path\to\emqx-ca.crt'
```

脚本只接受 `mqtts://` 和 `8883`，并要求 CA 证书。账号、密码、CA 和 Wi-Fi 信息只写入被忽略的本机文件，不能提交 Git。

水枪控制不存在模拟开关。后端启动后会将已确认的控制请求下发到 EMQX，因此必须先完成硬件检查、确认急停条件和真机联调。真实 MQTT 配置必须存在于本机 `backend_api/.env.mqtt.local`：

```text
MQTT_ENABLED=true
DEVICE_COMMAND_TRANSPORT=mqtt
```

### 7. 常见问题

- `Missing node_modules`：在 `前端/` 执行 `npm install`。
- `Python was not found`：安装 Python 3.10+，确认 `py -3 --version` 可运行后重新启动后端。
- `Address already in use`：先运行 `scripts\dev\stop-full-stack.ps1`。若脚本提示端口属于未知程序，它会保留该进程；使用 `Get-NetTCPConnection -LocalPort 8000,5173` 查看 PID，再用 `Get-CimInstance Win32_Process -Filter "ProcessId=<PID>"` 确认程序身份后处理。
- 后端可启动但 MQTT 显示未连接：检查 `backend_api/.env.mqtt.local` 是否存在、EMQX 域名/端口/CA 是否正确，以及网络是否允许访问 `8883`。
- 页面操作后没有收到 ACK：先确认 ESP32 已连接 EMQX 并订阅 `smartagribrain/v1/devices/greenhouse_001_s3/command`，再检查设备时间同步、`device_id`/`site_id`、命令有效期和 EMQX ACL。只有 `command_ack.state=executed` 才表示设备控制输出已应用。
- 页面能操作但水泵没有动作：检查 ESP32 在线状态、GPIO26 接线、供电、云台标定和是否收到 `command_ack`。真实模式会驱动硬件，不应以页面状态代替设备 ACK。

## 开发环境

`platformio.ini` 位于 `esp32/`，而不是仓库根目录。当前根工作区通过 `.vscode/settings.json` 读取 `esp32/compile_commands.json`，用于头文件和函数定义跳转。

依赖或编译参数变化后，在 `esp32/` 目录重新生成索引：

```powershell
pio run -t compiledb
```

随后在 VS Code 执行 `C/C++: Reset IntelliSense Database` 或重新加载窗口。

## 文档入口

文档阅读顺序和事实来源见 [docs/README.md](docs/README.md)。协议字段、单位、主题和 REST 路径以 [SmartAgriBrain v1 统一通信与数据标准](docs/smartagribrain-v1-standard.md) 为准；所有尚未确认的问题只记录在 [问题与答复汇总](docs/open-questions.md)。
