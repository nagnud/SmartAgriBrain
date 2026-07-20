# 2026-07-20 当前架构与目录状态

## 1. 已确定的设备职责

- ESP32-C5 是语音与显示终端。它负责屏幕 UI、音频采集/播放，以及通过 `smartagribrain-api` 进行云端语音识别、大模型对话和语音合成。它不再负责农业传感器采集、农业遥测 MQTT 上报或二维云台控制。
- 通用 ESP32 是农业采集与云台节点。它负责传感器采集、通过 MQTT 向云端上报数据，以及后续二维舵机云台的水平和俯仰控制。
- `smartagribrain-api` 是唯一云端服务。它订阅采集 ESP32 的 MQTT 遥测，存储数据，调用云端语音/大模型服务，并把会话与业务结果返回给 C5 和 Web 前端。

固定数据流如下：

```text
采集 ESP32 -- MQTT 遥测 --> smartagribrain-api -- 数据库 --> Web 前端
                                |
                                +-- HTTPS --> 云端语音识别 / 大模型 / 语音合成
                                |
ESP32-C5 语音显示终端 -- HTTPS + SSE --> smartagribrain-api
```

ESP32-C5 不保存云端大模型、语音识别或语音合成的长期密钥。密钥只保存在云端 `smartagribrain-api` 的受保护环境变量中。

## 2. 当前工作区目录

```text
SmartAgriBrain/
  docs/
    README.md
    architecture-update-2026-07-20.md
    smartagribrain-v1-standard.md
    branch-collaboration-review.md
  esp32/
    src/                 通用 ESP32 应用入口和采集逻辑
    lib/                 Wi-Fi、MQTT、传感器、PID、泵和 LED 模块
    include/             配置头文件
    test/                独立测试代码
    doc/                 此 ESP32 工程原有说明
    .pio/                PlatformIO 本机构建缓存和依赖，不纳入版本控制
    platformio.ini
  frontend_dashboard/
  README.md
```

当前工作区根目录没有 C5 源码目录。C5 工程归位时，固定使用 `esp32c5_voice_display/`，不放入 `esp32/`，也不与 PlatformIO 采集工程混合。该目录本次不创建，因为用户要求先不修改 C5 代码或工程文件。

## 3. `esp32/` 工程已确认内容

该目录是 Arduino 框架的 PlatformIO 工程，环境名为 `esp32dev`，串口监视器为 115200，使用 Wi-Fi、PubSubClient、OneWire、DallasTemperature、FastLED 和 ArduinoJson。

已接入并在主循环中更新的采集对象：

- DS18B20 温度传感器。
- BH1750 光照传感器。
- 土壤湿度传感器。
- JW01 CO2 传感器。

现有 MQTT 发送逻辑会发布以下旧格式：

```json
{
  "fieldId": "field_001",
  "moisture": 0.0,
  "light": 0.0,
  "temp": 0.0,
  "co2": 0.0,
  "timestamp": 0
}
```

当前时间值来自 `millis()`，不是 UTC Unix 时间；主题和字段名也尚未符合 `smartagribrain-v1-standard.md`。这是现状记录，不表示本次已经改造。进入 ESP32 开发阶段时，采集上报应迁移为规范中的 `telemetry` 消息，并将设备能力声明为传感器采集节点。

工程中还存在水泵、加热、LED/PID 和 MQTT 控制订阅代码。这些是既有代码，不属于新的“采集上报 + 二维云台”职责。代码改造开始前，应先决定保留为本地安全控制、迁移到独立节点，还是明确下线；本次不改动它们。

## 4. 二维舵机云台状态

二维舵机云台是新增功能。当前 `esp32/` 目录中没有 Servo/LEDC 云台驱动、水平/俯仰角度模型、限位保护、云台 MQTT 命令解析或云台 ACK 实现。

后续代码阶段的固定模块边界如下：

- `lib/pan_tilt/`：二维舵机驱动、角度限幅、复位位和单轴运动接口。
- `src/`：将云端命令转换为水平角和俯仰角请求，不直接散落 PWM 调用。
- MQTT 命令：复用统一协议中的单原子命令原则；水平和俯仰分别确认，或由后端建立两个带独立 `command_id` 的命令。
- 状态上报：在采集 ESP32 的遥测中追加 `pan_tilt.pan_deg`、`pan_tilt.tilt_deg`、`pan_tilt.state`，单位均为度。

引脚、电源、舵机型号、有效角度范围和零点尚未出现在当前工程中，因此本文件不编造具体 GPIO 或角度值。它们必须在开始云台代码前由硬件负责人确认。

## 5. C5 语音与显示状态

C5 的新职责已经确定，但对应 C5 代码当前不在工作区根目录。进入 C5 开发阶段时，工程必须只包含以下职责：

- 屏幕显示设备在线状态、采集数据、语音会话状态和大模型回复。
- 录音、播放和会话 UI。
- 以 HTTPS 调用 `smartagribrain-api` 的语音会话接口，并使用 SSE 接收流式文本、状态和 TTS 播放指令。
- 不直接持久化大模型 API Key，不直接订阅农业采集 MQTT 主题，不控制二维云台。

语音识别和语音合成所选云服务、音频编码、采样率以及是否采用 C5 到云端的流式 WebSocket，尚未由现有代码或需求确定。它们必须在 C5 代码开始前单独冻结为语音接口扩展；在此之前不得把临时协议写进采集 ESP32 工程。

## 6. 安全与目录卫生

- 当前 `esp32/include/config.h` 含有明文 Wi-Fi 和 MQTT 连接凭据。该文件已经存在于工作区，本次未修改；这些凭据应视为已暴露并在后续安全处理时轮换。
- 轮换后，真实凭据必须移出受版本控制的头文件，使用本地私有配置或受保护的构建注入方式；仓库仅保留不含真实值的示例配置。
- `esp32/.pio/` 是生成目录。后续整理代码时不移动其内容，也不把它作为源代码评审对象。
- `esp32/doc/` 是采集 ESP32 的局部历史文档；跨端架构、协议和协同信息统一放在根目录 `docs/`。

## 7. 本次变更范围

本次只完成目录盘点和文档更新：没有修改 `esp32/`、C5、前端、后端或云台相关源代码，没有删除构建产物，也没有更改现有 MQTT 配置。
