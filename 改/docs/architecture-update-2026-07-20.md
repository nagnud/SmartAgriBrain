# 当前架构与目录状态

基线日期：2026-07-20。最后同步日期：2026-07-22。

## 1. 已确定的系统职责

- 普通 ESP32 是现场采集与执行节点。它采集土壤湿度、光照、温度和 CO2，通过 MQTT 上报数据，并控制水泵、补光灯和二维水枪云台。
- ESP32-C5 是语音与显示终端。它负责屏幕 UI、录音、播放以及通过云端服务完成语音识别、大模型对话和语音合成，不直接驱动现场执行器。
- `smartagribrain-api` 是唯一云端入口。它负责 MQTT 接入、遥测与命令持久化、REST/SSE、用户鉴权以及语音和大模型服务代理。
- Web 前端只调用 `smartagribrain-api`，不保存 MQTT 凭据，也不直接连接 Broker。

固定数据流如下：

```text
传感器/执行器 <-> 普通 ESP32 <-> MQTT Broker <-> smartagribrain-api <-> 数据库
                                                        ^
                                                        |
                                                   REST + SSE
                                                        |
                                             Web 前端 / ESP32-C5
```

## 2. 当前工作区

```text
SmartAgriBrain/
  docs/                    跨端架构、契约、问题、协同和 Word 设计文档
  esp32/
    src/                   普通 ESP32 主程序和运行环路
    include/               本机配置与统一 IoT 常量
    lib/                   MQTT、Wi-Fi、传感器、执行器和水枪状态机
    test/                  历史或独立测试代码
    doc/                   ESP32 工程说明
    .pio/                  PlatformIO 本机构建产物，不进入 Git
    compile_commands.json  IntelliSense 编译数据库，不进入 Git
    platformio.ini
  frontend_dashboard/      Web 管理端和现有本地服务原型
  前端/                  新增 Web/FastAPI/MQTT 集成工作区及联调说明
  README.md
```

当前工作区没有 C5 源码。C5 工程归位时固定使用 `esp32c5_voice_display/`，不得放入 `esp32/` 或与普通 ESP32 的 PlatformIO 工程混合。

## 3. 普通 ESP32 硬件定义

- 实际芯片：普通 ESP32，PlatformIO 环境为 `esp32dev`。
- 协议设备 ID：`greenhouse_001_s3`。其中 `_s3` 只是兼容前端的历史命名，不代表芯片型号。
- 站点 ID：`greenhouse_001`。
- GPIO27：SG90 水平轴，LEDC 通道 2，50 Hz。
- GPIO13：SG90 俯仰轴，LEDC 通道 3，50 Hz。
- GPIO14：高电平有效补光灯 PWM，LEDC 通道 0，1 kHz，协议范围 0 至 90%。
- GPIO26：高电平有效水泵 PWM，LEDC 通道 1，1 kHz，协议范围 0 至 100%。
- GPIO12：原 WS2812 灯带保留，但不响应 `grow_light` 命令。
- 舵机供电：独立稳定 5 V，并与 ESP32 共地。

水泵和水枪是同一套物理装置：GPIO26 控制水泵，水泵将水输送到水枪。普通 `pump` 命令和复合水枪命令必须经过同一个 PWM 输出函数和安全状态。

## 4. ESP32 已实现的软件能力

### 4.1 采集与执行

- 已接入 DS18B20 温度、BH1750 光照、土壤湿度和 JW01 CO2 更新流程。
- 已实现 GPIO14 补光灯百分比控制。
- 已实现 GPIO26 水泵百分比控制，非零 1 至 39% 暂时提升到 40%。
- 已实现 `PanTilt` 双 SG90 驱动和 0 至 180 度本机调试命令。
- 已实现 `WaterGunController` 非阻塞状态机，包括停泵、转向、等待 800 ms、开泵、定时停止和动态 3 秒超时。

40% 水泵启动值、800 ms 舵机稳定时间、目标坐标映射和距离功率关系均未实测，代码和消息必须标记 `UN_CALIBRATED_PLACEHOLDER`。

### 4.2 MQTT

固件使用 Arduino 框架内置的 ESP-IDF MQTT 客户端，不再依赖 PubSubClient。连接参数如下：

- MQTT 3.1.1 over TLS，部署端口当前为 8883。
- 设备 Client ID 为 `sab-dev-{device_id}`。
- 持久会话，30 秒 keepalive，5 秒自动重连。
- `command`、`command_ack`、`telemetry`、`status`、`capabilities` 和 LWT 全部为 QoS 1。
- `status` 和 `capabilities` retain；其他业务消息不 retain。
- MQTT 网络回调只拼接数据并放入队列，JSON 校验和硬件动作在 Arduino 主循环完成。

正式主题为：

```text
smartagribrain/v1/devices/{device_id}/command
smartagribrain/v1/devices/{device_id}/command_ack
smartagribrain/v1/devices/{device_id}/telemetry
smartagribrain/v1/devices/{device_id}/status
smartagribrain/v1/devices/{device_id}/capabilities
```

旧 `farm/test/control_cmd_888`、`waterDemand`、`lightDemand`、`panAngle` 和 `tiltAngle` 仅属于历史调试协议，当前主固件不再以其作为正式联调入口。

### 4.3 控制命令

- 原子命令：`pump`、`grow_light`、`pan`、`tilt`。
- 复合命令：`operation=target_position`、`target=position`。
- 静态模式支持持续喷水和本地定时停止。
- 动态模式要求同一 `session_id` 下 `sequence` 严格递增，3 秒收不到设备可见更新时停泵。
- 相同 `command_id` 和相同内容只重发首次 ACK；同 ID 不同内容被拒绝。

## 5. 主循环顺序

1. 检查 Wi-Fi；断网时优先请求统一安全停止，再尝试重连。
2. 推进 MQTT 事件、收包队列、协议校验和命令分发。
3. 推进水枪非阻塞状态机，包括舵机稳定、定时截止和动态超时。
4. 更新四类传感器和保留的 WS2812 模块。
5. 到达发送周期后发布统一遥测快照。

这个顺序保证网络回调不阻塞，并确保安全停止先于重连和后续控制。

## 6. 当前已知缺口

以下内容尚不能标记为端到端完成：

- `前端/backend_api` 已有 MQTT v1 接入、命令记录和 ACK/遥测处理代码，当前仅使用 EMQX TLS 和真实设备命令路径；实体 ESP32 的遥测、下行命令与 ACK 仍需完成端到端采样验收。
- Q-017、Q-019、Q-020 和 Q-021 已收到前端/后端核实答复；动态 MQTT 保活和真实模式已实现，ACK 展示、C5 最终回执和实体硬件验收仍需继续完成。
- 项目不使用本地 Mosquitto；普通 ESP32 与后端统一使用 EMQX TLS `8883`。
- `setup-local-mqtt.ps1` 生成 `.env.mqtt.local`，而后端启动脚本只加载 `.env`，是当前 MQTT 启用阻塞。
- 当前遥测周期配置为 5 秒，已与正式契约一致；真机联调仍需确认传感器实际采样周期与网络负载。
- MQTT JSON 已精简：状态和能力作为 retained 快照不使用 `message_id`，遥测保留 UUID `message_id` 和 `quality`。版本、设备和站点不再在每条 JSON 中重复。
- ACK 缓存容量为最近 50 条，但当前没有按“至少 10 分钟”设置独立时间淘汰规则。
- 临时坐标映射、机械安全角、水泵启动百分比和功率模型没有经过实物标定。
- C5 语音、屏幕和云端大模型代码不在当前工作区，无法据此确认完成度。

这些确定性差异属于待修复项，不通过修改文档掩盖。外部答复和未完成事项统一记录在 [问题与答复汇总](open-questions.md)。

## 7. 开发环境与目录卫生

- PlatformIO 工程位于 `esp32/`。从仓库根目录打开 VS Code 时，根工作区通过 `esp32/compile_commands.json` 提供 C/C++ 跳转。
- `esp32/.pio/`、`esp32/compile_commands.json`、`esp32/.vscode/` 和根 `.vscode/` 都是本机配置或生成物，不进入 Git。
- `esp32/include/config.h` 是本机私有配置，已被忽略。真实 Wi-Fi、MQTT 密码和 CA 配置不得提交。
- 任何曾经提交或公开过的连接凭据都应视为泄露并轮换。

## 8. 验证边界

PlatformIO 源码构建已经通过，说明当前主程序、ESP-IDF MQTT、ArduinoJson 和各本地库可以完成编译链接。尚未获得本轮真机 GPIO、舵机机械行程、水流、Broker、后端数据库和 Web/C5 闭环验收记录，因此这些项目不能写成“已经跑通”。
