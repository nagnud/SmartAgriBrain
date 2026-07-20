# SmartAgriBrain 分支协同评审

## 1. 评审范围与结论边界

本报告于 2026-07-11 编写，比较的是以下远端分支的最新提交，而非分支名称或口头描述。

2026-07-20 起，嵌入式职责已变更：ESP32-C5 转为语音与显示终端；新增通用 ESP32 负责传感器采集、MQTT 上报和后续二维云台控制。本报告中关于“C5 负责传感器采集、MQTT 遥测和执行器”的内容只保留为历史基线，不再作为当前开发分工。当前目录和职责以 [当前架构与目录状态](architecture-update-2026-07-20.md) 为准。

- `feature/backend`：评审基线为 `2b95e18`。已实现一套轻量 FastAPI 服务、SQLite 遥测存储、规则库、AI 调用和 Mock 病害识别。
- `feature/frontend`：评审基线为 `e341b1b`。已实现 Vue 管理端，并在分支内额外实现一套 `frontend_dashboard/backend_api` 本地 FastAPI 服务。
- `feature/embedded`：评审基线为 `d9081a2`。已实现 ESP32-C5 端显示工程、环境/惯性传感器采集入口、MQTT 遥测与 MQTT 控制框架。
- `feature/lcd-docs`：评审基线为 `f848ae3`。原本只有项目初始文件；本报告仅写入此分支。

“已确认”只表示可由上述提交中的代码直接验证；不表示该功能已经真机、网络或端到端验收通过。负责人姓名、实际硬件接线、最终部署位置和消息代理地址并未出现在代码中，均列为待确认事项。

## 2. 各分支当前完成内容

### 2.1 后端分支：`feature/backend`

已完成：

- `backend_server/main.py` 提供 HTTP 遥测接收、最新值、历史值、状态、控制命令、知识库匹配、AI 分析和 Mock 图像识别接口。
- `backend_server/models.py` 与 `database.py` 使用 SQLite 保存温度、湿度、气压、气体阻值、Wi-Fi、MQTT 和风机状态。
- `backend_server/ai/` 封装 DeepSeek 调用、提示词、结果解析和基于温湿度的风机兜底规则。
- `backend_server/mock_device.py` 可以用 HTTP 向本服务发送模拟遥测数据。

当前完成度判断：后端核心原型已经具备，但它尚不是可与其他两个分支直接联调的统一服务。它没有 MQTT 订阅/发布实现，也没有命令持久化、命令回执处理、鉴权或跨域配置。

### 2.2 前端分支：`feature/frontend`

已完成：

- `frontend_dashboard/src/App.vue` 和组件实现监测总览、趋势、病害识别、AI 建议、专家问答、天气、知识库、报警与远程控制界面。
- `frontend_dashboard/src/services/api.ts` 抽象了设备、AI、天气、图像、知识库和应用状态接口，并提供 Mock 回退。
- `frontend_dashboard/src/services/smartControl.ts` 实现基于环境和天气的前端本地智能调控计算。
- `frontend_dashboard/backend_api/` 另有一套 FastAPI 服务，已实现天气、知识库、图片、应用状态、专家问答和 AI 农事建议的一部分接口。

当前完成度判断：页面和交互原型较完整，但默认仍显示 Mock 遥测；其接口契约与 `feature/backend` 不一致，并且仓库内已经出现两套职责重叠的 Python 后端。

### 2.3 嵌入式分支：`feature/embedded`

已完成：

- `embedded_esp32c5` 是 ESP-IDF 工程，板级配置目标为 `esp32c5`，包含 ST77916 QSPI 显示、Brookesia 电话式 UI 和环境页面。
- `common_components/sensair_iot` 建立 Wi-Fi、SNTP、MQTT、周期遥测、执行器队列、命令解析和 ACK 发布机制。
- 温度应用会调用 `sensair_sensor_update_environment`；罗盘/手势相关代码会更新 IMU 与磁力计快照。
- 支持 `fan`、`pump`、`light`、`alarm` 四类命令及 `*_on`、`*_off` 形式。

当前完成度判断：端侧通信框架已实现，且可产生结构化 MQTT 遥测，但默认 Wi-Fi、MQTT 地址和四个执行器 GPIO 都为空或 `-1`，所以默认构建不是一个可直接联网并驱动实际继电器的配置。

## 3. 已确认的协同链路问题

### 3.1 设备遥测无法进入后端

嵌入式端在 `sensair_iot.c` 中只把遥测 JSON 发布到 `CONFIG_SENSAIR_TOPIC_TELEMETRY`，默认主题为 `devices/sensairshuttle_001/telemetry`。后端分支只提供 `POST /api/device/telemetry`，没有 MQTT 客户端、Broker 连接或订阅器。

因此，当前不存在“ESP32 MQTT 遥测 -> 后端数据库”的实现链路。`mock_device.py` 的 HTTP 测试不能证明真机遥测已经接通。

### 3.2 网页命令无法到达 ESP32

前端通过 `POST /api/device/command` 发命令。后端的同名接口当前只打印命令并原样返回 `command_dispatched`，没有把命令发布到 MQTT。嵌入式端只订阅 MQTT 命令主题，并在执行后把 ACK 发布到 MQTT ACK 主题。

因此，当前不存在“网页 -> 后端 -> MQTT -> ESP32 -> ACK -> 网页”的闭环；任何前端显示的命令成功都不能代表硬件已经动作。

### 3.3 前端与后端 HTTP 返回结构不兼容

前端 `api.ts` 期望的最新遥测是顶层 `device_id`、`timestamp`、`sensors`、`status`，历史记录是数组，状态是状态对象，命令结果含 `success`、`executed_at` 和最新状态。

后端分支实际返回：

- `GET /api/device/latest`：后端实际返回 `{ "status": "success", "data": TelemetryRecord }`，传感器字段已经扁平化；前端无法从顶层取得 `sensors` 和 `status`。
- `GET /api/device/history`：后端实际返回 `{ "status": "success", "data": [TelemetryRecord] }`；前端期望数组，且字段集合不同。
- `GET /api/device/status`：后端实际返回 `{ "status": "success", "device_status": {...} }`；前端期望直接得到状态对象。
- `POST /api/device/command`：后端实际返回 `{ "status": "success", "command_dispatched": {...} }`；前端期望可显示的 `CommandResult`，字段不匹配。
- `POST /api/ai/analyze`：后端使用查询参数读取 `device_id`、`crop` 并从自己的数据库取数据；前端发送的完整 JSON 体不会成为后端分析输入，返回体也缺少前端要求的 `risk_score`、`basis`、`updated_at` 等字段。

此外，`feature/backend` 没有启用 CORS 中间件。浏览器从默认的 `http://localhost:5173` 调用 `http://localhost:8000` 时会被浏览器跨域策略拦截，即使接口本身已启动。

### 3.4 数据字段未统一

前端实时控制算法依赖 `light`、`co2`、`soil_moisture`、`soil_ec`；嵌入式 MQTT 载荷目前提供温湿度、气压、气体阻值、IMU 和磁力计，不提供上述四个农业字段。后端数据库又只保存四个环境字段和一个风机状态，丢弃 IMU、磁力计、泵、灯、报警及所有前端农业字段。

这意味着即使先接通网络，仪表盘、趋势图和智能调控仍会因字段缺失而不能基于真实数据工作。

### 3.5 命令能力和硬件能力不一致

前端界面与智能调控使用水泵、补光、升温、降温、通风、CO2、卷帘、报警和 `smart_control_*` 等动作；嵌入式端只识别 `fan`、`pump`、`light`、`alarm`。其中四个 GPIO 的 Kconfig 默认值均为 `-1`，代码会把它们当作 virtual actuator 处理。

`curtain_*`、`heat`、`cool`、`vent`、`co2` 和智能托管复合命令目前没有端侧执行语义，也没有硬件映射。必须先定义能力集，不能把前端显示状态当作设备状态。

### 3.6 两套后端的职责重叠

后端分支的服务根目录为 `backend_server/`；前端分支中又有 `frontend_dashboard/backend_api/`。两者都使用 FastAPI，都假定本地 SQLite，并共同使用了 `/api/ai/analyze` 等路径的一部分；但前者实现设备遥测，后者实现天气、知识库、图片和助手服务，两边的数据模型不同。

在没有 API 网关、反向代理或明确服务拆分的情况下，前端只能连接到一个 `VITE_API_BASE_URL`，无法同时获得两套服务的全部接口。必须合并为一个服务，或明确服务边界、端口和网关路由。

## 4. 需要统一的内容

### 4.1 统一目标架构

建议把“设备接入/命令网关”设为唯一的设备数据入口，并由一个对前端稳定的 HTTP API 服务读取数据库和命令状态。MQTT 不直接暴露给浏览器。

```text
ESP32-C5 -- MQTT --> 设备接入服务 -- 数据库 --> Web API --> Vue 前端
   ^                    |                              |
   |                    +---- MQTT command / ACK -------+
   +-----------------------------------------------------+
```

需要指定哪个现有目录演进为该服务。代码无法决定这是 `backend_server`、`frontend_dashboard/backend_api`，还是新建网关；该决定必须由项目负责人确认。

### 4.2 统一 MQTT 契约

至少需要固定以下内容，并保存为仓库内版本化文档：

- 主题模板：`devices/{device_id}/telemetry`、`command`、`ack`、`status`。
- QoS、retain、离线遗嘱、重连和重复消息处理策略。
- 遥测 JSON schema、必填/可选字段、单位、有效性标志和版本号。
- 命令 JSON schema：至少包含 `command_id`、`device_id`、`command`、`value`、`issued_at`、`source`。
- ACK JSON schema：至少包含 `command_id`、执行结果、失败原因、设备时间和实际执行状态。
- MQTT TLS、账户权限和设备凭据的配置方式；不得把密码提交到仓库。

### 4.3 统一 REST API 契约

建议采用一个 `/api/v1` 前缀和 OpenAPI 文档作为唯一来源，前端类型由该 schema 生成或至少以它为准。需要统一：

- 最新遥测、历史、状态、报警、命令、AI、天气、病害和知识库的路径与响应包装规则。
- 遥测响应必须保持嵌套 `sensors` 与 `status`，或前端同时修改为接受明确的扁平 DTO；两种形式不可混用。
- 错误响应、分页、时间格式、设备筛选和多设备权限规则。
- 命令接口的 HTTP 语义：仅表示“已接收”还是“设备已执行”；后者必须等待/查询 ACK，不能在入队时伪造成功。

### 4.4 统一领域数据与单位

建议建立 `telemetry-v1`：

- 环境：`temperature`(degC)、`humidity`(pct)、`pressure`(kPa)、`gas_resistance`(ohm)、`light`(lux)、`co2`(ppm)。
- 土壤：`soil_moisture`(pct)、`soil_ec`(mS/cm)，以及传感器缺失时的 `valid=false`。
- 设备：`fan`、`pump`、`light`、`alarm`、`curtain` 的“期望状态”和“实际状态”。
- 质量：`timestamp`、采样时钟来源、数据版本、各传感器 `valid`、错误码。

服务器应使用接收时间兜底并标注设备时间是否可信。当前嵌入式端在 SNTP 未成功前会发送 `timestamp=0`，不能把它当作有效历史排序时间。

### 4.5 统一设备能力与控制安全规则

为每台设备定义能力清单，例如 `fan`、`pump`、`light`、`alarm`、`curtain`，以及每项的 GPIO/驱动、值域、互锁关系、默认安全状态和最大连续运行时间。前端只显示设备声明支持的控制项。

智能调控只能提出“期望动作”；真正下发前必须经过后端限幅、互锁、权限、超时自动关闭和 ACK 校验。没有真实继电器 GPIO 映射时，应在 API 中明确返回 `simulated`，而不是成功执行。

### 4.6 统一配置与部署

- 明确最终服务清单、端口、域名/反向代理和 CORS 白名单。
- 将设备 ID、MQTT 主机、主题前缀、Wi-Fi、AI Key、天气 Key 放入各自 `.env` 或 ESP-IDF 安全配置；提交模板，不提交真实值。
- 后端 SQLite 路径应基于应用目录或明确环境变量。`backend_server/database.py` 当前使用相对路径，随启动目录变化可能创建不同数据库文件。
- `backend_server/agri_brain.db` 已被提交到仓库；应改为初始化脚本/迁移文件，避免样例运行数据进入版本控制。

## 5. 代码错误与风险分级

### P0：阻断真实联调

1. MQTT 与 HTTP 没有桥接，遥测无法入库，命令无法到设备。
2. 前端与 `feature/backend` 的数据结构、AI 请求语义和命令响应不兼容。
3. `feature/backend` 缺少 CORS，默认 Web 开发地址无法直接调用它。
4. 前端 `.env.example` 默认 `VITE_USE_MOCK=true`；未显式切换时，页面展示的是模拟数据而非真实设备数据。

### P1：接通后会导致错误结果或错误控制

1. 前端依赖的光照、CO2、土壤湿度、土壤 EC 没有端到端采集与存储链路。
2. 后端接收遥测后丢弃泵、灯、报警、IMU 和磁力计等字段，无法还原设备实际状态。
3. 前端命令集超出嵌入式端支持范围；执行器 GPIO 默认均为 virtual actuator。
4. 命令没有端到端 `command_id` 回执关联，也没有“已接收/已执行/超时/失败”的状态机。
5. 设备控制、MQTT 命令和 `frontend_dashboard/backend_api` 的 CORS 配置均未见认证与授权边界；接入真实网络前必须补齐。

### P2：构建、维护与部署风险

1. `brookesia_app_temperature/CMakeLists.txt` 无条件链接 `esp32_risc_v/libalgobsec.a`。这与 ESP32-C5 的 RISC-V 目标一致，但如果误选为 `esp32`/Xtensa 会在链接阶段失败；应增加 `IDF_TARGET=esp32c5` 的显式构建检查。
2. 两套独立 SQLite 数据库和两套 FastAPI 启动方式会使开发人员难以判断当前页面使用哪一份数据。
3. 后端分支的 `.gitignore` 未排除 `*.db`，现有 `agri_brain.db` 已入库，易造成提交样例数据、冲突和误用旧数据。

## 6. 建议的协同实施顺序

1. 项目负责人确认唯一后端/网关归属，以及 MQTT Broker 的部署位置。
2. 三方共同冻结 `telemetry-v1`、`command-v1`、`ack-v1` 和 REST OpenAPI；先以 JSON 示例和契约测试通过为准。
3. 后端实现 MQTT 订阅、遥测入库、命令发布、ACK 持久化与查询接口。
4. 嵌入式填写真实 Wi-Fi/MQTT/执行器 GPIO 配置，按契约发布数据，并为每个命令返回可关联的 ACK。
5. 前端关闭遥测 Mock，改为消费统一 REST DTO；仅展示设备能力声明支持的控制项。
6. 增加最小端到端验收：一条真实遥测显示、一次风机命令 ACK、一次断网/超时提示、一次不支持命令的拒绝。

## 7. 需要负责人确认的问题

以下问题无法从当前代码可靠推出，必须在实施前确认：

1. 最终保留哪一个后端：`backend_server`、`frontend_dashboard/backend_api`，还是新建单独的设备网关？对应负责人是谁？
2. MQTT Broker 的地址、TLS 要求、账户权限和设备注册方案是什么？
3. 真机实际接入了哪些农业传感器与执行器？四个 GPIO 分别对应什么电路，是否需要低电平有效或互锁？
4. `light`、`co2`、`soil_moisture`、`soil_ec` 是计划接入、已有但未接线，还是只用于页面演示？
5. 控制接口的成功定义是什么：服务收到命令，还是 ESP32 回 ACK 后才算成功？ACK 等待时限是多少？
6. 本项目是单设备演示还是多设备、多用户系统？这决定设备 ID、数据隔离和权限模型。

## 8. 验收标准

在上述问题确认后，只有同时满足以下条件才能宣布三端协同完成：

- ESP32 发出的 MQTT 载荷可在数据库中按设备和时间查询到，字段和单位符合版本化 schema。
- 前端关闭 Mock 后可显示同一条真实遥测，且历史曲线使用同一数据源。
- 前端下发一个支持的执行器命令后，界面先显示“已接收”，仅在收到对应 `command_id` 的 ACK 后显示“已执行”。
- 不支持的命令、设备离线、MQTT 断开、传感器无效和 ACK 超时均有明确错误状态，不伪造成功。
- ESP32-C5 构建过程强制校验目标芯片，且目标错误时在配置阶段失败，而不是在链接阶段才报架构错误。
