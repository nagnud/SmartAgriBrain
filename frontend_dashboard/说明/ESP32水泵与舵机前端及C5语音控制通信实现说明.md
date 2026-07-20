# ESP32 水泵与舵机：Web 前端及 C5 语音控制通信实现说明

## 1. 文档用途

本文交给传感器/执行器 ESP32（下文称 S3）开发人员或其代码 Agent，用于实现以下闭环：

1. Web 前端控制水泵开关、喷水功率和水枪目标位置。
2. Web 前端静态/动态拖动目标时，控制水枪舵机。
3. C5 采集语音，后端识别并要求用户确认后，控制同一台 S3 上的水泵和水枪。
4. S3 执行后返回真实 ACK 和遥测，Web 与 C5 显示真实结果，而不是仅显示“命令已发送”。

本文只规定通信协议、状态机和安全要求，不规定具体舵机型号、GPIO 或机械标定值。开发人员必须根据实际接线填写这些参数，不能直接照抄示例引脚。

---

## 2. 必须先理解的系统结构

Web 和 C5 都不直接连接 S3，统一经过 FastAPI 后端和 MQTT Broker：

```text
Web 前端 ──HTTP/SSE──> FastAPI 后端 ──MQTT──> S3
Web 前端 <──HTTP/SSE── FastAPI 后端 <──MQTT── S3

C5 ──语音请求/确认 MQTT 或语音 HTTP──> FastAPI 后端
C5 <──AI 回复/操作状态──────────────── FastAPI 后端
                                      │
                                      └──同一套 MQTT command──> S3
```

因此，S3 不需要订阅 C5 的语音 Topic，也不需要在 S3 上做语音识别。S3 只需正确实现后端下发的统一 `command` Topic，并发布 `command_ack`、`telemetry`、`status` 和 `capabilities`。

C5 当前使用的语音链路为：

- `smartagribrain/v1/devices/greenhouse_001_c5/assistant/request`
- `smartagribrain/v1/devices/greenhouse_001_c5/assistant/decision`
- `smartagribrain/v1/devices/greenhouse_001_c5/assistant/response`

C5 说“打开水泵”后，后端先返回待确认操作；用户在 C5 上确认后，后端才向 S3 下发普通 `pump` 命令。C5 请求“瞄准/喷某个物体”时，后端完成视觉定位并等待确认，确认后向 S3 下发 `target_position` 水枪命令。

---

## 3. S3 的固定身份和 MQTT Topic

除非前后端配置同时修改，否则使用以下值：

```text
site_id: greenhouse_001
device_id: greenhouse_001_s3
schema_version: 1.0
MQTT QoS: 1
MQTT protocol: 3.1.1
```

S3 使用以下 Topic：

| 方向 | Topic | retain | 用途 |
|---|---|---:|---|
| S3 → 后端 | `smartagribrain/v1/devices/greenhouse_001_s3/telemetry` | 否 | 传感器及水泵、舵机实际状态 |
| S3 → 后端 | `smartagribrain/v1/devices/greenhouse_001_s3/status` | 是 | 在线/离线状态及 LWT |
| S3 → 后端 | `smartagribrain/v1/devices/greenhouse_001_s3/capabilities` | 是 | 能力声明 |
| 后端 → S3 | `smartagribrain/v1/devices/greenhouse_001_s3/command` | 否 | 所有水泵和水枪命令 |
| S3 → 后端 | `smartagribrain/v1/devices/greenhouse_001_s3/command_ack` | 否 | 命令执行回执 |

Broker 地址、用户名和密码必须通过私有配置文件或构建配置注入，不得写进仓库。S3 端的 Broker、账号、Topic 前缀必须与后端 `.env.mqtt.local` 保持一致。

---

## 4. S3 必须实现的能力

### 4.1 水泵直接控制

S3 必须支持：

```text
operation = set
target = pump
value = 0..100
```

语义：

- `value = 0`：立即停泵。
- `value = 1..100`：按百分比控制水泵；若现场只有继电器，则 `1..100` 均视为开，遥测 `actual` 返回 `100`。
- 若使用 PWM/MOS 管，必须将 0–100% 映射到实际 PWM 占空比。
- 不得收到命令后先 ACK 再执行；必须先完成硬件写入或确认硬件已进入目标状态，再返回成功 ACK。

### 4.2 水枪舵机控制

水枪命令中的位置采用地面极坐标：

- `ground_range_mm`：S3/水枪原点到目标地面点的水平距离，单位 mm。
- `bearing_deg`：方向角，单位度；`0` 为正前方，负数向左，正数向右。

至少实现一个方向舵机：

```cpp
bool set_nozzle_bearing_deg(float bearing_deg);
```

如果机械结构有第二个俯仰舵机，还应实现：

```cpp
bool set_nozzle_range_mm(float ground_range_mm);
```

距离到俯仰角不能凭空套用固定公式，必须通过实际机械尺寸或标定表换算。推荐使用标定点线性插值：

```text
距离 mm:   300, 600, 900, 1200, 1700
舵机角度: 由现场标定填写
```

只有一个舵机时：

- `bearing_deg` 控制舵机方向。
- `ground_range_mm` 不控制第二个舵机，只用于水泵功率或前端显示。

所有角度必须先经过机械安全范围校验。超出安全范围时应拒绝命令并返回 `TARGET_OUT_OF_RANGE`，不要静默映射到极限位置，否则前端会误以为已经瞄准真实目标。

### 4.3 水枪与水泵联动

水枪命令中：

```text
spray_enabled = false  → 水泵输出必须为 0
spray_enabled = true   → 水泵输出使用 pump_control_percent
```

执行顺序建议：

1. 先校验完整命令。
2. `spray_enabled=false` 时先停泵，再移动舵机。
3. `spray_enabled=true` 时先停泵或保持关闭，移动舵机到目标并等待稳定，再按 `pump_control_percent` 启泵。
4. 任一步失败都必须保持或恢复停泵状态。

绝不能仅解析和打印 `pump_control_percent`。必须真正调用水泵驱动函数。

---

## 5. 普通水泵命令格式

Web 手动控制或 C5 语音确认“打开水泵”后，后端会发送类似：

```json
{
  "schema_version": "1.0",
  "command_id": "2cb29b02-c5ec-45ee-8f7a-3194f7de7bc8",
  "device_id": "greenhouse_001_s3",
  "site_id": "greenhouse_001",
  "issued_at": 1784563200000,
  "expires_at": 1784563230000,
  "source": "edge_voice",
  "reason": "现场语音请求打开水泵",
  "command": {
    "operation": "set",
    "target": "pump",
    "value": 100
  }
}
```

关闭水泵：

```json
{
  "schema_version": "1.0",
  "command_id": "15e52de0-0e5b-4601-9bfe-b6a178723a5b",
  "device_id": "greenhouse_001_s3",
  "site_id": "greenhouse_001",
  "issued_at": 1784563205000,
  "expires_at": 1784563235000,
  "source": "edge_voice",
  "reason": "现场语音请求关闭水泵",
  "command": {
    "operation": "set",
    "target": "pump",
    "value": 0
  }
}
```

`source` 只用于记录来源，不能用它决定是否执行。Web 和 C5 最终都要进入同一套校验与硬件控制函数。

---

## 6. 水枪静态目标命令格式

Web 点击“确认目标”，或 C5 对视觉识别到的喷水目标进行确认后，后端会发送类似：

```json
{
  "schema_version": "1.0",
  "command_id": "127",
  "device_id": "greenhouse_001_s3",
  "issued_at": 1784563200000,
  "expires_at": 1784563230000,
  "source": "web_manual",
  "reason": "静态水枪目标确认",
  "command": {
    "operation": "target_position",
    "target": "position",
    "value": 1,
    "position": {
      "ground_range_mm": 850.0,
      "bearing_deg": -12.5
    },
    "water_gun": {
      "mode": "static",
      "spray_enabled": true,
      "simulation_only": false,
      "pump_control_percent": 50.0,
      "session_id": null,
      "sequence": 8
    }
  }
}
```

注意：当前水枪后端使用旧的持久命令队列，所以 `command_id` 可能是十进制字符串；普通远程执行器命令通常是 UUID。S3 必须同时接受：

- 合法 UUID；
- 1–18 位非零十进制字符串。

ACK 必须原样返回收到的 `command_id`，不能自行生成新 ID。

### 6.1 `simulation_only` 的处理

- 字段为 `true` 或缺失：只校验、记录和返回模拟 ACK，绝不写舵机或水泵。
- 字段为 `false`：允许进入真实硬件执行流程。

不要为了“看起来能工作”而忽略此安全字段。要真实联调，后端也必须显式配置：

```text
WATER_GUN_SIMULATION_ONLY=false
```

当前后端默认值是 `true`；如果后端没有改配置，单独修改 S3 无法进入真实喷水流程。

### 6.2 只有位置、没有 `water_gun` 的命令

这种命令表示发送目标位置：

- 可以移动舵机到目标位置；
- 不得启动水泵；
- ACK 中返回接收到的位置。

---

## 7. 水枪动态目标命令格式

动态模式的命令结构与静态模式相同，区别如下：

```json
{
  "command": {
    "operation": "target_position",
    "target": "position",
    "value": 1,
    "position": {
      "ground_range_mm": 720.0,
      "bearing_deg": 18.0
    },
    "water_gun": {
      "mode": "dynamic",
      "spray_enabled": true,
      "simulation_only": false,
      "pump_control_percent": 42.4,
      "session_id": "water-gun-6c40a7d764884796a51377c959ef0915",
      "sequence": 12
    }
  }
}
```

动态模式要求：

1. `session_id` 必须非空。
2. `sequence` 必须大于 0。
3. 同一 `session_id` 中，新命令的 `sequence` 必须严格递增。
4. 旧序号返回 `STALE_TARGET`，不得再次移动舵机或改变水泵。
5. 新 `session_id` 表示新会话，重置该会话的序号记录。
6. 建议限制最大执行频率为 5 Hz；MQTT 回调中只复制最新目标，舵机任务按固定周期消费，避免阻塞 MQTT 线程。

### 7.1 动态模式超时

S3 必须有独立于后端的安全超时：连续 3 秒没有收到本会话的有效动态目标/保活命令时：

1. 立即停泵；
2. 清除动态喷水活动状态；
3. 舵机可保持最后安全位置，不要在未知环境下突然回零；
4. 发布状态 `reason=water_gun_dynamic_timeout`。

### 7.2 当前后端存在的动态心跳缺口

当前 Web 每 1 秒调用一次后端心跳接口，但该心跳只更新后端内存，不会发送 MQTT 到 S3。只有拖动目标时，后端才会下发新的动态位置。因此，目标保持不动超过 3 秒时，正确实现安全超时的 S3 会停泵。

物理联调前，前后端 Agent 必须任选一种方式补齐：

1. 推荐：后端在动态会话存活期间，每 1 秒用递增 `sequence` 重发当前目标；或
2. 新增专用水枪心跳命令，并由 S3 订阅和校验。

在该缺口修复前，不能声称动态连续喷水已经完成。

---

## 8. 命令校验要求

S3 收到任何命令时，按顺序校验：

1. MQTT Topic 必须精确等于本机 `command` Topic。
2. JSON 必须完整，拒绝无法重组的分片和超大消息。
3. `schema_version == "1.0"`。
4. `device_id == "greenhouse_001_s3"`。
5. `command_id` 是 UUID 或合法十进制 ID。
6. `issued_at`、`expires_at` 使用 Unix 毫秒。
7. 当前时间不得晚于 `expires_at`。
8. `expires_at > issued_at`，且 TTL 不应超过 30 秒。
9. `pump.value`、`pump_control_percent` 必须在 0–100。
10. `bearing_deg` 先满足协议范围 `-180..180`，再满足实际机械安全范围。
11. `ground_range_mm` 必须满足实际水枪安全工作范围。
12. 动态模式必须校验会话和递增序号。
13. `simulation_only=true` 时禁止所有物理输出。

校验失败也必须发布失败 ACK；只有 JSON 完全无法解析且取不到 `command_id` 时，才只能记录日志。

---

## 9. ACK 格式

### 9.1 水泵成功

```json
{
  "schema_version": "1.0",
  "command_id": "2cb29b02-c5ec-45ee-8f7a-3194f7de7bc8",
  "device_id": "greenhouse_001_s3",
  "site_id": "greenhouse_001",
  "acknowledged_at": 1784563200300,
  "state": "executed",
  "command": {
    "operation": "set",
    "target": "pump",
    "value": 100
  },
  "actual_value": 100,
  "message": "executed",
  "error": null
}
```

### 9.2 水枪成功

```json
{
  "schema_version": "1.0",
  "command_id": "127",
  "device_id": "greenhouse_001_s3",
  "site_id": "greenhouse_001",
  "acknowledged_at": 1784563200450,
  "state": "executed",
  "command": {
    "operation": "target_position",
    "target": "position",
    "value": 1
  },
  "received_position": {
    "ground_range_mm": 850.0,
    "bearing_deg": -12.5
  },
  "received_water_gun": {
    "mode": "static",
    "spray_enabled": true,
    "simulation_only": false,
    "pump_control_percent": 50,
    "session_id": "",
    "sequence": 8
  },
  "actual_value": 50,
  "message": "executed",
  "error": null
}
```

`actual_value` 对水枪命令表示实际水泵输出百分比。若能读取真实舵机反馈，可额外增加 `actual_position`；后端会忽略不认识的附加字段，但不得删除上述核心字段。

### 9.3 失败 ACK

```json
{
  "schema_version": "1.0",
  "command_id": "127",
  "device_id": "greenhouse_001_s3",
  "site_id": "greenhouse_001",
  "acknowledged_at": 1784563200450,
  "state": "rejected",
  "command": {
    "operation": "target_position",
    "target": "position",
    "value": 1
  },
  "actual_value": null,
  "message": "target_out_of_range",
  "error": {
    "code": "TARGET_OUT_OF_RANGE",
    "message": "target_out_of_range"
  }
}
```

建议错误码：

| 错误码 | 含义 |
|---|---|
| `INVALID_COMMAND` | 字段缺失、类型或范围错误 |
| `COMMAND_EXPIRED` | 命令已过期 |
| `DEVICE_TIME_UNSYNCED` | 设备时间未同步，无法安全判断 TTL |
| `CAPABILITY_UNSUPPORTED` | 硬件不存在或未启用 |
| `TARGET_OUT_OF_RANGE` | 超出舵机/机械安全范围 |
| `STALE_TARGET` | 动态序号未递增 |
| `RESOURCE_BUSY` | 水泵或舵机正被更高优先级任务占用 |
| `ACTUATOR_FAULT` | 驱动、反馈或硬件故障 |

---

## 10. 重复命令和幂等性

MQTT QoS 1 允许重复投递。S3 必须缓存最近至少 8 个 `command_id` 及其最终 ACK：

- 再次收到同一个 `command_id` 时，不得重复移动舵机或重新启动水泵。
- 应原样重发缓存 ACK。
- 如果同一个 `command_id` 的内容发生变化，返回 `INVALID_COMMAND` 并记录严重协议错误。

断线重连后至少保留当前动态会话的 `session_id`、最后 `sequence` 和泵关闭状态；若无法持久化，重启时必须默认停泵，并把旧动态命令视为过期。

---

## 11. 水泵控制权与优先级

Web 水枪和 C5 语音水泵可能同时操作同一水泵，必须定义唯一状态机。建议：

```cpp
enum class PumpOwner {
    NONE,
    DIRECT_COMMAND,
    WATER_GUN_STATIC,
    WATER_GUN_DYNAMIC,
};
```

优先级规则：

1. 任何合法的停泵命令都立即执行，优先级最高。
2. 动态水枪活动期间，新的直接“开泵”命令返回 `RESOURCE_BUSY`，避免绕过水枪安全逻辑。
3. 直接“关泵”命令应停泵并结束本地动态喷水状态，防止下一条旧动态目标又自动启泵。
4. 新的、经过确认的水枪静态/动态命令可以取得水泵控制权。
5. MQTT 断开、Wi-Fi 长时间断开、设备重启、动态超时或驱动故障时必须停泵。
6. 上电初始化顺序必须先配置输出为安全关闭，再连接网络。

如果项目最终决定使用其他优先级，必须同时修改 Web/C5 提示语和后端状态机，不能只在 S3 内静默改变语义。

---

## 12. 建议的 S3 代码分层

不要把舵机延时、泵 PWM 和 JSON 解析全部写在 MQTT 回调中。建议结构：

```text
src/
  main.cpp
lib/
  mqtt/
    iot_mqtt.h
    mqtt_client.cpp
  pump/
    pump_controller.h
    pump_controller.cpp
  water_gun/
    water_gun_controller.h
    water_gun_controller.cpp
```

硬件层建议接口：

```cpp
struct WaterGunTarget {
    float groundRangeMm;
    float bearingDeg;
    bool sprayEnabled;
    uint8_t pumpPercent;
};

class PumpController {
public:
    bool beginSafeOff();
    bool setPercent(uint8_t percent);
    void emergencyStop();
    uint8_t actualPercent() const;
};

class WaterGunController {
public:
    bool beginSafe();
    bool validate(const WaterGunTarget &target, const char **errorCode) const;
    bool moveTo(const WaterGunTarget &target);
    void holdLastSafePosition();
    float actualBearingDeg() const;
};
```

主循环/任务的核心流程：

```cpp
void applyCommand(const IotCommand &cmd) {
    if (cmd.isSimulationOnly) {
        publishSimulatedAck(cmd);
        return;
    }

    if (cmd.target == PUMP) {
        applyDirectPumpCommand(cmd);
        return;
    }

    if (cmd.target == POSITION) {
        pump.emergencyStop();
        if (!waterGun.validate(cmd.targetPosition, &errorCode)) {
            publishRejectedAck(cmd, errorCode);
            return;
        }
        if (!waterGun.moveTo(cmd.targetPosition)) {
            pump.emergencyStop();
            publishRejectedAck(cmd, "ACTUATOR_FAULT");
            return;
        }
        if (cmd.waterGunPresent && cmd.sprayEnabled) {
            if (!pump.setPercent(cmd.pumpControlPercent)) {
                pump.emergencyStop();
                publishRejectedAck(cmd, "ACTUATOR_FAULT");
                return;
            }
        }
        publishExecutedAck(cmd, pump.actualPercent());
    }
}
```

上面是流程示意，不要求原样复制。实际实现不得使用会让 MQTT 任务长时间阻塞的 `delay()`；舵机稳定等待应使用状态机、定时器或独立执行任务。

---

## 13. 能力声明

S3 连接 MQTT 后发布 retained `capabilities`。真实硬件完成前不要虚报支持：

```json
{
  "schema_version": "1.0",
  "device_id": "greenhouse_001_s3",
  "site_id": "greenhouse_001",
  "reported_at": 1784563200000,
  "firmware": {
    "target": "esp32",
    "version": "填写实际版本"
  },
  "actuators": {
    "pump": {
      "supported": true,
      "type": "percent",
      "min": 0,
      "max": 100
    }
  },
  "positioning": {
    "target_position_supported": true,
    "range_unit": "mm",
    "bearing_unit": "deg",
    "water_gun_control_supported": true,
    "water_gun_simulation_only": false,
    "dynamic_max_hz": 5,
    "bearing_feedback_supported": false
  }
}
```

如果舵机或泵尚未接线：

- 对应 `supported` 必须为 `false`；
- `water_gun_simulation_only` 必须为 `true`；
- 收到真实控制命令返回 `CAPABILITY_UNSUPPORTED`，不得返回成功。

---

## 14. 遥测要求

S3 定期上报水泵实际状态；不能仅根据最后一条命令伪造：

```json
{
  "schema_version": "1.0",
  "message_id": "7aa2db35-c48a-4258-8318-8d16426971e1",
  "device_id": "greenhouse_001_s3",
  "site_id": "greenhouse_001",
  "sequence": 100,
  "sampled_at": 1784563200000,
  "actuators": {
    "pump": {
      "supported": true,
      "desired": 50,
      "actual": 50,
      "unit": "percent",
      "master_enabled": true
    }
  },
  "positioning": {
    "bearing_deg": -12.5,
    "ground_range_mm": 850,
    "mode": "static",
    "spray_enabled": true,
    "session_id": null,
    "sequence": 8,
    "fault": null
  },
  "connectivity": {
    "wifi": "connected",
    "mqtt": "connected",
    "rssi_dbm": -55
  }
}
```

后端当前会使用 `actuators.pump`。`positioning` 是建议的扩展字段，现有后端可能只保存或忽略它；如需 Web 显示真实舵机反馈，需要前后端 Agent 再把该字段加入 `SiteState`，不能只靠 S3 上报。

---

## 15. LWT 和异常安全

S3 连接 MQTT 时配置 retained LWT：

```json
{
  "schema_version": "1.0",
  "device_id": "greenhouse_001_s3",
  "site_id": "greenhouse_001",
  "reported_at": 1784563200000,
  "online": false,
  "reason": "unexpected_disconnect"
}
```

连接成功后在相同 `status` Topic 发布：

```json
{
  "schema_version": "1.0",
  "device_id": "greenhouse_001_s3",
  "site_id": "greenhouse_001",
  "reported_at": 1784563200000,
  "online": true,
  "reason": "connected"
}
```

必须满足：

- 上电默认停泵。
- 看门狗复位后默认停泵。
- 动态会话超时立即停泵。
- 舵机移动失败立即停泵。
- MQTT 断开时停止动态喷水；静态持续喷水是否停止应由项目安全策略确定，推荐也停止。
- 水泵不能因保留的 MQTT 命令或设备重连自动启动；`command` Topic 不使用 retain。

---

## 16. 当前 Web/后端必须配合修改的四项内容

以下问题不是 S3 单方代码可以解决，交接时必须同步告诉前后端人员：

### 16.1 关闭后端模拟模式

真实联调必须设置：

```text
WATER_GUN_SIMULATION_ONLY=false
```

并重启 FastAPI 后端。前端只改“安全模拟”文字或 CSS 没有作用。

### 16.2 “开启/关闭水枪”预览接口目前不发 MQTT

当前 Web 的水枪开关先调用 `preview`，只更新后端内存。要控制真实水泵，后端必须在用户确认或开关变化时，排队一条带当前位置、`spray_enabled` 和 `pump_control_percent` 的静态 `target_position` 命令。

### 16.3 动态心跳必须透传到 S3

当前 Web 心跳没有形成 MQTT 保活。必须按本文 7.2 节补齐，否则 S3 的安全超时会在目标不动时停泵。

### 16.4 Web“远程设备控制”的水泵卡片目前也走预览逻辑

当前水泵卡片被水枪功能接管，点击开关时调用的是水枪预览接口，不是标准的 `sendSiteCommand("pump", 100/0)`。项目需要二选一并保持界面文案一致：

1. 如果该卡片表示独立水泵总开关，就改为下发标准 `target=pump` 命令；或
2. 如果该卡片继续表示水枪喷水开关，就让后端排队包含当前位置的静态 `target_position`，不要只更新 preview。

否则会出现 C5 语音“打开水泵”可以控制真实泵，但 Web 水泵按钮不能控制的情况。

---

## 17. C5 语音控制验收流程

### 17.1 语音打开水泵

1. C5 用户说“打开水泵”。
2. C5 把文本发给后端。
3. 后端返回高风险待确认操作，C5 显示确认界面。
4. 用户确认。
5. 后端向 S3 `command` Topic 下发 `target=pump,value=100,source=edge_voice`。
6. S3 启动真实水泵并发布相同 `command_id` 的成功 ACK。
7. 后端把操作状态改为 `executed`，Web 和 C5 均能看到结果。

### 17.2 语音关闭水泵

流程相同，但 S3 收到 `value=0` 后必须立即停泵。即使当前水枪动态会话处于活动状态，也应执行停泵并结束本地喷水状态。

### 17.3 语音对目标喷水

1. 用户通过 C5 明确要求“瞄准/喷某个物体”。
2. 后端调用摄像头定位，得到 `ground_range_mm` 和 `bearing_deg`。
3. C5 显示 `water_gun_target` 待确认操作。
4. 用户确认。
5. 后端向 S3 下发带 `position` 和 `water_gun` 的 `target_position`。
6. S3 先移动舵机，稳定后启动水泵。
7. S3 ACK，后端把 C5 操作状态更新为 `executed`。

只有完成第 6、7 步，才算 C5 语音控制真正闭环。仅在 C5 上显示“已确认”不算设备执行成功。

---

## 18. 最低测试用例

边缘端 Agent 完成代码后，至少验证：

1. 上电及复位过程中水泵始终关闭。
2. `pump=100` 启动，`pump=0` 停止，并返回真实 `actual_value`。
3. 静态目标左、正前、右三个方向正确，正负角方向没有写反。
4. 超范围目标不动作并返回 `TARGET_OUT_OF_RANGE`。
5. `spray_enabled=false` 时，无论 `pump_control_percent` 多大都不启泵。
6. `simulation_only=true` 时舵机和水泵均不动作。
7. 动态序号递增时更新目标，重复/倒退序号返回 `STALE_TARGET`。
8. 动态消息中断 3 秒后自动停泵。
9. 重复 `command_id` 不重复执行，只重发 ACK。
10. 过期命令不执行并返回 `COMMAND_EXPIRED`。
11. MQTT 断线和重连不会意外启泵。
12. Web 静态目标控制能够收到 ACK。
13. C5 语音“打开水泵→确认→执行→ACK”完整通过。
14. C5 语音“关闭水泵→确认”能在任何状态下停泵。
15. C5 语音水枪目标确认后，舵机先到位、水泵后启动。

---

## 19. 完成定义

以下条件全部满足才能宣布完成：

- S3 使用正确设备 ID 和 MQTT Topic。
- 水泵直接命令、静态水枪、动态水枪均经过统一校验。
- 舵机和水泵是真实硬件输出，不是串口打印。
- `simulation_only` 安全语义有效。
- S3 返回与命令相同的 `command_id`。
- Web 必须等设备 ACK 后显示成功。
- C5 语音操作必须经过确认，且设备 ACK 后变为 `executed`。
- 重复、过期、越界和失联场景均保持停泵安全。
- 动态心跳已真正到达 S3。
- capabilities 和 telemetry 反映真实硬件能力与实际输出。

---

## 20. 当前工程中的参考实现位置

如接收本文的 Agent 能访问当前工程，可对照以下文件理解协议，但不要覆盖队友已有的硬件驱动和引脚配置：

```text
Web 水枪交互：
D:\比赛\物联网设计\物联网设计web\pro\src\App.vue

Web API：
D:\比赛\物联网设计\物联网设计web\pro\src\services\api.ts

后端 MQTT 收发：
D:\比赛\物联网设计\物联网设计web\pro\backend_api\mqtt_service.py

后端标准 S3 命令与 ACK：
D:\比赛\物联网设计\物联网设计web\pro\backend_api\site_service.py

后端水枪状态机：
D:\比赛\物联网设计\物联网设计web\pro\backend_api\water_gun_service.py

C5 MQTT 语音请求与确认：
D:\contest_english\iot_design\esp32\c5\common_components\sensair_iot\src\sensair_iot.c

C5 语音待确认操作解析：
D:\contest_english\iot_design\esp32\c5\common_components\sensair_voice\src\sensair_voice.c

当前 S3 协议参考：
D:\contest_english\iot_design\esp32\esp32s3\study\lib\mqtt\mqtt_client.cpp
D:\contest_english\iot_design\esp32\esp32s3\study\lib\mqtt\iot_mqtt.h
D:\contest_english\iot_design\esp32\esp32s3\study\src\main.cpp
```

接收本文的 Agent 应先读取队友实际 S3 工程，再将本文协议接到现有水泵和舵机驱动层；不要新建一套与原硬件代码并行、互相争抢 GPIO/PWM 的控制器。
