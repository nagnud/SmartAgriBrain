# 设备通信与联调

最后同步日期：2026-07-22。

本文件统一说明 Web、FastAPI、EMQX、ESP32-C5 和普通 ESP32 的控制与联调。完整字段、单位、Topic、状态和错误码只以仓库根目录 [SmartAgriBrain v1 统一标准](../../docs/smartagribrain-v1-standard.md) 为准。

## 1. 端侧职责

- Web 负责监测、配置、用户确认和状态展示，只调用 FastAPI REST/SSE。
- FastAPI 负责业务状态、权限、限幅、命令记录、知识库、AI 服务和可选 MQTT 网关。
- EMQX 云端 Broker 负责后端与嵌入式设备的消息交换，不直接暴露给浏览器。
- ESP32-C5 负责录音、播放、屏幕和云端语音交互，不直接驱动水泵或云台。
- 普通 ESP32 负责传感器采集、MQTT 上报、水泵、补光灯和二维 SG90 云台。

现场控制器是普通 ESP32，不是 ESP32-S3。协议 ID 暂保留 `greenhouse_001_s3`，名称中的 `_s3` 只是历史兼容标识。旧 `sensairshuttle_001` 只用于兼容历史遥测，不得用于新水枪命令。

## 2. 硬件能力

- GPIO27：SG90 水平轴。
- GPIO13：SG90 俯仰轴。
- GPIO14：补光灯 PWM，目标范围 `0..90%`。
- GPIO26：水泵 PWM，目标范围 `0..100%`。

水泵和水枪是同一套供水装置，所有普通水泵命令和水枪命令必须共用 GPIO26 输出、安全停止和运行状态。

当前 v1 原子命令只支持 `pump`、`grow_light`、`pan` 和 `tilt`。风机、加热、降温、通风、CO2、卷帘和报警器不属于当前普通 ESP32 能力，已从前端正式控制流移除。

## 3. 通信链路

```text
Web -- REST/SSE --> FastAPI -- MQTT command --> 普通 ESP32
Web <-- REST/SSE -- FastAPI <-- MQTT ACK/telemetry/status -- 普通 ESP32

ESP32-C5 -- MQTT/HTTPS --> FastAPI -- MQTT command --> 普通 ESP32
ESP32-C5 <-- 后端状态事件 -- FastAPI <-- MQTT ACK -- 普通 ESP32
```

Web 和 C5 只提交用户意图，不直接拼接 GPIO 语义。FastAPI 生成带唯一 `command_id`、有效期和来源的命令；ESP32 再执行版本、设备 ID、值域、有效期和幂等检查。

设备主题统一为：

```text
smartagribrain/v1/devices/{device_id}/command
smartagribrain/v1/devices/{device_id}/command_ack
smartagribrain/v1/devices/{device_id}/telemetry
smartagribrain/v1/devices/{device_id}/status
smartagribrain/v1/devices/{device_id}/capabilities
```

命令、ACK、遥测、状态、能力和 LWT 当前统一使用 QoS 1。命令发布 `retain=false`。QoS 1 允许重复投递，所以后端和 ESP32 都必须按完整 ID 幂等处理。

## 4. EMQX 配置

项目不再使用本地 Mosquitto。Broker 统一为外部 EMQX，地址、凭据和 CA 证书均是部署机本地配置，不得提交到仓库。

后端默认状态是：

```text
MQTT_ENABLED=true
DEVICE_COMMAND_TRANSPORT=mqtt
MQTT_URI=mqtts://your-emqx-host:8883
MQTT_TLS=true
MQTT_USERNAME=backend-account
MQTT_PASSWORD=local-secret
```

此状态下页面请求只更新后端本地状态，不会产生真实设备命令。真实联调至少需要：

```text
MQTT_ENABLED=true
DEVICE_COMMAND_TRANSPORT=mqtt
MQTT_URI=mqtts://your-emqx-host:8883
S3_DEVICE_ID=greenhouse_001_s3
```

`backend_api/.env` 先加载，`backend_api/.env.mqtt.local` 后加载并覆盖同名值。使用 `scripts/setup/configure-emqx.ps1` 生成后一个文件；该文件包含真实凭据，必须保持忽略且不得提交。

后端和两个嵌入式设备必须使用同一 EMQX 域名、端口、TLS、CA 和 Topic 前缀；账号应按后端、ESP32 和 C5 分离并配置最小 ACL。ESP32 的 CA PEM 由配置脚本写入忽略文件 `esp32/include/emqx_ca_cert.h`。

## 5. 普通控制

普通执行器使用 `operation=set`。后端应为每个发生变化的执行器生成一条独立命令，ESP32 应返回同一 `command_id` 的 ACK。

水泵 50% 示例：

```json
{
  "schema_version": "1.0",
  "command_id": "91b4635f-1b4d-4c9c-a6b2-a33ad6209984",
  "device_id": "greenhouse_001_s3",
  "site_id": "greenhouse_001",
  "issued_at": 1784620800000,
  "expires_at": 1784620830000,
  "source": "web_automation",
  "command": {
    "operation": "set",
    "target": "pump",
    "value": 50
  }
}
```

补光灯命令把目标改为 `grow_light`，值限制为 `0..90`。前端水枪正式交互不得拆成独立 `pan`、`tilt`、`pump` 命令，否则无法保证停泵、转向、稳定和开泵顺序。

## 6. 水枪复合控制

正式水枪使用 `operation=target_position` 和 `target=position`。参数包含方位、地面距离、模式、泵功率、定时时长、动态会话 ID 和递增序号。

ESP32 非阻塞环路为：

1. 校验版本、ID、有效期、模式、坐标、百分比、会话和序号。
2. 立即关闭 GPIO26 水泵。
3. 使用临时映射计算两轴舵机目标。
4. 写入舵机 PWM。
5. 非阻塞等待临时 800 ms 稳定时间。
6. 再次检查命令有效期和会话状态。
7. 建立定时截止或 3 s 动态超时保护。
8. 开泵并发布 ACK。
9. 主循环持续推进定时器和动态超时，到期立即停泵。

坐标到舵机角度、800 ms 稳定时间、水泵 40% 最小启动值和距离功率关系均为 `UN_CALIBRATED_PLACEHOLDER`，只能验证程序流程，不能宣称已经精确瞄准。

Web 当前每 1000 ms 调用后端 heartbeat，后端约 3000 ms 判定会话超时，但 heartbeat 只刷新内存，不发 MQTT、不递增 `sequence`。真实联调前，后端必须向 ESP32 发布设备可见的 1 s 保活；ESP32 继续保留 3 s 无合法新序号即停泵。

## 7. 智能托管

前端 `smart_control_update`、`smart_control_stop` 和需求值是页面内部模型，不是 ESP32 v1 命令。正式链路应由后端把有效托管结果转换为独立 `set` 命令。

当前普通 ESP32 可直接使用的托管执行器只有水泵和补光灯。水泵现由水枪功能独占，页面代码强制托管水泵需求为 0；智能托管不得在没有用户确认和安全会话时自动生成水枪目标。

算法可使用温度、光照、土壤湿度、CO2、历史趋势、天气和执行器状态。输入缺失、时间过旧、超出物理范围或设备离线时必须停止自动下发，不能用默认数值伪造正常遥测。

托管关闭时应根据安全策略分别发布 `pump=0` 和 `grow_light=0`，不得向 ESP32 发布它不识别的 `smart_control_stop`。

## 8. C5 语音和 Web 语音

C5 把语音转成结构化意图并进入后端确认流程，不直接控制 GPIO。水泵、补光灯和水枪具有硬件副作用，必须由用户确认后再生成设备命令。

C5 当前只订阅 `view_state` 与 `assistant/response`，不订阅普通 ESP32 的 `command_ack`，因此尚不能展示最终设备执行结果。后端还需把 ACK 转换成 C5 可消费的最终状态事件。

浏览器语音输入使用 Web Speech API，将识别文字写入助手输入框，不调用后端转写接口。Chrome 或 Edge 不支持或未授权麦克风时，用户仍可手动输入。后端的语音 HTTP/WebSocket 接口服务于 C5，是另一条链路。

## 9. 安全和 ACK

- Wi-Fi 或 MQTT 断开时立即停泵。
- 动态模式 3 s 无合法新序号时立即停泵。
- 过期命令、重复旧序号、越界坐标和不支持目标不得写 GPIO。
- MQTT 3.1.1 没有 Message Expiry，ESP32 必须按 `expires_at` 拒绝 Broker 补发的旧命令。
- SG90、水泵和水枪没有闭环位置、水流或命中传感器，ACK 只能表示控制输出已应用。

Web 提交后先显示等待回执；匹配 `command_id` 的 `executed` ACK 到达后，只能显示“设备已应用控制输出，未验证真实水流、舵机角度或命中结果”。拒绝、过期、离线和 ACK 超时必须分别展示，不能把本地状态更新当作设备 ACK。

## 10. 联调与验收

1. 统一后端、Broker 和 ESP32 的 IP、端口、TLS 和凭据。
2. 运行 MQTT ACL 测试，确认 C5 与 ESP32 无法访问对方未授权主题。
3. 启动后端，确认日志显示 MQTT 已连接。
4. 启动 ESP32，先验收 `status`、`capabilities` 和 `telemetry`。
5. 依次测试停泵、低功率水泵、低亮度补光灯、单轴舵机和水枪复合命令。
6. 对每条命令核对 REST 记录、MQTT JSON、ESP32 串口日志、ACK 和 Web 状态。
7. 验证过期、重复 ID、旧序号、断网、关页、后端重启和动态超时均会停泵。

当前只能确认源码和测试存在，不能确认 Web 到真实设备再返回 ACK 的端到端链路已跑通。主要剩余项是 C5 ACK 展示尚未统一、EMQX 最小 ACL 尚未实测，以及 ESP32 临时标定尚未完成；MQTT 配置、动态保活下发和 ESP32 遥测质量字段已实现。

所有待确认项只记录在 [问题与答复汇总](../../docs/open-questions.md)，当前重点是 Q-017、Q-019、Q-020、Q-021 和 Q-025。
