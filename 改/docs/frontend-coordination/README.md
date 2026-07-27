# 前端与后端协同状态

最后同步日期：2026-07-23。

本文件汇总 Web、FastAPI、Broker、ESP32-C5 与普通 ESP32 的联调边界。问题结论以 [问题与答复汇总](../open-questions.md) 为唯一依据，正式字段以 [SmartAgriBrain v1 统一标准](../smartagribrain-v1-standard.md) 为准。

## 1. 设备侧基线

- 实际芯片是普通 ESP32，PlatformIO 环境为 `esp32dev`。
- 兼容协议 ID 暂保留 `greenhouse_001_s3`；`_s3` 不表示真实芯片型号。
- Topic 前缀为 `smartagribrain/v1/devices/greenhouse_001_s3`。
- MQTT 使用 3.1.1、QoS 1 和设备持久会话。
- 原子执行器目标为 `pump`、`grow_light`、`pan`、`tilt`。
- 水枪复合命令为 `operation=target_position`、`target=position`。
- 动态模式要求同一 `session_id` 的 `sequence` 严格递增；3 s 没有合法新序号时设备本地停泵。
- `executed` 仅表示控制输出已应用，不表示已检测真实水流、角度或命中结果。

## 2. 已核实的前端与后端状态

### 2.1 真实 MQTT

当前部署配置通过忽略的 `backend_api/.env.mqtt.local` 启用 `MQTT_ENABLED=true` 与 `DEVICE_COMMAND_TRANSPORT=mqtt`，并已完成 EMQX TLS 连接订阅验证。水枪控制不再具有本地模拟分支，确认后的请求会进入真实设备命令队列并等待 ESP32 ACK。

本项目不再使用本地 Mosquitto。`scripts/setup/configure-emqx.ps1` 会生成忽略的 `backend_api/.env.mqtt.local`；`database.py` 在加载 `backend_api/.env` 后会加载该文件并覆盖同名 MQTT 配置。该脚本只接受 EMQX TLS `mqtts://...:8883` 和本机 CA 证书。

### 2.2 动态水枪保活

Web 每 1000 ms 刷新后端动态会话。后端会为每次有效 heartbeat 递增服务端 `sequence`，并在 1 秒节拍向 MQTT 命令队列重发当前 `target_position`；ESP32 只在收到新序号后刷新 3 s 本地安全超时。后端重启时仍不恢复旧会话，因此设备端超时停泵仍是必要安全边界。

### 2.3 ACK 展示

Web 当前把 `executed` 映射为 `succeeded`，显示“状态已同步”；没有独立 ACK 超时状态。C5 当前不订阅 `command_ack`，只能显示“正在执行确认的操作…”，不能显示最终设备回执。

## 3. 真实联调必须完成的工作

1. 让后端实际加载 MQTT 配置，并在私有 `backend_api/.env.mqtt.local` 中设置：

```text
MQTT_ENABLED=true
DEVICE_COMMAND_TRANSPORT=mqtt
```

2. 已实现：后端每 1000 ms 向设备发布当前 `target_position`，保持同一 `session_id` 并统一递增 `sequence`；Web 不再与 heartbeat 竞争序号。
3. Web 和 C5 只在收到对应 `command_id` 的 ACK 后显示设备已应用输出。
4. Web 对 `executed`、`rejected`、ACK 超时和设备离线使用不同状态，并展示稳定错误码。
5. C5 通过后端事件获得最终 ACK，不得在确认对话结束时直接宣称硬件已执行。
6. 后端发布前生成唯一 `command_id`，保存命令状态，并按 `command_id` 幂等处理 QoS 1 重复 ACK。

## 4. 联调验收证据

真实联调完成需同时保存以下证据：

- 后端启动日志或进程连接显示 MQTT 已连接至 EMQX TLS `8883`。
- Broker 可见完整 `command`、`command_ack`、`telemetry`、`status` 和 `capabilities` 消息。
- ESP32 串口日志能关联 `command_id`，并显示校验、舵机等待、开泵/停泵和 ACK 阶段。
- Web 与 C5 的状态转换与实际 ACK 一致，断网、关页、后端重启和过期命令均不会使水泵继续运行。

## 5. 待改动文案

- `executed`：“设备已应用控制输出，未验证真实水流、舵机角度或命中结果”。
- `rejected`：“设备未应用控制输出：{error_code}”。
- ACK 超时：“等待设备回执超时，无法确认设备是否已应用控制输出”。
- 离线：“设备离线，未确认命令是否已执行”。

新的未确认问题必须先写入 `docs/open-questions.md`，不在本文件另起问题编号。
