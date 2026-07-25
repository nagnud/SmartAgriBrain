# ESP32 与后端通信要求

最后同步日期：2026-07-23。

## 1. 范围与实现状态

本文定义普通 ESP32 与后端之间已经确认的通信和控制行为。ESP32 只通过 MQTT 与后端通信，不直接连接 Web 或 C5，也不处理语音识别。

当前固件已经完成 v1 主题、QoS 1、原子执行器命令、水枪复合命令、ACK、遥测、状态、能力声明、幂等缓存和非阻塞水枪状态机。前端/FastAPI 只走真实 REST、EMQX MQTT 和设备 ACK 路径；源码已通过 PlatformIO 构建，但实体硬件的端到端闭环仍需现场验收。

实际硬件是普通 ESP32，PlatformIO 使用 `esp32dev`。协议仍使用 `device_id=greenhouse_001_s3` 和 `site_id=greenhouse_001`；`_s3` 只是兼容命名，不代表芯片型号。

## 2. 通信链路

```text
Web/C5 -- REST、SSE --> smartagribrain-api -- MQTT command --> ESP32
Web/C5 <-- REST、SSE -- smartagribrain-api <-- MQTT ACK/遥测/状态 -- ESP32
```

正式主题为：

```text
smartagribrain/v1/devices/{device_id}/command
smartagribrain/v1/devices/{device_id}/command_ack
smartagribrain/v1/devices/{device_id}/telemetry
smartagribrain/v1/devices/{device_id}/status
smartagribrain/v1/devices/{device_id}/capabilities
```

固定消息策略：

- `command`：后端发布、设备订阅，QoS 1，retain=false。
- `command_ack`：设备发布、后端订阅，QoS 1，retain=false。
- `telemetry`：设备发布、后端订阅，QoS 1，retain=false。
- `status`：设备发布、后端订阅，QoS 1，retain=true。
- `capabilities`：设备发布、后端订阅，QoS 1，retain=true。
- LWT：设备异常断开时由 Broker 发布，QoS 1，retain=true。

设备使用 MQTT 3.1.1 TLS 持久会话。QoS 1 是至少一次投递，后端和设备都必须执行幂等处理。

## 3. 精简命令信封

设备只接受以下公共结构：

```json
{
  "command_id": "c820003f-b6c4-4f6d-a3e3-2194c7c77989",
  "expires_at": 1784620830000,
  "command": {}
}
```

字段规则如下：

- `command_id` 接受 UUID v4 或 1 至 20 位十进制字符串，按完整字符串作为幂等键。
- `expires_at` 为 UTC Unix Epoch 毫秒。设备拒绝已经过期或超过未来 300 秒的命令。
- `command` 是补光灯原子命令或水枪复合命令。

协议版本和设备身份由精确 Topic `smartagribrain/v1/devices/{device_id}/command` 确定。后端在数据库中保存站点、来源、原因和创建时间，MQTT JSON 不再重复这些审计字段。设备时间未同步时拒绝所有正式控制命令；命令已过期时返回 `COMMAND_EXPIRED`。

## 4. 补光灯原子命令

唯一允许的原子命令是 `target="grow_light"`。GPIO26 水泵和 GPIO27/GPIO13 云台是水枪内部部件，只能通过下一节的 `target_position` 复合命令控制。

```json
{
  "command": {
    "operation": "set",
    "target": "grow_light",
    "value": 60
  }
}
```

`grow_light` 只接受 0 至 90 的整数，驱动 GPIO14 高电平有效 PWM。`pump`、`pan` 和 `tilt` 不是独立命令；正式的“向目标喷水”必须使用复合水枪命令，保证停泵、转向和开泵顺序不可被网络乱序破坏。

## 5. 水枪复合命令

完整结构为：

```json
{
  "command": {
    "operation": "target_position",
    "target": "position",
    "position": {
      "ground_range_mm": 850,
      "bearing_deg": -12.5
    },
    "water_gun": {
      "mode": "static",
      "spray_enabled": true,
      "pump_control_percent": 50,
      "session_id": null,
      "sequence": 7,
      "spray_schedule": "timed",
      "spray_duration_seconds": 113,
      "spray_ends_at": 1784620913000
    }
  }
}
```

字段规则如下：

- `ground_range_mm`：目标水平距离，临时允许 300 至 1200 mm。
- `bearing_deg`：0 为正前方，负数向左，正数向右，允许 -90 至 90 度。
- `mode`：`static` 或 `dynamic`。
- `spray_enabled`：false 表示通过身份校验后的有效停止请求。
- `pump_control_percent`：0 至 100；喷水时必须大于 0，停止时必须为 0。
- `session_id`：dynamic 必填且最长 79 字符；static 必须为空或 null。
- `sequence`：dynamic 必须大于 0 并在同一会话中严格递增。
- `spray_schedule`：`continuous` 或 `timed`。
- `spray_duration_seconds`：timed 喷水必填，1 至 86399 秒。
- `spray_ends_at`：timed 喷水必填，UTC Unix Epoch 毫秒；持续或动态模式必须为空。

## 6. 控制环路

### 6.1 接收与校验

1. MQTT 任务只拼接完整消息并放入深度受限的队列，不直接操作 GPIO。
2. MQTT 客户端只订阅本设备精确 `command` Topic；主循环校验 JSON、命令 ID 和有效期。
3. Topic 身份确认后计算原始报文指纹，并检查已完成或正在执行的同 ID 命令。
4. 校验具体执行器或水枪字段、数值范围、会话序号和定时时间。
5. 非本设备 Topic 不会进入命令队列；本设备 Topic 上业务字段非法的水枪命令会触发安全停泵并发布拒绝 ACK。

### 6.2 水枪执行

1. 目标变化或收到停止请求时先关闭 GPIO26。
2. 使用临时坐标映射计算舵机角度，越界时拒绝，不能静默钳位到另一个目标。
3. 写入两个 SG90 目标。
4. 非阻塞等待临时 800 ms 稳定时间。
5. 建立本地定时截止或动态会话超时保护。
6. 再写入 GPIO26 水泵 PWM。
7. 控制输出写入且状态机无错误后发布最终 ACK。

### 6.3 动态目标与保活

1. Web 指针只生成设备支持的 `300..1200 mm` 距离和 `-90..90 deg` 方向角。
2. Web 串行发送动态目标；前一 HTTP 请求未结束时只保留最新位置，不并发发送中间目标。
3. Web 不生成 MQTT `sequence`。后端在同一把锁内为目标更新和每秒 heartbeat 统一分配严格递增序号。
4. 后端每 1000 ms 最多将当前最新目标进入 MQTT 队列；连续拖动可能产生多个真实目标，单击一个位置只保留最终目标。
5. ESP32 只有在距离或方向实际变化时才重新写两个舵机。相同目标保活只刷新动态序号和 3 秒超时；稳定等待期间也不重复写 PWM。
6. 动态模式关闭喷水时仍保留 `session_id` 和最后 `sequence`，防止延迟旧目标绕过乱序校验；退出动态模式后才清除。
7. 新目标仍执行“先停泵、写舵机、等待 800 ms、再决定开泵”的顺序。

### 6.4 本地安全停止

以下任一条件发生时立即停泵并清除定时/动态状态：

- 上电初始化、Wi-Fi 断开或 MQTT 断开。
- 有效停止命令。
- 定时截止到达。
- 动态模式 3 秒没有收到合法新序号。
- 已认证水枪命令的业务字段非法。
- 新目标替换当前目标。

EMQX ACL 必须保证只有后端账号能够发布设备 `command`。未经精确 Topic 接收、命令 ID 和有效期校验的数据不能驱动 GPIO，也不能利用“停止优先”形成未授权停机入口。

## 7. 机械限位与距离模型

当前映射和安全范围如下：

- `bearing_deg=-90..90` 线性映射为水平舵机 0 至 180 度，0 对应 90 度。
- 垂直舵机实体安全范围为 5 至 60 度；5 度时水枪平行向前，60 度时水枪竖直向上。
- `ground_range_mm=300..1200` 单段线性映射为垂直舵机 60 至 5 度：300 mm 对应 60 度，1200 mm 对应 5 度。
- 换算公式为 `tilt_deg = round(60 - (ground_range_mm - 300) * 55 / 900)`；距离每增加 100 mm，角度约降低 6.11 度。
- 上电先关闭水泵，再将水平轴置于 90 度、垂直轴置于 5 度；垂直轴所有写入最终强制限制在 5 至 60 度。
- 舵机稳定等待为 800 ms。
- 水泵非零值低于 40% 时提升到 40%。

垂直轴 5 度和 60 度是已确认的实体端点。距离到角度的线性关系仍未结合真实水压、喷嘴、重力和落点完成标定；完成喷水实验前不得宣传为准确瞄准或闭环喷水。

## 8. ACK、遥测和能力

ACK 的 `state` 只允许 `executed` 或 `rejected`。精简 ACK 只包含 `command_id`、`acknowledged_at`、`state`、`actual_value`、`feedback_verified` 和 `error`。后端已按 `command_id` 保存原命令，因此设备不再回显命令摘要、位置和水枪参数。

SG90 没有位置反馈，水路也没有流量传感器。因此 `executed` 只表示控制输出已应用且状态机无错误，不表示真实角度、水流量或目标命中已经被测得。

遥测只保留用于 QoS 1 去重的 `message_id`、采样时间、四类传感器及质量、补光灯 PWM 值、二维角度、水枪状态和 RSSI。设备 ID 与协议版本从 Topic 推导，站点从后端设备注册关系推导；不再上报重复身份、序号、时间质量和固定的 Wi-Fi/MQTT connected 字符串。能力消息只声明四类传感器、补光灯、水枪和固件能力。

## 9. 已完成与剩余工作

设备源码已经完成：

- ESP-IDF MQTT QoS 1 持久会话和 TLS。
- 正式主题和公共命令信封。
- 补光灯原子命令与水枪复合命令解析。
- 水枪独占 GPIO26、GPIO27 和 GPIO13 输出。
- 水枪非阻塞状态机、定时停止和动态超时。
- 50 条命令 ACK 缓存、内容指纹和重复 ACK 重发。
- 状态、能力、遥测和 ACK 发布。
- 与控制阶段对应的串口诊断日志和详细代码注释。

仍需完成：

- 按实物测量替换全部临时标定值。
- 遥测周期已统一为 5 秒；真机联调时确认各传感器采样周期不会阻塞 MQTT 主循环。
- 决定 ACK 缓存的时间淘汰策略，使“最近 50 条且至少 10 分钟”可验证。
- 验证后端命令状态机、ACK 持久化和实体硬件端到端闭环。
- Q-017 的设备可见动态保活已实现；仍需按 Q-019 完成 Web/C5 ACK 文案、最终回执和实体断网停泵验收。

## 10. 验收要求

1. PlatformIO 构建通过，且主固件没有使用旧 `farm/test/control_cmd_888` 作为正式入口。
2. Broker 观察到五类正式主题的 QoS、retain 和 payload 与统一标准一致。
3. 同一 `command_id` 重发不会再次驱动硬件或重置定时器。
4. 目标变化、断网、超时和非法已认证水枪命令都能看到先停泵日志。
5. Web 的 `EXECUTED` 只在收到设备 ACK 后出现，并使用“控制输出已应用”的准确文案。
6. 真机分别验证 GPIO14、GPIO26、GPIO27、GPIO13、电源共地和机械安全范围。
