# SmartAgriBrain 前端与集成服务

最后同步日期：2026-07-22。

本目录是 Web 前端、FastAPI 集成服务和本地联调脚本的唯一开发源。页面负责环境监测、设备控制、水枪目标、智能托管、病害识别、知识库、报警和 AI 助手；浏览器只调用 FastAPI，不直接保存 MQTT 设备凭据。

## 1. 目录

- `src/`：Vue 3 前端源码。
- `backend_api/`：FastAPI 源码和测试。
- `scripts/`：Web、后端、开发、安装、便携启动和 Git 推送脚本。
- `shared_data/`：前后端可复用的静态数据。
- `docs/frontend.md`：完整前端业务逻辑。
- `docs/integration.md`：ESP32、C5、MQTT、控制和联调。
- `.vscode/tasks.json`：从 VS Code 启动、验证和设备开发的任务入口。
- `AGENTS.md`：当前目录和受保护推送机制的修改约束。

仓库根目录 `docs/` 保存统一契约、总体架构和项目唯一问题清单。前端目录不再为每个局部功能新建一份说明文件。

## 2. 系统边界

- ESP32-C5：语音交互和屏幕显示。
- 普通 ESP32：传感器采集、MQTT 上报、GPIO26 水泵、GPIO14 补光灯和 GPIO27/GPIO13 二维舵机云台。
- FastAPI：REST/SSE/WebSocket、业务状态、命令记录、知识库、AI/视觉/语音服务和可选 MQTT 网关。
- EMQX：FastAPI 与嵌入式设备之间的云端消息交换。

普通 ESP32 的协议 ID 暂保留 `greenhouse_001_s3`，但真实芯片不是 ESP32-S3。旧 `sensairshuttle_001` 只用于兼容历史接口，不得用于新水枪命令。

## 3. 环境与配置

前端要求 Node.js `>=20.19`。后端使用 `backend_api/.venv`，不得依赖系统 Python 的全局包。

安装前端依赖：

```powershell
npm install
```

创建后端虚拟环境并安装运行依赖：

```powershell
python -m venv backend_api/.venv
backend_api/.venv/Scripts/python.exe -m pip install -r backend_api/requirements.txt
```

需要运行测试时安装开发依赖：

```powershell
backend_api/.venv/Scripts/python.exe -m pip install -r backend_api/requirements-dev.txt
```

前端本地变量放在 `.env.local`，可用变量见 `.env.example`。后端变量放在 `backend_api/.env`；`backend_api/.env.mqtt.local` 后加载并覆盖同名 MQTT 值。所有真实密钥、本地数据库、上传数据和日志都由仓库根 `.gitignore` 排除。

## 4. 启动

启动 Web：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/web/start-web.ps1
```

启动 FastAPI：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/backend/start-backend.ps1
```

同时启动 Web 与 API：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start-full-stack.ps1
```

该命令在后台启动两个服务，等待 API 健康检查和 Web 首页就绪后返回 PowerShell 提示符。受管后台模式会关闭 Uvicorn 自动重载，避免重载器替换 PID 后遗留持有摄像头的 Python 进程。停止它们时执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/stop-full-stack.ps1
```

停止脚本会结束后端和前端完整进程树，并验证 `8000`、`5173` 端口已释放。即使 `%LOCALAPPDATA%\SmartAgriBrain\full-stack.json` 丢失，它也会根据本项目启动命令和监听端口重新发现受管进程；不能确认归属的进程不会被误杀。

不要用 `Stop-Process` 单独结束某个 PID，这可能留下父进程、子进程或摄像头所有者。也可以直接双击 `一键启动.bat` 和 `一键关闭.bat`，两者分别调用上述受管启动、停止入口。

若使用 `start-web.ps1` 或 `start-backend.ps1` 分别启动，窗口被日志占用是正常前台服务行为，直接在对应窗口按 `Ctrl+C` 停止；窗口异常关闭后再运行 `stop-full-stack.ps1` 清理。

复制到新 Windows 电脑后可以运行根目录 `一键启动.bat`。便携脚本会检查 Node/Python、创建缺少的依赖和虚拟环境、生成示例本地配置并启动前后端。真实 AI、天气、视觉、语音和 MQTT 仍需填写对应凭据。

启动后访问 `http://localhost:5173`，默认 API 为 `http://localhost:8000`。

## 5. 验证与设备任务

直接在 VS Code 打开当前 `前端/` 目录，任务面板提供：

- `SmartAgri: Verify Web and API`：完整后端 pytest 和前端生产构建，不要求设备源码。
- `SmartAgri: Start full stack`：启动 FastAPI 与 Vite。
- `SmartAgri: Stop full stack`：结束 FastAPI、Vite 及其完整子进程树并释放端口。
- `SmartAgri: Build ESP32`：使用仓库根 `esp32/platformio.ini`。
- ESP32 烧录和串口监视：自动检测非 C5 串口，有歧义时显式传入 COM 口。
- C5 构建、烧录和监视：只在仓库存在 `esp32c5_voice_display/` 时可用。

命令行只验证 Web 与 API：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/build-all.ps1 -SkipEsp32 -SkipC5
```

开发环境检查会把 Node、npm 和后端 Python 作为必需项，把 PlatformIO、ESP-IDF、EMQX 配置、设备源码和云端连通性作为可选集成项：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/check-environment.ps1
```

## 6. 脚本边界

- `scripts/web/` 只负责 Web。
- `scripts/backend/` 只负责 API 启动和重启。
- `scripts/dev/` 负责环境检查、全栈启动、构建、烧录和串口。
- `scripts/setup/` 负责 EMQX 本地凭据文件和设备配置生成；不会安装、启动或配置本地 Broker。
- `scripts/portable/` 负责新电脑的一键准备。
- `scripts/git/` 是受保护的前端快照推送机制。

`scripts/git/push-frontend.bat` 把当前目录的受控快照推送到远端 `feature/frontend` 分支的 `frontend_dashboard/`。`.push-cache/` 是持久化推送队列，不得清空或重建；不得修改远端、目标分支、SSH 方式或全局 Git 配置，除非用户明确批准并完成 `AGENTS.md` 要求的验证。

## 7. 当前运行边界

当前配置只支持真实硬件联调：

- 本机 EMQX 配置文件存在时，`MQTT_ENABLED=true` 且 `DEVICE_COMMAND_TRANSPORT=mqtt`。
- Web 动态 heartbeat 会递增服务端序号，并进入 MQTT 保活队列。
- C5 尚未消费普通 ESP32 的最终 `command_ack`。

页面本地成功不能证明水泵、补光灯或舵机已动作；必须收到设备 ACK。真实联调条件见 [设备通信与联调](docs/integration.md)。

## 8. 代码组织规则

### 8.1 前端

`src/App.vue` 当前集中八个主视图和大量状态。新增完整页面优先放入 `src/views/<feature>/`，复用业务逻辑放入 `src/composables/`，单一功能组件跟随功能目录，真正跨功能组件才进入 `src/components/`。

`src/services/api.ts` 统一 REST/SSE 请求和错误处理，`src/services/smartControl.ts` 负责页面侧托管计算，`src/types.ts` 保存跨页面领域类型。设备事实和共享业务状态必须来自后端，不能只修改页面状态伪造执行成功。

### 8.2 后端

后端当前从 `backend_api/` 直接执行 `uvicorn main:app`，大量模块使用同级导入。新增业务沿用 `*_routes.py`、`*_service.py`、`*_models.py` 和 `*_schemas.py` 约定；在正式包化改造前不得单独移动模块，否则会同时破坏启动和测试。

路由层只处理 HTTP，服务层处理业务，模型和 Schema 分别处理持久化与接口数据。设备命令必须经过后端记录、有效期、限幅和 ACK 状态链路。

## 9. 生成文件

以下内容可以存在于开发机，但不是源码：

- `node_modules/`、`dist/`、`tsconfig.tsbuildinfo`。
- `backend_api/.venv/`、Python 字节码和测试缓存。
- `.env`、`.env.local`、`backend_api/.env`、`backend_api/.env.mqtt.local`。
- `backend_api/smartagribrain.db`、`uploads/`、`position_captures/` 和日志。
- `.push-cache/`、`.push-tmp/` 和历史嵌套目录。

忽略规则统一维护在仓库根 `.gitignore`，不在子目录重复创建。清理时不得删除数据库、上传文件、定位截图、虚拟环境、依赖或 `.push-cache`，除非用户明确要求。

## 10. 后续重构顺序

当前 `App.vue`、`styles.css` 和 `services/api.ts` 体积过大，前端生产包也已超过 Vite 默认 500 kB 提示阈值。后续按以下顺序处理：

1. 为八个主视图补页面行为测试和 API 测试替身。
2. 按 `overview`、`realtime`、`history`、`disease`、`ai`、`control`、`knowledge`、`alarms` 提取视图。
3. 提取助手、水枪、天气、历史图表和持久化 composable。
4. 按功能拆分全局 CSS，并用动态导入做页面级代码分包。
5. 按领域拆分 API 客户端，保留统一 HTTP 核心。
6. 最后评估后端包化，并一次性同步导入、启动命令和测试。

## 11. 文档与问题

- [前端业务逻辑](docs/frontend.md)
- [设备通信与联调](docs/integration.md)
- [统一 MQTT/REST 与领域标准](../docs/smartagribrain-v1-standard.md)
- [项目唯一问题与答复汇总](../docs/open-questions.md)

所有需要项目负责人确认的字段、硬件事实、产品行为或协同决策只写入 `docs/open-questions.md`。问题必须包含背景、影响、推荐方案、回答格式和明确的回答位置；其他文档只引用 Q 编号。
