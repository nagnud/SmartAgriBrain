# SmartAgriBrain 前后端与 ESP32 边缘端联调配置说明

## 1. 通信架构

本项目采用以下通信链路：

```text
Web 前端 -> FastAPI 后端 -> MQTT Broker -> ESP32
Web 前端 <- FastAPI 后端 <- MQTT Broker <- ESP32
```

Web 前端不直接连接 ESP32。ESP32 只需要连接 Wi-Fi 和后端共同使用的 MQTT Broker。

> 注意：ESP32 端不能填写 `localhost` 或 `127.0.0.1`。ESP32 中的 `localhost` 指 ESP32 自己，不是运行前后端的 PC。

## 2. 当前 PC 网络信息

| 配置项 | 当前值 | 说明 |
| --- | --- | --- |
| PC 局域网 IPv4 | `192.168.3.14` | 当前 WLAN 地址，可能因 DHCP 发生变化 |
| FastAPI 后端地址 | `http://192.168.3.14:8000` | 后端当前监听 `0.0.0.0:8000` |
| 前端本机后端地址 | `http://localhost:8000` | 仅供同一台 PC 上的前端使用 |
| MQTT Broker | **尚未部署或确认** | 当前 PC 的 `1883/8883` 端口没有 MQTT 服务监听 |

正式联调前建议给 PC 设置固定局域网 IP，或者在路由器中为 PC 设置 DHCP 地址保留。

## 3. 待确认的 MQTT 连接配置

如果 MQTT Broker 部署在当前 PC，计划配置如下：

```text
MQTT URI: mqtt://192.168.3.14:1883
MQTT Host: 192.168.3.14
MQTT Port: 1883
MQTT TLS: false
MQTT QoS: 1
MQTT KeepAlive: 60 秒
MQTT Username: <待配置，私下发送>
MQTT Password: <待配置，私下发送>
```

> `mqtt://192.168.3.14:1883` 目前只是计划地址。必须先部署并启动 MQTT Broker、配置账号密码、开放 Windows 防火墙端口后，才能作为有效地址使用。

如果使用云端 MQTT Broker，需要把以上 Host、Port、TLS、用户名和密码替换成云端提供的配置。

## 4. ESP32 基础配置

```text
Device ID: sensairshuttle_001
Schema Version: 1.0
Telemetry Interval: 5000 ms
MQTT Protocol: MQTT 3.1.1
QoS: 1
```

ESP32 工程中的对应配置项：

```text
CONFIG_SENSAIR_IOT_ENABLE=y
CONFIG_SENSAIR_DEVICE_ID="sensairshuttle_001"
CONFIG_SENSAIR_UPLOAD_INTERVAL_MS=5000
CONFIG_SENSAIR_WIFI_SSID="<Wi-Fi名称>"
CONFIG_SENSAIR_WIFI_PASSWORD="<Wi-Fi密码>"
CONFIG_SENSAIR_MQTT_URI="mqtt://192.168.3.14:1883"
CONFIG_SENSAIR_MQTT_USERNAME="<MQTT用户名>"
CONFIG_SENSAIR_MQTT_PASSWORD="<MQTT密码>"
```

Wi-Fi 和 MQTT 密码请私下传递，不要写入 Git 仓库、群聊截图或公开文档。

## 5. MQTT 主题约定

主题前缀：

```text
smartagribrain/v1
```

完整主题：

| 方向 | 主题 | 用途 |
| --- | --- | --- |
| ESP32 -> 后端 | `smartagribrain/v1/devices/sensairshuttle_001/telemetry` | 传感器和执行器状态遥测 |
| ESP32 -> 后端 | `smartagribrain/v1/devices/sensairshuttle_001/status` | 在线、离线和异常断开状态 |
| ESP32 -> 后端 | `smartagribrain/v1/devices/sensairshuttle_001/capabilities` | 固件、传感器和执行器能力声明 |
| 后端 -> ESP32 | `smartagribrain/v1/devices/sensairshuttle_001/command` | 设备控制命令 |
| ESP32 -> 后端 | `smartagribrain/v1/devices/sensairshuttle_001/command_ack` | 命令执行结果回执 |

## 6. ESP32 遥测上报格式

建议继续使用 ESP32 固件当前的 V1 遥测格式，不要用虚假 `0` 代替未安装的传感器。未安装或无效的数据使用 `null`，并通过 `quality` 标明状态。

示例：

```json
{
  "schema_version": "1.0",
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "device_id": "sensairshuttle_001",
  "sequence": 1,
  "sampled_at": 1770000000000,
  "time_quality": "synced",
  "sensors": {
    "temperature_c": 25.30,
    "humidity_pct": 60.10,
    "pressure_kpa": 101.20,
    "gas_resistance_ohm": 12000.00,
    "illuminance_lux": null,
    "co2_ppm": null,
    "soil_moisture_pct": null,
    "soil_ec_ms_cm": null,
    "acceleration_g": {
      "x": 0.000,
      "y": 0.000,
      "z": 1.000
    },
    "gyroscope_dps": {
      "x": 0.000,
      "y": 0.000,
      "z": 0.000
    },
    "magnetic_field_ut": {
      "x": 1.000,
      "y": 2.000,
      "z": 3.000
    }
  },
  "quality": {
    "temperature_c": "ok",
    "humidity_pct": "ok",
    "pressure_kpa": "ok",
    "gas_resistance_ohm": "ok",
    "illuminance_lux": "unsupported",
    "co2_ppm": "unsupported",
    "soil_moisture_pct": "unsupported",
    "soil_ec_ms_cm": "unsupported",
    "imu": "ok",
    "magnetometer": "ok"
  },
  "actuators": {
    "fan": {
      "desired": null,
      "actual": null
    },
    "pump": {
      "desired": null,
      "actual": null
    },
    "grow_light": {
      "desired": null,
      "actual": null
    },
    "alarm": {
      "desired": null,
      "actual": null
    }
  },
  "connectivity": {
    "wifi": "connected",
    "mqtt": "connected",
    "rssi_dbm": -45
  }
}
```

质量状态约定：

| 状态 | 含义 |
| --- | --- |
| `ok` | 数据有效且未过期 |
| `stale` | 曾经有效，但超过规定时间没有更新 |
| `invalid` | 传感器存在，但尚无有效数据 |
| `unsupported` | 当前硬件或固件不支持 |

## 7. 后端控制命令格式

后端向 ESP32 下发的命令统一使用以下格式：

```json
{
  "schema_version": "1.0",
  "command_id": "550e8400-e29b-41d4-a716-446655440000",
  "device_id": "sensairshuttle_001",
  "issued_at": 1770000000000,
  "expires_at": 1770000030000,
  "source": "web_manual",
  "reason": "用户在Web端打开风机",
  "command": {
    "operation": "set",
    "target": "fan",
    "value": 1
  }
}
```

字段要求：

| 字段 | 要求 |
| --- | --- |
| `command_id` | 小写 UUID v4；回执必须原样返回同一个 ID |
| `issued_at` | Unix 毫秒时间戳 |
| `expires_at` | Unix 毫秒时间戳；建议比 `issued_at` 晚 30 秒 |
| `source` | 手动控制使用 `web_manual` |
| `operation` | 当前只使用 `set` |
| `value` | 当前二值执行器只使用 `0` 或 `1` |

第一阶段计划支持的目标：

| target | 含义 | 当前 ESP32 代码 |
| --- | --- | --- |
| `fan` | 风机 | 已有控制逻辑，GPIO 待配置 |
| `pump` | 水泵 | 已有控制逻辑，GPIO 待配置 |
| `grow_light` | 补光灯 | 已有控制逻辑，GPIO 待配置 |
| `alarm` | 报警器 | 已有控制逻辑，GPIO 待配置 |

暂不宣称支持：

```text
curtain
heater
cooler
ventilation
co2_valve
```

## 8. ESP32 命令回执格式

执行成功：

```json
{
  "schema_version": "1.0",
  "command_id": "550e8400-e29b-41d4-a716-446655440000",
  "device_id": "sensairshuttle_001",
  "acknowledged_at": 1770000001000,
  "state": "executed",
  "command": {
    "operation": "set",
    "target": "fan",
    "value": 1
  },
  "actual_value": 1,
  "error": null
}
```

执行失败：

```json
{
  "schema_version": "1.0",
  "command_id": "550e8400-e29b-41d4-a716-446655440000",
  "device_id": "sensairshuttle_001",
  "acknowledged_at": 1770000001000,
  "state": "rejected",
  "command": {
    "operation": "set",
    "target": "fan",
    "value": 1
  },
  "actual_value": null,
  "error": {
    "code": "CAPABILITY_UNSUPPORTED",
    "message": "actuator_not_supported"
  }
}
```

## 9. 边缘端同学需要确认的信息

请回复以下硬件配置：

```text
ESP32开发板型号：
固件版本：

风机 GPIO：
水泵 GPIO：
补光灯 GPIO：
报警器 GPIO：
卷帘 GPIO（如有）：

是否有光照传感器：
是否有真实 CO2 传感器：
是否有土壤湿度传感器：
是否有土壤 EC 传感器：

执行器是高电平有效还是低电平有效：
执行器使用继电器、PWM还是其他驱动：
是否需要安全默认状态和最大连续运行时间：
```

ESP32 当前配置中，风机、水泵、补光灯和报警器 GPIO 都是 `-1`。如果不改成真实 GPIO，ESP32 会把对应命令判定为 `CAPABILITY_UNSUPPORTED`。

## 10. 智能托管功能说明

当前第一阶段建议先完成以下闭环：

```text
真实遥测 -> 后端保存 -> 前端显示
前端二值开关 -> 后端下发 -> ESP32执行 -> ACK回执 -> 前端显示真实结果
```

`smart_control_update`、`smart_control_stop` 和 0-100 强度控制尚未完成端到端协议统一。第一阶段联调时先不启用智能托管命令，避免将未执行的操作显示为成功。

后续如需智能托管，需要单独约定：

- 水泵、补光灯、加热、制冷、通风、CO2 的 0-100 数值如何换算为 GPIO、PWM、档位或运行时间。
- 手动命令和自动托管命令的优先级。
- 最大连续运行时间、互锁条件和断网安全状态。
- 执行器实际值和故障状态的回传方式。

## 11. 前后端侧仍需完成的适配

边缘端连接参数配置完成后，前后端侧仍需修复以下内容，不能只靠 ESP32 单方配置解决：

1. 前端关闭设备数据和控制的 Mock 模式。
2. 后端启用 MQTT，并连接到与 ESP32 相同的 Broker。
3. 后端允许 `null/unsupported` 传感器值。
4. 后端正确解析执行器的 `desired/actual` 嵌套结构。
5. 后端统一使用 UUID v4 命令 ID，并保存 UUID 与数据库记录的映射。
6. 后端正确解析 ESP32 的 UUID 命令回执。
7. 后端统一使用 `grow_light`，或在转换层完成 `light <-> grow_light` 映射。
8. 前端必须等待设备 ACK 或后续遥测，不能在命令刚入队时直接显示执行成功。

## 12. 联调步骤

### 阶段一：网络连通

- [ ] PC 与 ESP32 连接到能互相访问的网络。
- [ ] 确认 PC 局域网 IP。
- [ ] MQTT Broker 已启动并监听正确端口。
- [ ] Windows 防火墙已允许 MQTT 端口。
- [ ] ESP32 能解析 Broker 地址并建立连接。

### 阶段二：MQTT 基础通信

- [ ] ESP32 发布在线状态，后端能收到。
- [ ] ESP32 发布 capabilities，主题和 JSON 正确。
- [ ] ESP32 每 5 秒发布 telemetry。
- [ ] 后端成功保存 telemetry，数据库不再是 0 条记录。
- [ ] 前端关闭 Mock 后能显示真实温湿度。

### 阶段三：控制闭环

- [ ] 后端使用 UUID v4 下发命令。
- [ ] ESP32 校验命令并执行真实 GPIO。
- [ ] ESP32 返回相同 UUID 的 command_ack。
- [ ] 后端把 ACK 关联到原命令。
- [ ] 前端只在 ACK 或遥测确认后更新实际状态。
- [ ] 失败、过期、重复和不支持命令均有明确提示。

## 13. 当前结论

目前前端、后端和 ESP32 都已经有部分通信代码，但还没有完整打通。当前主要阻塞是：

- 前端设备功能仍使用 Mock。
- 后端 MQTT 尚未配置启用。
- 当前 PC 没有 MQTT Broker 监听。
- ESP32 遥测结构与后端模型不完全一致。
- 后端整数命令 ID 与 ESP32 UUID v4 要求不一致。
- ESP32 执行器 GPIO 尚未配置。

完成本文件中的配置和协议适配后，才能形成可靠的“前端 -> 后端 -> ESP32 -> 回执 -> 前端”闭环。
